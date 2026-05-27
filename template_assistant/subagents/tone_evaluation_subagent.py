from __future__ import annotations

import json
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from template_assistant.llm import get_llm_model

from shared.db import get_pool
from template_assistant.context import validate_session_context
from template_assistant.ml.goemotions import get_classifier, scores_from_pipeline_result
from template_assistant.models import ToneEvaluationResult
from template_assistant.services import resolve_template, working_copy_key
from template_assistant.utils.text import extract_plain_text


def normalize_stored_tones(raw: Any) -> dict[str, float] | None:
    """Convert template_tone_evaluations.tones to label→score dict."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    if isinstance(raw, list):
        scores: dict[str, float] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            score = item.get("score")
            if label is not None and score is not None:
                scores[str(label)] = float(score)
        return scores or None
    return None


async def _has_working_copy(session_state: dict) -> bool:
    from shared.redis_client import get_redis

    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    count = await redis_client.hlen(working_copy_key(session_context))
    return count > 0


async def evaluate_tone(session_state: dict) -> ToneEvaluationResult:
    """Resolve template, strip HTML, and score emotional tone with GoEmotions."""
    session_context = validate_session_context(session_state)
    result = await resolve_template(session_context)
    plain_text = extract_plain_text(result.resolved_body)
    low_coverage_warning = len(plain_text) < 50

    if plain_text:
        classifier = get_classifier()
        raw_scores = classifier(plain_text)
        if isinstance(raw_scores, list) and raw_scores and isinstance(raw_scores[0], list):
            scores = scores_from_pipeline_result(raw_scores[0])
        else:
            scores = scores_from_pipeline_result(raw_scores)
    else:
        scores = {label: 0.0 for label in _zero_score_labels()}

    source = "working_copy" if await _has_working_copy(session_state) else "graph"
    return ToneEvaluationResult(
        scores=scores,
        source=source,
        low_coverage_warning=low_coverage_warning,
    )


def _zero_score_labels() -> list[str]:
    from template_assistant.tone_profiles import GOEMOTIONS_LABELS

    return sorted(GOEMOTIONS_LABELS)


async def store_tone_scores(
    scores: dict[str, float], session_state: dict, *, model_id: str = "goemotions"
) -> None:
    """Persist tone scores to template_tone_evaluations for the current template context."""
    session_context = validate_session_context(session_state)
    pool = get_pool()
    tones_json = json.dumps({str(k): float(v) for k, v in scores.items()})
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO template_tone_evaluations
                (template_id, model_id, lang_local, param_cust_brand, tones, evaluated_at)
            SELECT t.id, $2, $3, $4, $5::jsonb, NOW()
            FROM template t
            WHERE t.name = $1
            ON CONFLICT (template_id, model_id, lang_local, param_cust_brand)
            DO UPDATE SET
                tones = EXCLUDED.tones,
                evaluated_at = EXCLUDED.evaluated_at
            """,
            session_context.template_name,
            model_id,
            session_context.lang_local,
            session_context.param_cust_brand,
            tones_json,
        )


async def get_stored_tone_scores(session_state: dict) -> dict[str, float] | None:
    """Read historical tone scores from template_tone_evaluations."""
    session_context = validate_session_context(session_state)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT tte.tones
            FROM template t
            JOIN template_tone_evaluations tte ON tte.template_id = t.id
            WHERE t.name = $1
              AND UPPER(tte.lang_local) = UPPER($2)
              AND UPPER(tte.param_cust_brand) = UPPER($3)
            ORDER BY tte.evaluated_at DESC
            LIMIT 1
            """,
            session_context.template_name,
            session_context.lang_local,
            session_context.param_cust_brand,
        )
    if row is None:
        return None

    return normalize_stored_tones(row["tones"])


async def _evaluate_tone_tool(tool_context: ToolContext) -> dict[str, Any]:
    result = await evaluate_tone(tool_context.state.to_dict())
    return {
        "scores": result.scores,
        "evaluated_at": result.evaluated_at.isoformat(),
        "source": result.source,
        "low_coverage_warning": result.low_coverage_warning,
    }


async def _get_stored_tone_scores_tool(tool_context: ToolContext) -> dict[str, float] | None:
    return await get_stored_tone_scores(tool_context.state.to_dict())


async def _store_tone_scores_tool(
    scores: dict[str, float], tool_context: ToolContext
) -> dict[str, bool]:
    await store_tone_scores(scores, tool_context.state.to_dict())
    return {"stored": True}


def create_tone_evaluation_subagent() -> LlmAgent:
    return LlmAgent(
        name="ToneEvaluationSubagent",
        model=get_llm_model("TONE_EVALUATION"),
        description="""
        Evaluates the emotional tone of the loaded template using the GoEmotions
        BERT classifier. Always runs a fresh evaluation against the current
        resolved template state — including any working copy overrides active
        in this session. Can also retrieve previously stored tone scores from
        the database for comparison. Never writes to Redis; persists evaluations
        to PostgreSQL only via store_tone_scores when asked to save scores.
        """,
        instruction="""
        You are the Tone Evaluation Subagent. You score the emotional content
        of the loaded template using GoEmotions, a 28-label BERT classifier.

        ## Evaluation pipeline (always in this order)
        1. Validate SessionContext.
        2. Call resolve_full_template from the shared resolution library to get
           the current resolved HTML — this respects the Redis working copy.
        3. Call extract_plain_text to strip HTML boilerplate using trafilatura.
        4. If the extracted plain text is fewer than 50 characters, set
           low_coverage_warning=True and include a warning in your response.
        5. Pass the plain text to the GoEmotions classifier via get_classifier().
           Use top_k=None to receive all 28 label scores.
        6. Return a ToneEvaluationResult with all scores and the warning flag.

        ## Your tools
        - evaluate_tone: runs the full pipeline above and returns all 28 emotion
          label scores with confidence values for the current template state.
        - get_stored_tone_scores: queries template_tone_evaluations in PostgreSQL
          for the most recent stored scores matching this template, lang_local,
          and param_cust_brand. Returns None when no stored scores exist.
        - store_tone_scores: upserts the provided emotion scores into
          template_tone_evaluations for the current template context.

        ## Behaviour rules
        - Always validate SessionContext as the first action in every tool call.
        - Always run a fresh evaluation — never return stored scores as the
          evaluation result. Stored scores are only for comparison context.
        - Always report scores even when confidence values are low — never
          withhold results due to low absolute confidence.
        - Always evaluate against the current working copy state. If the user
          has made edits in this session, those edits must be reflected in
          the evaluation.
        - Never load or instantiate the GoEmotions pipeline yourself — always
          call get_classifier() from template_assistant.ml.goemotions.
        - When presenting scores to the user, sort by confidence descending
          and highlight the top 5 emotions clearly. Include all 28 only
          if the user explicitly asks for the full breakdown.
        - The GoEmotions model is deterministic — the same resolved text always
          produces the same scores. Make this clear if the user asks why
          scores are identical across two evaluations of unchanged content.
        """,
        tools=[_evaluate_tone_tool, _get_stored_tone_scores_tool, _store_tone_scores_tool],
    )


ToneEvaluationSubagent = create_tone_evaluation_subagent()
