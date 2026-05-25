from __future__ import annotations

import asyncpg

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.namespace import normalize_key
from shared.resolution.resolver import PLACEHOLDER_PATTERN, ReasonCode, ResolutionResult, resolve_body
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
    html_body, _text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    context = build_resolution_context(session_context)
    return await resolve_body(
        pool,
        redis_client,
        graph,
        html_body,
        context,
        session_context.session_id,
        session_context.template_name,
    )


def map_unresolvable_reason(reason: ReasonCode) -> str:
    return _REASON_TO_CONTRACT.get(reason, "MISSING")


def working_copy_key(session_context: SessionContext) -> str:
    return f"working-copy:{session_context.template_name}:{session_context.session_id}"


def snapshot_key(session_context: SessionContext) -> str:
    return f"working-copy-snapshot:{session_context.template_name}:{session_context.session_id}"


SNAPSHOT_NONE_SENTINEL = "__SNAPSHOT_NONE__"
