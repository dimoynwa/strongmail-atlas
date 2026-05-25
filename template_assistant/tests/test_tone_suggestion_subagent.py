import pytest
from unittest.mock import patch

from template_assistant.context import SessionContextMissingError
from template_assistant.services import SNAPSHOT_NONE_SENTINEL, snapshot_key, working_copy_key
from template_assistant.subagents.tone_suggestion_subagent import (
    apply_tone_suggestions,
    capture_snapshot,
    is_eligible_for_rewrite,
    set_rewrite_fn,
    suggest_tone_rewrites,
    undo_tone_suggestions,
)
from template_assistant.subagents.working_copy_subagent import set_working_copy_value
from template_assistant.tests.test_resolution_subagent import _seed_template
from template_assistant.context import validate_session_context
from shared.resolution.graph_builder import build_resolution_graph


@pytest.fixture(autouse=True)
def reset_rewrite_fn():
    set_rewrite_fn(None)
    yield
    set_rewrite_fn(None)


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
async def test_suggest_tone_rewrites(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="<p>##GREETING##</p>",
        kv_pairs={
            "GREETING": "We hope you enjoy using our service every day.",
            "LOGO_URL": "https://example.com/logo.png",
        },
    )

    async def rewrite(_key, current, _profile, _ctx):
        return current.replace("enjoy", "love")

    set_rewrite_fn(rewrite)
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        suggestions = await suggest_tone_rewrites("warmer", session_state)

    assert len(suggestions) == 1
    assert suggestions[0].key == "GREETING"
    assert "love" in suggestions[0].suggested_value


@pytest.mark.asyncio
async def test_suggest_tone_rewrites_empty_when_no_eligible(db_pool, redis_client, session_state):
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##LOGO_URL##",
        kv_pairs={"LOGO_URL": "https://example.com/logo.png"},
    )
    suggestions = await suggest_tone_rewrites("warmer", session_state)
    assert suggestions == []


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
