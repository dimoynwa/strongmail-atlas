"""Tests for resolved_keys reachability tracking (spec 004 T-001, T-002, T-006)."""

import types

import pytest

from shared.resolution.resolver import resolve_body
from template_assistant.context import SessionContext
from template_assistant.services import resolve_template
from template_assistant.tests.test_resolution_subagent import _seed_template


@pytest.mark.asyncio
async def test_resolved_keys_populated_correctly(db_pool, redis_client):
    """T-001: direct, transitive, and unreachable keys."""
    graph = types.MappingProxyType(
        {
            "GREETING": "Hi, my name is ##NAME##",
            "NAME": "Alice",
            "ORPHAN": "This key is never referenced in the template body.",
        }
    )
    body = "##GREETING##"

    res = await resolve_body(db_pool, redis_client, graph, body, {}, "s1", "T1")

    assert res.resolved_keys
    assert "GREETING" in res.resolved_keys
    assert "NAME" in res.resolved_keys
    assert "ORPHAN" not in res.resolved_keys


@pytest.mark.asyncio
async def test_resolved_keys_union_across_html_and_text(db_pool, redis_client, session_state):
    """T-002: HTML and text bodies contribute to the same resolved_keys set."""
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##HTML_KEY##",
        text="Plain ##TEXT_KEY##",
        kv_pairs={
            "HTML_KEY": "HTML body value long enough for testing.",
            "TEXT_KEY": "Text body value long enough for testing.",
        },
    )
    session_context = SessionContext(
        template_name="TestTemplate",
        lang_local=session_state["lang_local"],
        param_cust_brand=session_state["param_cust_brand"],
        session_id=session_state["session_id"],
    )

    result = await resolve_template(session_context)

    assert "HTML_KEY" in result.resolved_keys
    assert "TEXT_KEY" in result.resolved_keys


@pytest.mark.asyncio
async def test_resolved_keys_namespace_expansion_is_canonical(db_pool, redis_client, session_state):
    """T-006: LANG_LOCAL tokens expand to canonical session-scoped keys."""
    paragraph_key = "EN-US.PARAGRAPH_1"
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##LANG_LOCAL.PARAGRAPH_1##",
        kv_pairs={paragraph_key: "Paragraph value long enough for tone rewrite testing."},
    )
    session_context = SessionContext(
        template_name="TestTemplate",
        lang_local="EN-US",
        param_cust_brand=session_state["param_cust_brand"],
        session_id=session_state["session_id"],
    )

    result = await resolve_template(session_context)

    assert paragraph_key in result.resolved_keys
    assert "LANG_LOCAL.PARAGRAPH_1" not in result.resolved_keys


@pytest.mark.asyncio
async def test_resolved_keys_namespace_session_scoped(db_pool, redis_client, session_state):
    """T-006: different lang_local values produce different resolved_keys."""
    await _seed_template(
        db_pool,
        "TestTemplate",
        html="##LANG_LOCAL.PARAGRAPH_1##",
        kv_pairs={
            "EN-US.PARAGRAPH_1": "English paragraph value long enough for testing.",
            "DE.PARAGRAPH_1": "German paragraph value long enough for testing.",
        },
    )

    en_result = await resolve_template(
        SessionContext(
            template_name="TestTemplate",
            lang_local="EN-US",
            param_cust_brand=session_state["param_cust_brand"],
            session_id=session_state["session_id"],
        )
    )
    de_result = await resolve_template(
        SessionContext(
            template_name="TestTemplate",
            lang_local="DE",
            param_cust_brand=session_state["param_cust_brand"],
            session_id=session_state["session_id"],
        )
    )

    assert "EN-US.PARAGRAPH_1" in en_result.resolved_keys
    assert "DE.PARAGRAPH_1" not in en_result.resolved_keys
    assert "DE.PARAGRAPH_1" in de_result.resolved_keys
    assert "EN-US.PARAGRAPH_1" not in de_result.resolved_keys
