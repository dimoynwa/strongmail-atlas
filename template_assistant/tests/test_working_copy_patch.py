"""Tests for working-copy PATCH key eligibility."""

from __future__ import annotations

import pytest

from template_assistant.context import validate_session_context
from template_assistant.services import (
    is_working_copy_patchable_key,
    working_copy_key,
)
from template_assistant.tests.test_resolution_subagent import _seed_template
from template_assistant.tests.test_working_copy_init import LANG, _long_text

def _eligible_key(name: str) -> str:
    return f"{LANG}.{name}"


@pytest.mark.asyncio
async def test_patchable_when_key_in_graph(db_pool, redis_client, session_state):
    used_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{used_key}##",
        kv_pairs={used_key: _long_text()},
    )
    from shared.resolution.graph_builder import build_resolution_graph

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    assert await is_working_copy_patchable_key(
        used_key,
        graph=graph,
        session_context=session_context,
    )


@pytest.mark.asyncio
async def test_patchable_when_key_only_in_template_body(db_pool, redis_client, session_state):
    missing_key = "AMOUNT"
    used_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{used_key}## paid ##{missing_key}##",
        kv_pairs={used_key: _long_text()},
    )
    from shared.resolution.graph_builder import build_resolution_graph

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    assert missing_key not in graph
    assert await is_working_copy_patchable_key(
        missing_key,
        graph=graph,
        session_context=session_context,
    )


@pytest.mark.asyncio
async def test_patchable_when_key_in_working_copy_only(db_pool, redis_client, session_state):
    missing_key = "CAMPAIGN_NAME"
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{_eligible_key('PARAGRAPH_1')}##",
        kv_pairs={},
    )

    from shared.resolution.graph_builder import build_resolution_graph

    session_context = validate_session_context(session_state)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    wc_key = working_copy_key(session_context)
    await redis_client.hset(wc_key, missing_key, "")

    assert missing_key not in graph
    assert await is_working_copy_patchable_key(
        missing_key,
        graph=graph,
        session_context=session_context,
    )
