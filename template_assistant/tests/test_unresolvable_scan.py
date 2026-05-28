"""Tests for shared unresolvable scan helper and preview integration (spec 014)."""

from __future__ import annotations

import pytest

from api.services.preview import build_preview
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import ReasonCode
from template_assistant.context import validate_session_context
from template_assistant.services import scan_template_unresolvables
from template_assistant.subagents.working_copy_subagent import set_working_copy_value
from template_assistant.tests.test_resolution_subagent import _seed_template

LANG = "EN-US"
BRAND = "BRANDX"


def _eligible_key(name: str) -> str:
    return f"{LANG}.{name}"


def _long_text(suffix: str = "") -> str:
    return f"This is a long enough placeholder value for tone rewrite testing.{suffix}"


@pytest.mark.asyncio
async def test_scan_merges_html_and_text_unresolvables(db_pool, redis_client, session_state):
    html_key = _eligible_key("HTML_MISSING")
    text_key = _eligible_key("TEXT_MISSING")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{html_key}##",
        text=f"##{text_key}##",
        kv_pairs={},
    )

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    unresolvables, scan_sources = await scan_template_unresolvables(
        session_context,
        graph=graph,
    )

    keys = {entry.key for entry in unresolvables}
    assert html_key in keys
    assert text_key in keys
    assert scan_sources == ["html", "text"]


@pytest.mark.asyncio
async def test_scan_includes_detail_for_cycle(db_pool, redis_client, session_state):
    key_a = _eligible_key("BLOCK_A")
    key_b = _eligible_key("BLOCK_B")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{key_a}##",
        text="",
        kv_pairs={
            key_a: f"Cycle to ##{key_b}##",
            key_b: f"Back to ##{key_a}##",
        },
    )

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    unresolvables, _ = await scan_template_unresolvables(session_context, graph=graph)

    cycle_entries = [entry for entry in unresolvables if entry.reason == ReasonCode.CYCLE]
    assert cycle_entries
    assert cycle_entries[0].detail


@pytest.mark.asyncio
async def test_preview_unresolvables_match_scan_helper(db_pool, redis_client, session_state):
    html_key = _eligible_key("HTML_MISSING")
    text_key = _eligible_key("TEXT_MISSING")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{html_key}##",
        text=f"##{text_key}##",
        kv_pairs={},
    )

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    scan_entries, scan_sources = await scan_template_unresolvables(
        session_context,
        graph=graph,
    )
    preview = await build_preview(session_state)

    scan_payload = {
        (entry.key, entry.reason.value, entry.detail) for entry in scan_entries
    }
    preview_payload = {
        (entry["key"], entry["reason"], entry["detail"])
        for entry in preview["unresolvable_keys"]
    }
    assert scan_payload == preview_payload
    assert preview["scan_sources"] == scan_sources
    assert preview["tokens_scanned"] == preview["total_placeholders"]
    assert preview["resolved_token_count"] == preview["resolved_count"]


@pytest.mark.asyncio
async def test_preview_scan_respects_working_copy(db_pool, redis_client, session_state):
    key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{key}##",
        kv_pairs={key: _long_text()},
    )
    await set_working_copy_value(key, _long_text(" Override."), session_state)

    preview = await build_preview(session_state)
    assert preview["evaluated_from"] == "working_copy"


@pytest.mark.asyncio
async def test_preview_skips_scan_when_disabled(db_pool, redis_client, session_state):
    html_key = _eligible_key("HTML_MISSING")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{html_key}##",
        kv_pairs={},
    )

    preview = await build_preview(session_state, include_unresolvable_scan=False)
    assert preview["unresolvable_keys"] == []
    assert preview["scan_sources"] == []
    assert preview["tokens_scanned"] == 0
