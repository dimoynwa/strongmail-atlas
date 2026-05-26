import json
import pytest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from template_assistant.context import SessionContextMissingError
from template_assistant.services import SNAPSHOT_NONE_SENTINEL, resolve_template, snapshot_key, working_copy_key
from template_assistant.subagents import tone_suggestion_subagent as tss
from template_assistant.subagents.tone_suggestion_subagent import (
    _apply_structural_heuristics,
    _apply_tone_suggestions_tool,
    _build_llm_prompt,
    _build_reachable_eligible,
    _finalize_suggest_rewrites,
    _populate_eligible_keys,
    _suggest_tone_rewrites_tool,
    apply_tone_suggestions,
    capture_snapshot,
    classify_keys,
    is_eligible_for_rewrite,
    set_classifier_llm_fn,
    suggest_tone_rewrite,
    undo_tone_suggestions,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy, set_working_copy_value
from template_assistant.tests.test_resolution_subagent import _seed_template
from template_assistant.context import validate_session_context
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


@dataclass
class FakeCallbackContext:
    state: FakeToolState


def _long_text(suffix: str = "") -> str:
    return (
        "We are delighted to welcome you to our platform and hope you enjoy "
        f"everything we have prepared for you today.{suffix}"
    )


@pytest.fixture(autouse=True)
def reset_classifier_fn():
    set_classifier_llm_fn(None)
    yield
    set_classifier_llm_fn(None)


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
async def test_capture_snapshot_graph_value_when_not_in_working_copy(
    db_pool, redis_client, session_state
):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "Graph greeting value here."},
    )
    ctx = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, ctx.template_name)
    await capture_snapshot(["GREETING"], ctx, redis_client, graph)
    snap = await redis_client.hgetall(snapshot_key(ctx))
    assert snap["GREETING"] == "Graph greeting value here."


@pytest.mark.asyncio
async def test_capture_snapshot_overwrites_previous(db_pool, redis_client, session_state):
    ctx = validate_session_context(session_state)
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##A## ##B##",
        kv_pairs={"A": "First value long enough.", "B": "Second value long enough."},
    )
    graph = await build_resolution_graph(db_pool, ctx.template_name)
    await capture_snapshot(["A"], ctx, redis_client, graph)
    await capture_snapshot(["B"], ctx, redis_client, graph)
    snap = await redis_client.hgetall(snapshot_key(ctx))
    assert snap == {"B": "Second value long enough."}


@pytest.mark.asyncio
async def test_apply_writes_snapshot_before_working_copy(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "Original greeting message long enough."},
    )
    ctx = validate_session_context(session_state)
    suggestion = {
        "key": "GREETING",
        "current_value": "Original greeting message long enough.",
        "suggested_value": "Updated greeting message long enough.",
        "predicted_delta": {"joy": 0.2},
    }
    await apply_tone_suggestions([suggestion], session_state)
    snap = await redis_client.hgetall(snapshot_key(ctx))
    wc = await redis_client.hgetall(working_copy_key(ctx))
    assert snap["GREETING"] == "Original greeting message long enough."
    assert wc["GREETING"] == "Updated greeting message long enough."


@pytest.mark.asyncio
async def test_undo_restores_snapshot_and_deletes_when_none(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": "Original greeting message long enough."},
    )
    ctx = validate_session_context(session_state)
    await redis_client.hset(snapshot_key(ctx), "GREETING", SNAPSHOT_NONE_SENTINEL)
    await redis_client.hset(working_copy_key(ctx), "GREETING", "Changed greeting message.")
    result = await undo_tone_suggestions(["GREETING"], session_state)
    assert result["restored"] == 1
    assert await redis_client.hget(working_copy_key(ctx), "GREETING") is None


@pytest.mark.asyncio
async def test_undo_all_when_no_snapshot(db_pool, redis_client, session_state):
    result = await undo_tone_suggestions(None, session_state)
    assert "nothing" in result["message"].lower() or "no tone" in result["message"].lower()


@pytest.mark.asyncio
async def test_undo_missing_context():
    with pytest.raises(SessionContextMissingError):
        await undo_tone_suggestions(None, {})


@pytest.mark.asyncio
async def test_suggest_reads_tone_bearing_keys(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING## ##BODY##</p>",
        kv_pairs={
            "GREETING": _long_text(" greeting"),
            "BODY": _long_text(" body"),
        },
    )

    session_state["tone_bearing_keys"] = {"GREETING": _long_text(" greeting")}

    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        result = await _suggest_tone_rewrites_tool("warmer", ctx)  # type: ignore[arg-type]

    assert "rewrite_prompt" in result
    assert result["eligible_keys"] == ["GREETING"]
    assert "suggestions" not in result


@pytest.mark.asyncio
async def test_apply_refuses_without_suggestion_id(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##GREETING##",
        kv_pairs={"GREETING": _long_text()},
    )
    suggestions = [
        {
            "key": "GREETING",
            "current_value": _long_text(),
            "suggested_value": _long_text(" updated"),
            "predicted_delta": {"joy": 0.2},
        }
    ]
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await _apply_tone_suggestions_tool(suggestions, ctx)  # type: ignore[arg-type]
    assert "error" in result
    assert "suggestion_id" in result["message"].lower()


@pytest.mark.asyncio
async def test_e2e_structural_keys_excluded(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING## ##FOOTER_COPYRIGHT##</p>",
        kv_pairs={
            "GREETING": _long_text(" greeting"),
            "FOOTER_COPYRIGHT": _long_text(" footer"),
        },
    )

    async def classify_stub(_prompt: str) -> str:
        return json.dumps([{"key": "GREETING", "role": "tone"}])

    set_classifier_llm_fn(classify_stub)

    session_context = validate_session_context(session_state)
    resolution = await resolve_template(session_context)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    eligible, _ = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )
    classified = await classify_keys(eligible, session_state)
    session_state["tone_bearing_keys"] = classified["tone_bearing"]

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        tool_result = await suggest_tone_rewrite("warmer", session_state)

    assert "rewrite_prompt" in tool_result
    llm_response = json.dumps(
        [{"key": "GREETING", "new_value": _long_text(" warmer")}]
    )
    finalized = _finalize_suggest_rewrites(
        llm_response,
        classified["tone_bearing"],
        tool_result["suggestion_id"],
    )

    for item in finalized["suggestions"]:
        assert not _apply_structural_heuristics(item["key"])


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

    async def classify_stub(_prompt: str) -> str:
        return json.dumps([{"key": "GREETING", "role": "tone"}])

    set_classifier_llm_fn(classify_stub)

    session_context = validate_session_context(session_state)
    resolution = await resolve_template(session_context)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    eligible, _ = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )
    classified = await classify_keys(eligible, session_state)
    session_state["tone_bearing_keys"] = classified["tone_bearing"]

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        tool_result = await suggest_tone_rewrite("warmer", session_state)

    assert "rewrite_prompt" in tool_result
    llm_response = json.dumps(
        [{"key": "GREETING", "new_value": _long_text(" warmer greeting")}]
    )
    suggest_result = _finalize_suggest_rewrites(
        llm_response,
        classified["tone_bearing"],
        tool_result["suggestion_id"],
    )

    assert suggest_result["suggestions"]
    session_state["suggestion_id"] = suggest_result["suggestion_id"]
    session_state["suggestions"] = suggest_result["suggestions"]

    ctx = FakeToolContext(state=FakeToolState(session_state))
    apply_result = await _apply_tone_suggestions_tool(
        suggest_result["suggestions"],
        ctx,  # type: ignore[arg-type]
    )
    assert apply_result["applied"] == 1

    wc = await get_working_copy(session_state)
    assert wc["GREETING"] == _long_text(" warmer greeting")

    undo_result = await undo_tone_suggestions(["GREETING"], session_state)
    assert undo_result["restored"] == 1
    wc_after = await get_working_copy(session_state)
    assert "GREETING" not in wc_after or wc_after["GREETING"] != _long_text(" warmer greeting")


@pytest.mark.asyncio
async def test_callback_populates_eligible_keys(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    ctx = FakeCallbackContext(state=FakeToolState(session_state.copy()))
    await _populate_eligible_keys(ctx)  # type: ignore[arg-type]
    assert ctx.state.data.get("eligible_keys")
    assert isinstance(ctx.state.data["eligible_keys"], dict)
    assert len(ctx.state.data["eligible_keys"]) > 0


@pytest.mark.asyncio
async def test_callback_skips_if_already_populated(db_pool, redis_client, session_state):
    existing = {"GREETING": _long_text()}
    ctx = FakeCallbackContext(
        state=FakeToolState({**session_state, "eligible_keys": existing})
    )
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.build_resolution_graph"
    ) as mock_build:
        await _populate_eligible_keys(ctx)  # type: ignore[arg-type]
        mock_build.assert_not_called()
    assert ctx.state.data["eligible_keys"] == existing


@pytest.mark.asyncio
async def test_callback_returns_none(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    populate_ctx = FakeCallbackContext(state=FakeToolState(session_state.copy()))
    assert await _populate_eligible_keys(populate_ctx) is None  # type: ignore[arg-type]

    skip_ctx = FakeCallbackContext(
        state=FakeToolState(
            {**session_state, "eligible_keys": {"GREETING": _long_text()}}
        )
    )
    assert await _populate_eligible_keys(skip_ctx) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_suggest_errors_without_tone_bearing_keys(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    session_state["eligible_keys"] = {"GREETING": _long_text()}
    result = await suggest_tone_rewrite("warmer", session_state)
    assert result.get("error") == "missing_tone_bearing_keys"
    assert "suggestions" not in result


@pytest.mark.asyncio
async def test_suggest_tool_returns_rewrite_prompt(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={"GREETING": _long_text()},
    )
    session_state["tone_bearing_keys"] = {"GREETING": _long_text()}
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        result = await _suggest_tone_rewrites_tool("warmer", ctx)  # type: ignore[arg-type]

    assert "rewrite_prompt" in result
    assert "KEYS TO REWRITE" in result["rewrite_prompt"]
    assert "eligible_keys" in result
    assert "target_emotions" in result
    assert "baseline_emotions" in result
    assert "suggestion_id" in result
    assert "instruction" in result
    assert "suggestions" not in result


@pytest.mark.asyncio
async def test_suggest_tool_no_eligible_keys(db_pool, redis_client, session_state):
    session_state["tone_bearing_keys"] = {}
    ctx = FakeToolContext(state=FakeToolState(session_state.copy()))
    result = await _suggest_tone_rewrites_tool("warmer", ctx)  # type: ignore[arg-type]
    assert result["message"] == "No eligible keys found for tone rewriting."
    assert "rewrite_prompt" not in result


def test_build_llm_prompt_keys_in_reading_order():
    eligible = {
        "EN.GREETING": "Hello there.",
        "EN.PARAGRAPH_1": "First paragraph text here.",
        "EN.CTA": "Click here now.",
    }
    resolved_body = (
        "<p>EN.PARAGRAPH_1 content</p><p>EN.GREETING content</p>"
    )
    prompt = _build_llm_prompt(eligible, "warmer", {"joy": 0.8}, resolved_body)
    paragraph_pos = prompt.index("EN.PARAGRAPH_1")
    greeting_pos = prompt.index("EN.GREETING")
    cta_pos = prompt.index("EN.CTA")
    assert paragraph_pos < greeting_pos < cta_pos


def test_build_llm_prompt_no_template_context_section():
    prompt = _build_llm_prompt(
        {"EN.SUBJECT": "Hello world today."},
        "warmer",
        {"joy": 0.8},
        "<p>EN.SUBJECT</p>",
    )
    assert "TEMPLATE CONTEXT" not in prompt


def test_call_batch_llm_deleted():
    assert not hasattr(tss, "_call_batch_llm")
    assert not hasattr(tss, "_default_rewrite")
    assert not hasattr(tss, "set_llm_batch_fn")
    assert not hasattr(tss, "set_rewrite_fn")
