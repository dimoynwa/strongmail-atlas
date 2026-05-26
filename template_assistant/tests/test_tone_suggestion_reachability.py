"""Reachability pre-filter tests for tone suggestions (spec 004 T-003, T-004, T-007)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from template_assistant.context import validate_session_context
from template_assistant.services import working_copy_key
from template_assistant.subagents.tone_suggestion_subagent import (
    _build_reachable_eligible,
    finalize_rewrites,
    suggest_tone_rewrite,
)
from template_assistant.tests.test_resolution_subagent import _seed_template
from shared.resolution.graph_builder import build_resolution_graph
from template_assistant.services import resolve_template

LANG = "EN-US"
BRAND = "BRANDX"


def _eligible_key(name: str) -> str:
    return f"{LANG}.{name}"


def _long_text(suffix: str = "") -> str:
    return f"This is a long enough placeholder value for tone rewrite testing.{suffix}"


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

    session_context = validate_session_context(session_state)
    resolution = await resolve_template(session_context)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    eligible, _ = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        tool_result = await suggest_tone_rewrite("warmer", eligible, session_state)

    fin_ctx = FakeToolContext(
        state=FakeToolState(
            {
                **session_state,
                "eligible_keys": eligible,
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    result = await finalize_rewrites(
        [
            {"key": used_key, "new_value": _long_text(" Rewritten.")},
            {"key": orphan_key, "new_value": _long_text(" Should not appear.")},
        ],
        fin_ctx,  # type: ignore[arg-type]
    )

    suggestion_keys = {item["key"] for item in result["suggestions"]}
    assert used_key in suggestion_keys
    assert orphan_key not in suggestion_keys


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

    session_context = validate_session_context(session_state)
    resolution = await resolve_template(session_context)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    eligible, ineligible_keys = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )

    assert key not in eligible
    assert key in ineligible_keys


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

    session_context = validate_session_context(session_state)
    resolution = await resolve_template(session_context)
    graph = await build_resolution_graph(db_pool, session_context.template_name)
    eligible, _ = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        tool_result = await suggest_tone_rewrite("warmer", eligible, session_state)

    fin_ctx = FakeToolContext(
        state=FakeToolState(
            {
                **session_state,
                "eligible_keys": eligible,
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    result = await finalize_rewrites(
        [{"key": greeting_key, "new_value": rewritten_greeting}],
        fin_ctx,  # type: ignore[arg-type]
    )

    suggestion_keys = {item["key"] for item in result["suggestions"]}
    assert greeting_key in suggestion_keys
    assert first_name_key not in suggestion_keys
    greeting = next(item for item in result["suggestions"] if item["key"] == greeting_key)
    assert f"##{first_name_key}##" in greeting["new_value"]
