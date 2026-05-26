"""Integration tests for tone suggestion subagent tools (spec 009)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from template_assistant.context import (
    MissingClassificationError,
    SessionContextMissingError,
    SuggestionIdMismatchError,
    validate_session_context,
)
from template_assistant.services import SNAPSHOT_NONE_SENTINEL, resolve_template, snapshot_key, working_copy_key
from template_assistant.subagents import tone_suggestion_subagent as tss
from template_assistant.subagents.tone_suggestion_subagent import (
    KeyNotInGraphError,
    _apply_structural_heuristics,
    _apply_tone_suggestions_tool,
    _build_llm_prompt,
    _build_reachable_eligible,
    _classify_keys_tool,
    _suggest_tone_rewrites_tool,
    _undo_tone_suggestions_tool,
    apply_tone_suggestions,
    capture_snapshot,
    classify_keys,
    finalize_rewrites,
    is_eligible_for_rewrite,
    load_eligible_keys,
    suggest_tone_rewrite,
    undo_tone_suggestions,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy, set_working_copy_value
from template_assistant.tests.test_resolution_subagent import _seed_template
from shared.resolution.graph_builder import build_resolution_graph


@dataclass
class FakeToolState:
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        return self.data.pop(key, default)


@dataclass
class FakeToolContext:
    state: FakeToolState


def _long_text(suffix: str = "") -> str:
    return (
        "We are delighted to welcome you to our platform and hope you enjoy "
        f"everything we have prepared for you today.{suffix}"
    )


def _classifier_patch():
    return patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    )


# --- eligibility helpers (unchanged behaviour) ---


def test_ineligible_suffixes():
    assert is_eligible_for_rewrite("LOGO_URL", "https://example.com/logo.png") is False
    assert is_eligible_for_rewrite("BG_COLOR", "#FFFFFF background color value") is False
    assert is_eligible_for_rewrite("USER_ID", "123456789012345678901") is False


def test_ineligible_http_value():
    assert is_eligible_for_rewrite("LINK", "https://example.com/path") is False


def test_ineligible_short_value():
    assert is_eligible_for_rewrite("TITLE", "Short title") is False


def test_eligible_long_natural_language():
    assert is_eligible_for_rewrite(
        "PARAGRAPH_1",
        "We are delighted to welcome you to our platform today.",
    )


# --- load_eligible_keys ---


@pytest.mark.asyncio
async def test_load_eligible_keys_success(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert "eligible_keys" in result
    assert result["total"] > 0
    assert ctx.state.data.get("eligible_keys")


@pytest.mark.asyncio
async def test_load_eligible_keys_cache_hit_skips_db(db_pool, redis_client, session_state):
    cached = {"GREETING": _long_text()}
    ctx = FakeToolContext(
        state=FakeToolState({**session_state, "eligible_keys": cached})
    )
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.build_resolution_graph"
    ) as mock_build:
        result = await load_eligible_keys(False, ctx)  # type: ignore[arg-type]
        mock_build.assert_not_called()
    assert result["eligible_keys"] == cached


@pytest.mark.asyncio
async def test_load_eligible_keys_force_reload_bypasses_cache(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    ctx = FakeToolContext(
        state=FakeToolState({**session_state, "eligible_keys": {"STALE": "old value long enough."}})
    )
    result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert "STALE" not in result["eligible_keys"]
    assert "GREETING" in result["eligible_keys"]


@pytest.mark.asyncio
async def test_load_eligible_keys_db_failure_returns_error_dict(session_state):
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_pool",
        side_effect=RuntimeError("DB unavailable"),
    ):
        result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert isinstance(result.get("error"), str)
    assert isinstance(result.get("message"), str)


# --- finalize_rewrites ---


@pytest.mark.asyncio
async def test_finalize_rewrites_accepts_valid_keys(session_state):
    state = {
        **session_state,
        "eligible_keys": {"GREETING": _long_text()},
        "suggestion_id": "batch-001",
    }
    ctx = FakeToolContext(state=FakeToolState(state))
    rewrites = [{"key": "GREETING", "new_value": _long_text(" updated")}]
    result = await finalize_rewrites(rewrites, ctx)  # type: ignore[arg-type]
    assert result["accepted"] == 1
    suggestions = ctx.state.data["suggestions"]
    assert suggestions[0]["old_value"] == _long_text()
    assert suggestions[0]["new_value"] == _long_text(" updated")
    assert suggestions[0]["suggestion_id"] == "batch-001"


@pytest.mark.asyncio
async def test_finalize_rewrites_discards_hallucinated_keys(session_state):
    state = {
        **session_state,
        "eligible_keys": {"GREETING": _long_text()},
        "suggestion_id": "batch-001",
    }
    ctx = FakeToolContext(state=FakeToolState(state))
    rewrites = [
        {"key": "GREETING", "new_value": _long_text(" ok")},
        {"key": "PHANTOM", "new_value": _long_text(" bad")},
    ]
    result = await finalize_rewrites(rewrites, ctx)  # type: ignore[arg-type]
    assert result["accepted"] == 1
    assert len(ctx.state.data["suggestions"]) == 1
    assert "discarded_keys" in ctx.state.data


@pytest.mark.asyncio
async def test_finalize_rewrites_filters_unchanged_values(session_state):
    current = _long_text()
    state = {
        **session_state,
        "eligible_keys": {"GREETING": current},
        "suggestion_id": "batch-001",
    }
    ctx = FakeToolContext(state=FakeToolState(state))
    rewrites = [{"key": "GREETING", "new_value": current}]
    result = await finalize_rewrites(rewrites, ctx)  # type: ignore[arg-type]
    assert result["accepted"] == 0
    assert ctx.state.data["suggestions"] == []


@pytest.mark.asyncio
async def test_finalize_rewrites_malformed_json(session_state):
    state = {
        **session_state,
        "eligible_keys": {"GREETING": _long_text()},
        "suggestion_id": "batch-001",
    }
    ctx = FakeToolContext(state=FakeToolState(state))
    result = await finalize_rewrites("{not valid json", ctx)  # type: ignore[arg-type]
    assert result["error"] == "parse_error"
    assert "message" in result


# --- snapshot lifecycle ---


@pytest.mark.asyncio
async def test_capture_snapshot_from_working_copy(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "Graph greeting value here."},
    )
    await redis_client.hset(
        working_copy_key(validate_session_context(session_state)),
        "GREETING",
        "Working copy greeting value.",
    )
    ctx = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, ctx.template_name)
    await capture_snapshot(["GREETING"], ctx, redis_client, graph)
    snap = await redis_client.hgetall(snapshot_key(ctx))
    assert snap["GREETING"] == "Working copy greeting value."


@pytest.mark.asyncio
async def test_suggest_tone_rewrite_snapshot_saved_before_prompt(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    tone_bearing = {"GREETING": _long_text()}
    with _classifier_patch():
        result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)
    assert result["snapshot_saved"] is True
    ctx = validate_session_context(session_state)
    snap = await redis_client.hgetall(snapshot_key(ctx))
    assert snap
    assert "rewrite_prompt" in result


@pytest.mark.asyncio
async def test_suggest_tone_rewrite_snapshot_overwritten_flag(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    ctx = validate_session_context(session_state)
    await redis_client.hset(snapshot_key(ctx), "GREETING", "existing snapshot value")
    tone_bearing = {"GREETING": _long_text()}
    with _classifier_patch():
        result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)
    assert result["snapshot_overwritten"] is True


@pytest.mark.asyncio
async def test_apply_does_not_call_capture_snapshot(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": _long_text()},
    )
    session_state["suggestion_id"] = "batch-001"
    suggestions = [
        {
            "key": "GREETING",
            "old_value": _long_text(),
            "new_value": _long_text(" applied"),
            "suggestion_id": "batch-001",
        }
    ]
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.capture_snapshot"
    ) as mock_capture:
        await apply_tone_suggestions(suggestions, session_state)
        mock_capture.assert_not_called()


@pytest.mark.asyncio
async def test_undo_full_clears_snapshot_hash(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": _long_text()},
    )
    ctx = validate_session_context(session_state)
    await redis_client.hset(snapshot_key(ctx), "GREETING", _long_text())
    await redis_client.hset(working_copy_key(ctx), "GREETING", _long_text(" changed"))
    result = await undo_tone_suggestions(None, session_state)
    assert result["snapshot_cleared"] is True
    assert not await redis_client.exists(snapshot_key(ctx))


@pytest.mark.asyncio
async def test_undo_partial_leaves_snapshot_hash(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING## ##BODY##",
        kv_pairs={"GREETING": _long_text(" g"), "BODY": _long_text(" b")},
    )
    ctx = validate_session_context(session_state)
    await redis_client.hset(snapshot_key(ctx), "GREETING", _long_text(" g"))
    await redis_client.hset(snapshot_key(ctx), "BODY", _long_text(" b"))
    result = await undo_tone_suggestions(["GREETING"], session_state)
    assert result["snapshot_cleared"] is False
    assert await redis_client.exists(snapshot_key(ctx))


@pytest.mark.asyncio
async def test_undo_no_snapshot_returns_gracefully(db_pool, redis_client, session_state):
    result = await undo_tone_suggestions(None, session_state)
    assert result["restored"] == 0
    assert result["snapshot_cleared"] is False
    assert "message" in result


# --- classification and suggest tool ---


@pytest.mark.asyncio
async def test_suggest_tone_rewrite_raises_on_missing_tone_bearing_keys(
    db_pool, redis_client, session_state
):
    with pytest.raises(MissingClassificationError):
        await suggest_tone_rewrite("warmer", None, session_state)


@pytest.mark.asyncio
async def test_suggest_tone_rewrite_empty_tone_bearing_keys_returns_message(
    db_pool, redis_client, session_state
):
    result = await suggest_tone_rewrite("warmer", {}, session_state)
    assert result["message"] == "No eligible keys found for tone rewriting."


@pytest.mark.asyncio
async def test_classify_keys_tool_returns_classification_not_writes_state(session_state):
    async def stub_llm(_keys: dict[str, str]) -> dict[str, str]:
        return {"EN.PARAGRAPH_1": "tone"}

    state = FakeToolState(
        {
            **session_state,
            "eligible_keys": {
                "EN.PARAGRAPH_1": _long_text(),
                "EN.LOGO_URL": "https://example.com/logo.png",
            },
        }
    )
    ctx = FakeToolContext(state=state)
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent._llm_classify_keys",
        side_effect=stub_llm,
    ):
        result = await _classify_keys_tool(ctx)  # type: ignore[arg-type]
    assert "tone_bearing" in result
    assert "structural" in result
    assert "tone_bearing_keys" not in state.data
    assert "structural_keys" not in state.data


@pytest.mark.asyncio
async def test_apply_validates_suggestion_id_cross_match(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": _long_text()},
    )
    session_state["suggestion_id"] = "expected-id"
    suggestions = [
        {
            "key": "GREETING",
            "old_value": _long_text(),
            "new_value": _long_text(" new"),
            "suggestion_id": "wrong-id",
        }
    ]
    with pytest.raises(SuggestionIdMismatchError):
        await apply_tone_suggestions(suggestions, session_state)


@pytest.mark.asyncio
async def test_apply_awaits_pool_and_redis(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": _long_text()},
    )
    session_state["suggestion_id"] = "batch-001"
    suggestions = [
        {
            "key": "GREETING",
            "old_value": _long_text(),
            "new_value": _long_text(" applied"),
            "suggestion_id": "batch-001",
        }
    ]
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await _apply_tone_suggestions_tool(suggestions, ctx)  # type: ignore[arg-type]
    assert result["applied"] == 1


@pytest.mark.asyncio
async def test_post_apply_state_keys_are_clean(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    load_ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    loaded = await load_eligible_keys(True, load_ctx)  # type: ignore[arg-type]

    async def classify_stub(_keys: dict[str, str]) -> dict[str, str]:
        return {"GREETING": "tone"}

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent._llm_classify_keys",
        side_effect=classify_stub,
    ):
        classified = await classify_keys(loaded["eligible_keys"], session_state)

    tone_bearing = classified["tone_bearing"]
    with _classifier_patch():
        tool_result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)

    fin_ctx = FakeToolContext(
        state=FakeToolState(
            {
                **session_state,
                "eligible_keys": loaded["eligible_keys"],
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    fin_result = await finalize_rewrites(
        [{"key": "GREETING", "new_value": _long_text(" applied")}],
        fin_ctx,  # type: ignore[arg-type]
    )
    session_state.update(fin_ctx.state.data)
    await apply_tone_suggestions(fin_result["suggestions"], session_state)
    assert "tone_bearing_keys" not in session_state
    assert "structural_keys" not in session_state
    assert "pending_suggest_rewrite" not in session_state


@pytest.mark.asyncio
async def test_suggest_tool_returns_rewrite_prompt(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    with _classifier_patch():
        result = await _suggest_tone_rewrites_tool(
            "warmer", {"GREETING": _long_text()}, ctx
        )  # type: ignore[arg-type]
    assert "rewrite_prompt" in result
    assert "suggestion_id" in result
    assert ctx.state.data.get("suggestion_id") == result["suggestion_id"]
    assert "suggestions" not in result


@pytest.mark.asyncio
async def test_apply_refuses_without_suggestion_id(db_pool, redis_client, session_state):
    suggestions = [{"key": "GREETING", "new_value": _long_text(" x")}]
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await _apply_tone_suggestions_tool(suggestions, ctx)  # type: ignore[arg-type]
    assert "error" in result


@pytest.mark.asyncio
async def test_undo_missing_context():
    with pytest.raises(SessionContextMissingError):
        await undo_tone_suggestions(None, {})


def test_build_llm_prompt_keys_in_reading_order():
    eligible = {
        "EN.GREETING": "Hello there.",
        "EN.PARAGRAPH_1": "First paragraph text here.",
        "EN.CTA": "Click here now.",
    }
    resolved_body = "<p>EN.PARAGRAPH_1 content</p><p>EN.GREETING content</p>"
    prompt = _build_llm_prompt(eligible, "warmer", {"joy": 0.8}, resolved_body)
    paragraph_pos = prompt.index("EN.PARAGRAPH_1")
    greeting_pos = prompt.index("EN.GREETING")
    cta_pos = prompt.index("EN.CTA")
    assert paragraph_pos < greeting_pos < cta_pos


def test_call_batch_llm_deleted():
    assert not hasattr(tss, "_call_batch_llm")
    assert not hasattr(tss, "set_classifier_llm_fn")
    assert not hasattr(tss, "_classifier_llm_fn")


# --- e2e-style integration flows ---


@pytest.mark.asyncio
async def test_manual_edit_then_suggest_excludes_edited_key(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING## ##BODY##</p>",
        kv_pairs={"GREETING": _long_text(" g"), "BODY": _long_text(" b")},
    )
    await set_working_copy_value(
        "GREETING",
        "https://example.com/a-very-long-path-that-is-not-short",
        session_state,
    )
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert "GREETING" not in result["eligible_keys"]
    assert "BODY" in result["eligible_keys"]


@pytest.mark.asyncio
async def test_db_failure_during_load_eligible_keys_surfaces_message(session_state):
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.build_resolution_graph",
        side_effect=ConnectionError("database unreachable"),
    ):
        result = await load_eligible_keys(True, ctx)  # type: ignore[arg-type]
    assert "error" in result
    assert isinstance(result["message"], str)


@pytest.mark.asyncio
async def test_second_suggest_before_undo_shows_warning(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    tone_bearing = {"GREETING": _long_text()}
    with _classifier_patch():
        first = await suggest_tone_rewrite("warmer", tone_bearing, session_state)
        second = await suggest_tone_rewrite("warmer", tone_bearing, session_state)
    assert first["snapshot_overwritten"] is False
    assert second["snapshot_overwritten"] is True
    warning = (
        "undo snapshot from your previous suggestion batch"
    )
    assert warning in tss._SNAPSHOT_OVERWRITE_WARNING


@pytest.mark.asyncio
async def test_e2e_full_flow(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING## ##FOOTER_COPYRIGHT##</p>",
        kv_pairs={
            "GREETING": _long_text(" greeting"),
            "FOOTER_COPYRIGHT": _long_text(" footer"),
        },
    )

    async def classify_stub(_keys: dict[str, str]) -> dict[str, str]:
        return {"GREETING": "tone"}

    load_ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    loaded = await load_eligible_keys(True, load_ctx)  # type: ignore[arg-type]
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent._llm_classify_keys",
        side_effect=classify_stub,
    ):
        classified = await classify_keys(loaded["eligible_keys"], session_state)

    tone_bearing = classified["tone_bearing"]
    with _classifier_patch():
        tool_result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)

    fin_ctx = FakeToolContext(
        state=FakeToolState(
            {
                **session_state,
                "eligible_keys": loaded["eligible_keys"],
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    fin_result = await finalize_rewrites(
        [{"key": "GREETING", "new_value": _long_text(" warmer greeting")}],
        fin_ctx,  # type: ignore[arg-type]
    )
    assert fin_result["suggestions"]
    session_state["suggestion_id"] = tool_result["suggestion_id"]
    session_state["suggestions"] = fin_result["suggestions"]

    apply_ctx = FakeToolContext(state=FakeToolState(session_state))
    apply_result = await _apply_tone_suggestions_tool(
        fin_result["suggestions"],
        apply_ctx,  # type: ignore[arg-type]
    )
    assert apply_result["applied"] == 1

    wc = await get_working_copy(session_state)
    assert wc["GREETING"] == _long_text(" warmer greeting")

    undo_result = await undo_tone_suggestions(["GREETING"], session_state)
    assert undo_result["restored"] == 1

    for item in fin_result["suggestions"]:
        assert not _apply_structural_heuristics(item["key"])
