from unittest.mock import MagicMock, patch

import pytest

from template_assistant.agent import build_context_greeting
from template_assistant.services import working_copy_key
from template_assistant.subagents.resolution_subagent import resolve_full_template, resolve_key
from template_assistant.subagents.tone_evaluation_subagent import evaluate_tone
from template_assistant.subagents.tone_suggestion_subagent import (
    apply_tone_suggestions,
    set_rewrite_fn,
    suggest_tone_rewrites,
    undo_tone_suggestions,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy, reset_full_working_copy
from template_assistant.tests.test_resolution_subagent import _seed_template
from template_assistant.tone_profiles import GOEMOTIONS_LABELS


@pytest.fixture(autouse=True)
def reset_rewrite_fn():
    set_rewrite_fn(None)
    yield
    set_rewrite_fn(None)


@pytest.mark.asyncio
async def test_e2e_happy_path(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##PARAGRAPH_1##</p><p>##PARAGRAPH_2##</p>",
        kv_pairs={
            "PARAGRAPH_1": "Welcome to our service, we are glad you joined us today.",
            "PARAGRAPH_2": "Your account is ready and waiting for you to explore.",
        },
    )

    greeting = build_context_greeting(session_state)
    assert "TestTemplate" in greeting
    assert "EN-US" in greeting
    assert "BRANDX" in greeting

    resolved = await resolve_key("PARAGRAPH_1", session_state)
    assert "Welcome to our service" in resolved["value"]

    mock_scores = [{"label": label, "score": 0.04} for label in sorted(GOEMOTIONS_LABELS)]
    with patch("template_assistant.subagents.tone_evaluation_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=mock_scores)
        tone = await evaluate_tone(session_state)
    assert len(tone.scores) == 28

    async def rewrite(_key, current, _profile, _ctx):
        return current.replace("glad", "delighted")

    set_rewrite_fn(rewrite)
    with patch("template_assistant.subagents.tone_suggestion_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=[{"label": "joy", "score": 0.5}])
        suggestions = await suggest_tone_rewrites("warmer", session_state)
    assert suggestions

    suggestion_payload = [
        {
            "key": s.key,
            "current_value": s.current_value,
            "suggested_value": s.suggested_value,
            "predicted_delta": s.predicted_delta,
        }
        for s in suggestions
    ]
    await apply_tone_suggestions(suggestion_payload, session_state)
    wc = await get_working_copy(session_state)
    assert wc[suggestions[0].key] == suggestions[0].suggested_value

    paragraph_1_key = suggestions[0].key
    await undo_tone_suggestions([paragraph_1_key], session_state)
    wc_after_undo = await get_working_copy(session_state)
    assert paragraph_1_key not in wc_after_undo or wc_after_undo[paragraph_1_key] != suggestions[0].suggested_value

    remaining = await get_working_copy(session_state)
    assert isinstance(remaining, dict)

    preview = await resolve_full_template(session_state)
    assert "```html" in preview

    await reset_full_working_copy(session_state)
    assert await get_working_copy(session_state) == {}

    preview_after_reset = await resolve_full_template(session_state)
    assert "Welcome to our service" in preview_after_reset
