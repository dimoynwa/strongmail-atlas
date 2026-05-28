"""Tests for working-copy init and build_tone_eligible_keys (spec 014)."""

from __future__ import annotations

import pytest

from template_assistant.context import validate_session_context
from template_assistant.services import (
    build_tone_eligible_keys,
    select_reachability_body,
    working_copy_key,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy, set_working_copy_value
from template_assistant.tests.test_resolution_subagent import _seed_template

LANG = "EN-US"
BRAND = "BRANDX"


def _eligible_key(name: str) -> str:
    return f"{LANG}.{name}"


def _long_text(suffix: str = "") -> str:
    return f"This is a long enough placeholder value for tone rewrite testing.{suffix}"


def test_select_reachability_body_prefers_text():
    assert select_reachability_body("<html>##A##</html>", "Plain ##B##") == "Plain ##B##"


def test_select_reachability_body_falls_back_to_html():
    assert select_reachability_body("<html>##A##</html>", "") == "<html>##A##</html>"
    assert select_reachability_body("<html>##A##</html>", "   ") == "<html>##A##</html>"


def test_select_reachability_body_empty():
    assert select_reachability_body("", "") == ""


@pytest.mark.asyncio
async def test_build_tone_eligible_keys_from_text_body(db_pool, redis_client, session_state):
    used_key = _eligible_key("PARAGRAPH_1")
    html_only_key = _eligible_key("HTML_ONLY")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{html_only_key}##</p>",
        text=f"##{used_key}##",
        kv_pairs={
            used_key: _long_text(),
            html_only_key: _long_text(" HTML only."),
        },
    )

    session_context = validate_session_context(session_state)
    eligible = await build_tone_eligible_keys(session_context)

    assert used_key in eligible
    assert html_only_key not in eligible
    assert eligible[used_key] == _long_text()


@pytest.mark.asyncio
async def test_build_tone_eligible_keys_from_html_when_text_blank(
    db_pool, redis_client, session_state
):
    used_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{used_key}##</p>",
        text="",
        kv_pairs={used_key: _long_text()},
    )

    session_context = validate_session_context(session_state)
    eligible = await build_tone_eligible_keys(session_context)

    assert used_key in eligible


@pytest.mark.asyncio
async def test_build_tone_eligible_keys_empty_bodies(db_pool, redis_client, session_state):
    await _seed_template(db_pool, "TestTemplate", html="", text="")

    session_context = validate_session_context(session_state)
    eligible = await build_tone_eligible_keys(session_context)

    assert eligible == {}


@pytest.mark.asyncio
async def test_build_tone_eligible_keys_stores_empty_for_unresolved(
    db_pool, redis_client, session_state
):
    used_key = _eligible_key("PARAGRAPH_1")
    missing_key = _eligible_key("MISSING_REF")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="",
        text=f"##{used_key}## and ##{missing_key}##",
        kv_pairs={
            used_key: _long_text(),
        },
    )

    session_context = validate_session_context(session_state)
    eligible = await build_tone_eligible_keys(session_context)

    assert used_key in eligible
    assert missing_key in eligible
    assert eligible[missing_key] == ""


@pytest.mark.asyncio
async def test_build_tone_eligible_keys_includes_html_only_unresolvable(
    db_pool, redis_client, session_state
):
    text_key = _eligible_key("PARAGRAPH_1")
    html_only_missing = _eligible_key("HTML_ONLY_MISSING")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{html_only_missing}##</p>",
        text=f"##{text_key}##",
        kv_pairs={text_key: _long_text()},
    )

    session_context = validate_session_context(session_state)
    eligible = await build_tone_eligible_keys(session_context)

    assert text_key in eligible
    assert html_only_missing in eligible
    assert eligible[html_only_missing] == ""


@pytest.mark.asyncio
async def test_init_writes_eligible_keys_to_redis(db_pool, redis_client, session_state):
    used_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{used_key}##</p>",
        kv_pairs={used_key: _long_text()},
    )

    session_context = validate_session_context(session_state)
    eligible = await build_tone_eligible_keys(session_context)
    wc_key = working_copy_key(session_context)

    async with redis_client.pipeline(transaction=True) as pipe:
        for key, value in eligible.items():
            pipe.hset(wc_key, key, value)
        await pipe.execute()

    stored = await redis_client.hgetall(wc_key)
    assert stored[used_key] == _long_text()


@pytest.mark.asyncio
async def test_init_idempotent_when_redis_has_entries(db_pool, redis_client, session_state):
    used_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{used_key}##</p>",
        kv_pairs={used_key: _long_text()},
    )
    await set_working_copy_value(used_key, "User override value here.", session_state)

    session_context = validate_session_context(session_state)
    tone_count = len(await build_tone_eligible_keys(session_context))
    existing = await get_working_copy(session_state)

    assert tone_count >= 1
    assert existing == {used_key: "User override value here."}
    assert len(existing) == 1


@pytest.mark.asyncio
async def test_build_tone_eligible_keys_matches_reachable_eligible(
    db_pool, redis_client, session_state
):
    from template_assistant.subagents.tone_suggestion_subagent import _build_reachable_eligible
    from shared.resolution.graph_builder import build_resolution_graph

    used_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{used_key}##</p>",
        kv_pairs={used_key: _long_text()},
    )

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    eligible_via_helper = await build_tone_eligible_keys(session_context, graph=graph)
    eligible_via_subagent, _ = await _build_reachable_eligible(
        graph, None, session_context, session_state
    )

    assert set(eligible_via_helper.keys()) == set(eligible_via_subagent.keys())
