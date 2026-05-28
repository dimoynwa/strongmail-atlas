from __future__ import annotations

import html
import re
from typing import Any

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.resolver import resolve_body
from template_assistant.context import build_resolution_context, validate_session_context
from template_assistant.services import (
    count_body_tokens,
    fetch_template_bodies,
    scan_template_unresolvables,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy

from api.helpers import get_resolution_graph


def _apply_highlights(resolved: str, overrides: dict[str, str]) -> str:
    highlighted = resolved
    for value in overrides.values():
        if not value:
            continue
        match = re.search(re.escape(value), highlighted)
        if not match:
            continue
        start, end = match.span()
        span = (
            '<span style="border-left:2px solid #22c55e;padding-left:6px;color:#166534">'
            f"{html.escape(value, quote=False)}"
            "</span>"
        )
        highlighted = highlighted[:start] + span + highlighted[end:]
    return highlighted


async def build_preview(
    session_state: dict[str, Any],
    *,
    highlight_modified: bool = True,
    include_unresolvable_scan: bool = True,
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

    scan_sources: list[str] = []
    unresolvable_keys: list[dict[str, str]] = []
    tokens_scanned = 0

    if include_unresolvable_scan:
        unresolvables, scan_sources = await scan_template_unresolvables(
            session_context,
            graph=graph,
        )
        unresolvable_keys = [
            {
                "key": entry.key,
                "reason": entry.reason.value,
                "detail": entry.detail,
            }
            for entry in unresolvables
        ]
        scanned_bodies: list[str] = []
        if "html" in scan_sources:
            scanned_bodies.append(html_body)
        if "text" in scan_sources:
            scanned_bodies.append(text_body)
        tokens_scanned = count_body_tokens(*scanned_bodies)

    unresolvable_count = len(unresolvable_keys)
    resolved_token_count = max(tokens_scanned - unresolvable_count, 0)

    return {
        "resolved_html": resolved_html,
        "resolved_text": resolved_text,
        "unresolvable_keys": unresolvable_keys,
        "total_placeholders": tokens_scanned,
        "resolved_count": resolved_token_count,
        "unresolvable_count": unresolvable_count,
        "tokens_scanned": tokens_scanned,
        "resolved_token_count": resolved_token_count,
        "scan_sources": scan_sources,
        "evaluated_from": evaluated_from,
    }
