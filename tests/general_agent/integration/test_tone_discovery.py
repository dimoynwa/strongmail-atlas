import json

import pytest

from general_agent.subagents.tone_discovery_subagent import (
    find_templates_by_tone,
    rank_templates_by_emotion,
)
from tests.general_agent.conftest import seed_template


@pytest.mark.asyncio
async def test_find_templates_by_tone_filters_by_min_score(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-urgent",
        template_name="UrgentAlert",
        tones={"urgency": 0.85, "joy": 0.1},
    )
    await seed_template(
        db_pool,
        template_id="tpl-calm",
        template_name="CalmNotice",
        tones={"urgency": 0.2, "caring": 0.7},
    )

    results = await find_templates_by_tone("urgency", min_score=0.7, limit=10)

    assert len(results) == 1
    assert results[0].template_name == "UrgentAlert"
    assert results[0].emotions["urgency"] == 0.85


@pytest.mark.asyncio
async def test_find_templates_by_tone_returns_empty_when_below_threshold(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-low",
        template_name="LowJoy",
        tones={"joy": 0.1},
    )

    results = await find_templates_by_tone("joy", min_score=0.5, limit=10)

    assert results == []


@pytest.mark.asyncio
async def test_parse_pipeline_list_format_tones(db_pool):
    """Production stores tones as [{label, score}, ...] pipeline output."""
    pipeline_tones = [
        {"label": "gratitude", "score": 0.96},
        {"label": "neutral", "score": 0.05},
    ]
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO template (id, name) VALUES ('tpl-pipe', 'PipelineTone')"
        )
        await conn.execute(
            """
            INSERT INTO template_tone_evaluations
                (template_id, lang_local, param_cust_brand, tones)
            VALUES ('tpl-pipe', 'EN', 'SKRILL', $1::jsonb)
            """,
            json.dumps(pipeline_tones),
        )

    results = await rank_templates_by_emotion("gratitude", limit=10)

    assert len(results) == 1
    assert results[0].template_name == "PipelineTone"
    assert results[0].emotions["gratitude"] == pytest.approx(0.96)


@pytest.mark.asyncio
async def test_rank_templates_by_emotion(db_pool):
    await seed_template(
        db_pool,
        template_id="tpl-high",
        template_name="HighAdmiration",
        tones={"admiration": 0.9},
    )
    await seed_template(
        db_pool,
        template_id="tpl-low",
        template_name="LowAdmiration",
        tones={"admiration": 0.3},
    )

    results = await rank_templates_by_emotion("admiration", limit=10)

    assert len(results) == 2
    assert results[0].template_name == "HighAdmiration"
    assert results[1].template_name == "LowAdmiration"
