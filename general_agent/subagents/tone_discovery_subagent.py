from __future__ import annotations

import json
from datetime import datetime

from google.adk.agents import LlmAgent

from general_agent.models import ToneDiscoveryResult, clamp_limit
from shared.db import get_pool
from template_assistant.llm import get_llm_model
from template_assistant.ml.goemotions import scores_from_pipeline_result

# Supports both dict {"joy": 0.9} and pipeline list [{"label": "joy", "score": 0.9}] formats.
_EMOTION_SCORE_SQL = """
COALESCE(
    (tte.tones ->> $1)::float,
    (
        SELECT (elem->>'score')::float
        FROM jsonb_array_elements(tte.tones) AS elem
        WHERE elem->>'label' = $1
        LIMIT 1
    ),
    0.0
)
"""


def _parse_tones(raw: object) -> dict[str, float]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if isinstance(parsed, dict):
        return {str(key): float(value) for key, value in parsed.items()}
    if isinstance(parsed, list):
        return scores_from_pipeline_result(parsed)
    return {}


def _row_to_result(row: object) -> ToneDiscoveryResult:
    return ToneDiscoveryResult(
        template_id=row["template_id"],
        template_name=row["template_name"],
        emotions=_parse_tones(row["tones"]),
        evaluated_at=row["evaluated_at"] or datetime.now(),
    )


async def find_templates_by_tone(
    emotion: str,
    min_score: float = 0.5,
    lang_local: str = "EN",
    param_cust_brand: str = "SKRILL",
    limit: int = 10,
) -> list[ToneDiscoveryResult]:
    """Find templates whose pre-computed tone score for ``emotion`` meets ``min_score``."""
    effective_limit = clamp_limit(limit)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                t.id AS template_id,
                t.name AS template_name,
                tte.tones,
                tte.evaluated_at
            FROM template t
            JOIN template_tone_evaluations tte ON tte.template_id = t.id
            WHERE UPPER(tte.lang_local) = UPPER($2)
              AND UPPER(tte.param_cust_brand) = UPPER($3)
              AND {_EMOTION_SCORE_SQL} >= $4
            ORDER BY {_EMOTION_SCORE_SQL} DESC NULLS LAST, t.name
            LIMIT $5
            """,
            emotion,
            lang_local,
            param_cust_brand,
            min_score,
            effective_limit,
        )

    return [_row_to_result(row) for row in rows]


async def rank_templates_by_emotion(
    emotion: str,
    lang_local: str = "EN",
    param_cust_brand: str = "SKRILL",
    limit: int = 10,
) -> list[ToneDiscoveryResult]:
    """Rank templates by pre-computed tone score for ``emotion``."""
    effective_limit = clamp_limit(limit)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                t.id AS template_id,
                t.name AS template_name,
                tte.tones,
                tte.evaluated_at
            FROM template t
            JOIN template_tone_evaluations tte ON tte.template_id = t.id
            WHERE UPPER(tte.lang_local) = UPPER($2)
              AND UPPER(tte.param_cust_brand) = UPPER($3)
            ORDER BY {_EMOTION_SCORE_SQL} DESC NULLS LAST, t.name
            LIMIT $4
            """,
            emotion,
            lang_local,
            param_cust_brand,
            effective_limit,
        )

    return [_row_to_result(row) for row in rows]


async def _find_templates_by_tone_tool(
    emotion: str,
    min_score: float = 0.5,
    lang_local: str = "EN",
    param_cust_brand: str = "SKRILL",
    limit: int = 10,
) -> list[dict]:
    results = await find_templates_by_tone(
        emotion,
        min_score=min_score,
        lang_local=lang_local,
        param_cust_brand=param_cust_brand,
        limit=limit,
    )
    return [result.to_dict() for result in results]


async def _rank_templates_by_emotion_tool(
    emotion: str,
    lang_local: str = "EN",
    param_cust_brand: str = "SKRILL",
    limit: int = 10,
) -> list[dict]:
    results = await rank_templates_by_emotion(
        emotion,
        lang_local=lang_local,
        param_cust_brand=param_cust_brand,
        limit=limit,
    )
    return [result.to_dict() for result in results]


def create_tone_discovery_subagent() -> LlmAgent:
    return LlmAgent(
        name="ToneDiscoverySubagent",
        model=get_llm_model("TONE_DISCOVERY"),
        description="""
        Finds and ranks templates by pre-computed emotional tone scores stored in
        template_tone_evaluations. Never runs GoEmotions at query time. Read-only.
        """,
        instruction="""
        You are the Tone Discovery Subagent. You find and rank templates by their
        pre-computed GoEmotions scores from template_tone_evaluations.

        ## Your tools
        - find_templates_by_tone: filter templates where a given emotion score
          meets or exceeds min_score.
        - rank_templates_by_emotion: rank all templates by a given emotion score.

        ## Behaviour rules
        - Never load or call the GoEmotions classifier — scores are pre-computed.
        - Respect the limit parameter (default 10, maximum 50).
        - Default lang_local is EN and param_cust_brand is SKRILL unless specified.
        - Never write to PostgreSQL or Redis.
        """,
        tools=[_find_templates_by_tone_tool, _rank_templates_by_emotion_tool],
    )


ToneDiscoverySubagent = create_tone_discovery_subagent()
