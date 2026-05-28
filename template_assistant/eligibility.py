from __future__ import annotations

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import resolve_key as shared_resolve_key
from template_assistant.context import build_resolution_context, validate_session_context


def is_eligible_for_rewrite(key: str, value: str) -> bool:
    upper_key = key.upper()
    if upper_key.endswith(("_URL", "_COLOR", "_ID")):
        return False
    if value.startswith("http"):
        return False
    if len(value) < 20:
        return False
    return True


async def get_eligible_keys(
    session_state: dict, force_reload: bool = False
) -> dict[str, str]:
    """Return editable keys mapped to their current resolved values."""
    del force_reload
    session_context = validate_session_context(session_state)
    pool = get_pool()
    graph = await build_resolution_graph(pool, session_context.template_name)
    redis_client = get_redis()
    context = build_resolution_context(session_context)

    eligible: dict[str, str] = {}
    for key in sorted(graph.keys()):
        value, _unres = await shared_resolve_key(
            pool,
            redis_client,
            graph,
            key,
            context,
            session_context.session_id,
            session_context.template_name,
        )
        if value is not None and is_eligible_for_rewrite(key, value):
            eligible[key] = value
    return eligible
