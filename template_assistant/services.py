from __future__ import annotations

import types

import asyncpg

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.namespace import normalize_key
from shared.resolution.resolver import (
    PLACEHOLDER_PATTERN,
    ReasonCode,
    ResolutionResult,
    UnresolvableEntry,
    resolve_body,
    resolve_key,
)
from template_assistant.context import SessionContext, build_resolution_context

_REASON_TO_CONTRACT = {
    ReasonCode.MISSING_KEY: "MISSING",
    ReasonCode.CYCLE: "CYCLE",
    ReasonCode.BROKEN_RULE_CHAIN: "BROKEN_RULE",
    ReasonCode.INVALID_RULE: "BROKEN_RULE",
}


def extract_placeholder_keys(body: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for match in PLACEHOLDER_PATTERN.finditer(body):
        canonical = normalize_key(match.group(0))
        if canonical and canonical not in seen:
            seen.add(canonical)
            keys.append(canonical)
    return keys


async def fetch_template_bodies(
    pool: asyncpg.Pool,
    template_name: str,
    lang_local: str,
    param_cust_brand: str,
) -> tuple[str, str]:
    """Fetch template HTML/text bodies for the named template.

    ``lang_local`` and ``param_cust_brand`` are session resolution context;
    ``template_details`` stores one body row per template in production.
    """
    del lang_local, param_cust_brand
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT td.html, td.text
            FROM template t
            JOIN template_details td ON td.template_id = t.id
            WHERE t.name = $1
            LIMIT 1
            """,
            template_name,
        )
        if row is None:
            return "", ""
        return row["html"] or "", row["text"] or ""


async def resolve_template(session_context: SessionContext) -> ResolutionResult:
    """Resolve the template HTML body using the shared resolution engine."""
    pool = get_pool()
    redis_client = get_redis()
    graph = await build_resolution_graph(pool, session_context.template_name)
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
    if text_body:
        await resolve_body(
            pool,
            redis_client,
            graph,
            text_body,
            context,
            session_context.session_id,
            session_context.template_name,
            accumulated_keys=accumulated_keys,
        )
    return ResolutionResult(
        resolved_body=html_result.resolved_body,
        unresolvable=html_result.unresolvable,
        resolved_keys=sorted(accumulated_keys),
    )


def map_unresolvable_reason(reason: ReasonCode) -> str:
    return _REASON_TO_CONTRACT.get(reason, "MISSING")


def select_reachability_body(html_body: str, text_body: str) -> str:
    """Return the single body used for tone reachability (text first, else html)."""
    if text_body.strip():
        return text_body
    if html_body.strip():
        return html_body
    return ""


def count_body_tokens(*bodies: str) -> int:
    """Count distinct placeholder tokens across one or more template bodies."""
    seen: set[str] = set()
    for body in bodies:
        for key in extract_placeholder_keys(body):
            seen.add(key)
    return len(seen)


def _merge_unresolvables(
    target: dict[str, UnresolvableEntry],
    entries: list[UnresolvableEntry],
) -> None:
    for entry in entries:
        target.setdefault(entry.key, entry)


async def scan_template_unresolvables(
    session_context: SessionContext,
    *,
    graph: types.MappingProxyType[str, str],
    include_html: bool = True,
    include_text: bool = True,
) -> tuple[list[UnresolvableEntry], list[str]]:
    """Scan HTML and/or text bodies for unresolvable placeholders."""
    pool = get_pool()
    redis_client = get_redis()
    html_body, text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    context = build_resolution_context(session_context)
    by_key: dict[str, UnresolvableEntry] = {}
    scan_sources: list[str] = []

    if include_html and html_body.strip():
        html_result = await resolve_body(
            pool,
            redis_client,
            graph,
            html_body,
            context,
            session_context.session_id,
            session_context.template_name,
        )
        _merge_unresolvables(by_key, html_result.unresolvable)
        scan_sources.append("html")

    if include_text and text_body.strip():
        text_result = await resolve_body(
            pool,
            redis_client,
            graph,
            text_body,
            context,
            session_context.session_id,
            session_context.template_name,
        )
        _merge_unresolvables(by_key, text_result.unresolvable)
        scan_sources.append("text")

    ordered = sorted(by_key.values(), key=lambda entry: entry.key)
    return ordered, scan_sources


async def build_tone_eligible_keys(
    session_context: SessionContext,
    *,
    graph: types.MappingProxyType[str, str] | None = None,
    working_copy: dict[str, str] | None = None,
) -> dict[str, str]:
    """Discover tone-eligible keys and their resolved values for working-copy init."""
    from template_assistant.subagents.tone_suggestion_subagent import evaluate_eligibility

    pool = get_pool()
    redis_client = get_redis()
    if graph is None:
        graph = await build_resolution_graph(pool, session_context.template_name)
    html_body, text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    body = select_reachability_body(html_body, text_body)
    if not body.strip():
        return {}

    context = build_resolution_context(session_context)
    accumulated_keys: set[str] = set()
    await resolve_body(
        pool,
        redis_client,
        graph,
        body,
        context,
        session_context.session_id,
        session_context.template_name,
        accumulated_keys=accumulated_keys,
    )
    reachable = accumulated_keys
    wc = {} if working_copy is None else working_copy
    eligible: dict[str, str] = {}

    for key, graph_value in graph.items():
        if key not in reachable:
            continue
        eligibility_value = wc.get(key, graph_value)
        result = evaluate_eligibility(
            key,
            eligibility_value,
            session_context.lang_local,
            session_context.param_cust_brand,
        )
        if not result.eligible:
            continue
        resolved_value, _unres = await resolve_key(
            pool,
            redis_client,
            graph,
            key,
            context,
            session_context.session_id,
            session_context.template_name,
        )
        eligible[key] = resolved_value if resolved_value is not None else ""

    unresolvable_entries, _scan_sources = await scan_template_unresolvables(
        session_context,
        graph=graph,
    )
    for entry in unresolvable_entries:
        eligible.setdefault(entry.key, "")

    return eligible


async def is_working_copy_patchable_key(
    canonical_key: str,
    *,
    graph: types.MappingProxyType[str, str],
    session_context: SessionContext,
) -> bool:
    """Whether a key may be written via PATCH /working-copy.

    Tone-eligible graph keys are always patchable. Keys seeded at init from the
    unresolvable scan (or template placeholders) may not exist in the graph but
    must remain editable.
    """
    if canonical_key in graph:
        return True

    redis_client = get_redis()
    wc_key = working_copy_key(session_context)
    if await redis_client.hexists(wc_key, canonical_key):
        return True

    pool = get_pool()
    html_body, text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    for body in (html_body, text_body):
        if canonical_key in extract_placeholder_keys(body):
            return True
    return False


def working_copy_key(session_context: SessionContext) -> str:
    return f"working-copy:{session_context.template_name}:{session_context.session_id}"


def snapshot_key(session_context: SessionContext) -> str:
    return f"working-copy-snapshot:{session_context.template_name}:{session_context.session_id}"


SNAPSHOT_NONE_SENTINEL = "__SNAPSHOT_NONE__"
