import json
from unittest.mock import MagicMock, patch

import pytest

from template_assistant.context import SessionContextMissingError
from template_assistant.subagents.tone_evaluation_subagent import (
    evaluate_tone,
    get_stored_tone_scores,
)
from template_assistant.tests.test_resolution_subagent import _seed_template
from template_assistant.tone_profiles import GOEMOTIONS_LABELS


def _mock_classifier_scores():
    return [{"label": label, "score": 0.04} for label in sorted(GOEMOTIONS_LABELS)]


@pytest.mark.asyncio
async def test_evaluate_tone_returns_28_scores(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<html><body><p>This is a long enough paragraph for tone evaluation purposes today.</p></body></html>",
    )
    with patch("template_assistant.subagents.tone_evaluation_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=_mock_classifier_scores())
        result = await evaluate_tone(session_state)
    assert len(result.scores) == 28
    assert result.low_coverage_warning is False


@pytest.mark.asyncio
async def test_evaluate_tone_uses_working_copy_source(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<html><body><p>This is a long enough paragraph for tone evaluation purposes today.</p></body></html>",
    )
    await redis_client.hset("working-copy:TestTemplate:test-session-001", "NOTE", "override")
    with patch("template_assistant.subagents.tone_evaluation_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=_mock_classifier_scores())
        result = await evaluate_tone(session_state)
    assert result.source == "working_copy"


@pytest.mark.asyncio
async def test_evaluate_tone_low_coverage_warning(db_pool, redis_client, session_state):
    await _seed_template(db_pool, "TestTemplate", html="<p>Hi</p>")
    with patch("template_assistant.subagents.tone_evaluation_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=_mock_classifier_scores())
        result = await evaluate_tone(session_state)
    assert result.low_coverage_warning is True


@pytest.mark.asyncio
async def test_evaluate_tone_empty_html_still_returns_scores(db_pool, redis_client, session_state):
    await _seed_template(db_pool, "TestTemplate", html="<img src='x.png'>")
    with patch("template_assistant.subagents.tone_evaluation_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=_mock_classifier_scores())
        result = await evaluate_tone(session_state)
    assert len(result.scores) == 28


@pytest.mark.asyncio
async def test_evaluate_tone_missing_context():
    with pytest.raises(SessionContextMissingError):
        await evaluate_tone({})


@pytest.mark.asyncio
async def test_get_stored_tone_scores(db_pool, session_state):
    await _seed_template(db_pool, "TestTemplate", html="<p>Body</p>")
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO template_tone_evaluations
                (template_id, model_id, lang_local, param_cust_brand, tones)
            VALUES ('tpl-1', 'goemotions', 'EN-US', 'BRANDX', $1::jsonb)
            """,
            json.dumps({"joy": 0.8, "love": 0.2}),
        )
    scores = await get_stored_tone_scores(session_state)
    assert scores == {"joy": 0.8, "love": 0.2}


@pytest.mark.asyncio
async def test_get_stored_tone_scores_none_when_missing(db_pool, session_state):
    await _seed_template(db_pool, "TestTemplate", html="<p>Body</p>")
    assert await get_stored_tone_scores(session_state) is None


@pytest.mark.asyncio
async def test_get_stored_tone_scores_strips_warning_sentinel(db_pool, session_state):
    await _seed_template(db_pool, "TestTemplate", html="<p>Body</p>")
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO template_tone_evaluations
                (template_id, model_id, lang_local, param_cust_brand, tones)
            VALUES ('tpl-1', 'goemotions', 'EN-US', 'BRANDX', $1::jsonb)
            """,
            json.dumps(
                {
                    "joy": 0.8,
                    "love": 0.2,
                    "_warning": "unresolvable_keys",
                }
            ),
        )
    scores = await get_stored_tone_scores(session_state)
    assert scores == {"joy": 0.8, "love": 0.2}
