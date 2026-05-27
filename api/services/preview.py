from __future__ import annotations

from typing import Any

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.resolver import resolve_body
from template_assistant.context import build_resolution_context, validate_session_context
from template_assistant.services import fetch_template_bodies, map_unresolvable_reason
from template_assistant.subagents.working_copy_subagent import get_working_copy

from api.helpers import get_resolution_graph

_HIGHLIGHT_SPAN = (
    '<span style="border-left:2px solid #22c55e;padding-left:6px;color:#166534">{value}</span>'
)


def _apply_highlights(resolved: str, overrides: dict[str, str]) -> str:
    highlighted = resolved
    for value in overrides.values():
        if value and value in highlighted:
            highlighted = highlighted.replace(value, _HIGHLIGHT_SPAN.format(value=value))
    return highlighted


async def build_preview(
    session_state: dict[str, Any],
    *,
    highlight_modified: bool = True,
) -> dict[str, Any]:
    session_context = validate_session_context(session_state)
    pool = get_pool()
    redis_client = get_redis()
    graph = await get_resolution_graph(session_state)
    html_body, text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    context = build_resolution_context(session_context)
    accumulated_keys: set[str] = set()

    html_result = await resolve_body(
        pool,
        redis_client,
        graph,
        html_body,
        context,
        session_context.session_id,
        session_context.template_name,
        accumulated_keys=accumulated_keys,
    )
    text_result = None
    if text_body:
        text_result = await resolve_body(
            pool,
            redis_client,
            graph,
            text_body,
            context,
            session_context.session_id,
            session_context.template_name,
            accumulated_keys=accumulated_keys,
        )

    overrides = await get_working_copy(session_state)
    evaluated_from = "working_copy" if overrides else "graph"

    resolved_html = html_result.resolved_body
    resolved_text = text_result.resolved_body if text_result else ""
    if highlight_modified and overrides:
        resolved_html = _apply_highlights(resolved_html, overrides)
        if resolved_text:
            resolved_text = _apply_highlights(resolved_text, overrides)

    unresolvable = html_result.unresolvable
    if text_result:
        seen = {entry.key for entry in unresolvable}
        for entry in text_result.unresolvable:
            if entry.key not in seen:
                unresolvable.append(entry)
                seen.add(entry.key)

    unresolvable_keys = [
        {"key": entry.key, "reason": map_unresolvable_reason(entry.reason)}
        for entry in unresolvable
    ]
    total_placeholders = len(graph)
    unresolvable_count = len(unresolvable_keys)

    return {
        "resolved_html": resolved_html,
        "resolved_text": resolved_text,
        "unresolvable_keys": unresolvable_keys,
        "total_placeholders": total_placeholders,
        "resolved_count": max(total_placeholders - unresolvable_count, 0),
        "unresolvable_count": unresolvable_count,
        "evaluated_from": evaluated_from,
    }
