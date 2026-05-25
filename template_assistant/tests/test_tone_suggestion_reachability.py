"""Reachability pre-filter tests for tone suggestions (spec 004 T-003, T-004, T-007)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from template_assistant.context import validate_session_context
from template_assistant.services import working_copy_key
from template_assistant.subagents.tone_suggestion_subagent import (
    set_llm_batch_fn,
    set_rewrite_fn,
    suggest_tone_rewrite,
    suggest_tone_rewrites,
)
from template_assistant.tests.test_resolution_subagent import _seed_template

LANG = "EN-US"
BRAND = "BRANDX"


@pytest.fixture(autouse=True)
def reset_injected_fns():
    set_rewrite_fn(None)
    set_llm_batch_fn(None)
    yield
    set_rewrite_fn(None)
    set_llm_batch_fn(None)


def _eligible_key(name: str) -> str:
    return f"{LANG}.{name}"


def _long_text(suffix: str = "") -> str:
    return f"This is a long enough placeholder value for tone rewrite testing.{suffix}"


@pytest.mark.asyncio
async def test_unreachable_graph_keys_excluded_from_suggestions(
    db_pool, redis_client, session_state
):
    """T-003: keys in graph but not referenced in template are silently excluded."""
    used_key = _eligible_key("PARAGRAPH_1")
    orphan_key = _eligible_key("ORPHAN_BLOCK")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{used_key}##</p>",
        kv_pairs={
            used_key: _long_text(),
            orphan_key: _long_text(" Orphan content."),
        },
    )

    llm_payload = json.dumps(
        [
            {"key": used_key, "new_value": _long_text(" Rewritten.")},
            {"key": orphan_key, "new_value": _long_text(" Should not appear.")},
        ]
    )

    async def batch_fn(_prompt: str) -> str:
        return llm_payload

    set_llm_batch_fn(batch_fn)
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        result = await suggest_tone_rewrite("warmer", session_state)

    suggestion_keys = {item["key"] for item in result["suggestions"]}
    assert used_key in suggestion_keys
    assert orphan_key not in suggestion_keys
    assert orphan_key not in result["ineligible_keys"]


@pytest.mark.asyncio
async def test_working_copy_value_used_for_eligibility_not_graph_value(
    db_pool, redis_client, session_state
):
    """T-004: working copy URL override excludes key even when graph value is prose."""
    key = _eligible_key("PARAGRAPH_1")
    url_value = "https://example.com/a-very-long-path-that-is-not-short"
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{key}##</p>",
        kv_pairs={key: _long_text()},
    )
    await redis_client.hset(
        working_copy_key(validate_session_context(session_state)),
        key,
        url_value,
    )

    llm_payload = json.dumps([{"key": key, "new_value": _long_text(" Rewritten.")}])

    async def batch_fn(_prompt: str) -> str:
        return llm_payload

    set_llm_batch_fn(batch_fn)
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        result = await suggest_tone_rewrite("warmer", session_state)

    assert key not in {item["key"] for item in result["suggestions"]}
    assert key in result["ineligible_keys"]


@pytest.mark.asyncio
async def test_transitive_prose_eligible_bare_token_filtered(
    db_pool, redis_client, session_state
):
    """T-007: transitive prose keys are eligible; bare token keys are filtered out."""
    greeting_key = _eligible_key("GREETING")
    first_name_key = _eligible_key("FIRST_NAME")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"##{greeting_key}##",
        kv_pairs={
            greeting_key: f"Hi, my name is ##{first_name_key}##",
            first_name_key: "##PARAM_FIRST_NAME##",
        },
    )

    rewritten_greeting = (
        "Hello there, my name is "
        f"##{first_name_key}##"
        " and we are glad to have you here today."
    )

    async def rewrite(key, current, _profile, _ctx):
        if key == greeting_key:
            return rewritten_greeting
        return current

    set_rewrite_fn(rewrite)
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        suggestions = await suggest_tone_rewrites("warmer", session_state)

    suggestion_keys = {item.key for item in suggestions}
    assert greeting_key in suggestion_keys
    assert first_name_key not in suggestion_keys
    greeting = next(item for item in suggestions if item.key == greeting_key)
    assert f"##{first_name_key}##" in greeting.suggested_value
