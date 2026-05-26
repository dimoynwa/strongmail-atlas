from unittest.mock import MagicMock, patch

import pytest

from template_assistant.agent import build_context_greeting
from template_assistant.services import working_copy_key
from template_assistant.subagents.resolution_subagent import resolve_full_template, resolve_key
from template_assistant.subagents.tone_evaluation_subagent import evaluate_tone
from template_assistant.subagents.tone_suggestion_subagent import (
    apply_tone_suggestions,
    finalize_rewrites,
    suggest_tone_rewrite,
    undo_tone_suggestions,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy, reset_full_working_copy
from template_assistant.tests.test_resolution_subagent import _seed_template
from template_assistant.tone_profiles import GOEMOTIONS_LABELS
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeToolState:
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value


@dataclass
class FakeToolContext:
    state: FakeToolState


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

    tone_bearing = {
        "PARAGRAPH_1": "Welcome to our service, we are glad you joined us today.",
        "PARAGRAPH_2": "Your account is ready and waiting for you to explore.",
    }

    with patch("template_assistant.subagents.tone_suggestion_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=[{"label": "joy", "score": 0.5}])
        tool_result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)

    fin_ctx = FakeToolContext(
        state=FakeToolState(
            {
                **session_state,
                "eligible_keys": tone_bearing,
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    fin_result = await finalize_rewrites(
        [
            {
                "key": "PARAGRAPH_1",
                "new_value": "Welcome to our service, we are delighted you joined us today.",
            }
        ],
        fin_ctx,  # type: ignore[arg-type]
    )
    suggestions = fin_result["suggestions"]
    assert suggestions

    suggestion_payload = [
        {
            "key": item["key"],
            "current_value": tone_bearing[item["key"]],
            "suggested_value": item["new_value"],
            "predicted_delta": {},
            "suggestion_id": tool_result["suggestion_id"],
        }
        for item in suggestions
    ]
    session_state["suggestion_id"] = tool_result["suggestion_id"]
    await apply_tone_suggestions(suggestion_payload, session_state)
    wc = await get_working_copy(session_state)
    assert wc[suggestions[0]["key"]] == suggestions[0]["new_value"]

    paragraph_1_key = suggestions[0]["key"]
    await undo_tone_suggestions([paragraph_1_key], session_state)
    wc_after_undo = await get_working_copy(session_state)
    assert paragraph_1_key not in wc_after_undo or wc_after_undo[paragraph_1_key] != suggestions[0]["new_value"]

    remaining = await get_working_copy(session_state)
    assert isinstance(remaining, dict)

    preview = await resolve_full_template(session_state)
    assert "```html" in preview

    await reset_full_working_copy(session_state)
    assert await get_working_copy(session_state) == {}

    preview_after_reset = await resolve_full_template(session_state)
    assert "Welcome to our service" in preview_after_reset


@pytest.mark.asyncio
async def test_second_suggest_before_undo_shows_warning(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##PARAGRAPH_1##</p>",
        kv_pairs={
            "PARAGRAPH_1": "Welcome to our service, we are glad you joined us today.",
        },
    )
    tone_bearing = {
        "PARAGRAPH_1": "Welcome to our service, we are glad you joined us today.",
    }
    with patch("template_assistant.subagents.tone_suggestion_subagent.get_classifier") as mock_get:
        mock_get.return_value = MagicMock(return_value=[{"label": "joy", "score": 0.5}])
        first = await suggest_tone_rewrite("warmer", tone_bearing, session_state)
        second = await suggest_tone_rewrite("warmer", tone_bearing, session_state)
    assert first["snapshot_overwritten"] is False
    assert second["snapshot_overwritten"] is True
    from template_assistant.subagents.tone_suggestion_subagent import _SNAPSHOT_OVERWRITE_WARNING

    assert "undo snapshot from your previous suggestion batch" in _SNAPSHOT_OVERWRITE_WARNING


@pytest.mark.asyncio
async def test_manual_edit_then_suggest_excludes_edited_key(
    db_pool, redis_client, session_state
):
    from template_assistant.subagents.tone_suggestion_subagent import load_eligible_keys
    from template_assistant.subagents.working_copy_subagent import set_working_copy_value

    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##PARAGRAPH_1## ##PARAGRAPH_2##</p>",
        kv_pairs={
            "PARAGRAPH_1": "Welcome to our service, we are glad you joined us today.",
            "PARAGRAPH_2": "Your account is ready and waiting for you to explore.",
        },
    )
    await set_working_copy_value(
        "PARAGRAPH_1",
        "https://example.com/a-very-long-path-that-is-not-short",
        session_state,
    )
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert "PARAGRAPH_1" not in result["eligible_keys"]
    assert "PARAGRAPH_2" in result["eligible_keys"]


@pytest.mark.asyncio
async def test_db_failure_during_load_eligible_keys_surfaces_message(session_state):
    from template_assistant.subagents.tone_suggestion_subagent import load_eligible_keys

    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_pool",
        side_effect=RuntimeError("database unreachable"),
    ):
        result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert "error" in result
    assert isinstance(result["message"], str)
