from __future__ import annotations

import types
from datetime import UTC, datetime
from typing import Any

from api.state import APP_USER_ID, TEMPLATE_APP, session_service
from shared.db import get_pool
from shared.resolution.graph_builder import build_resolution_graph


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def get_resolution_graph(session_state: dict[str, Any]) -> types.MappingProxyType[str, str]:
    cached = session_state.get("resolution_graph")
    if isinstance(cached, dict) and cached:
        return types.MappingProxyType(cached)

    pool = get_pool()
    graph = await build_resolution_graph(pool, session_state["template_name"])
    update_session_state(session_state["session_id"], {"resolution_graph": dict(graph)})
    return graph


def update_session_state(session_id: str, updates: dict[str, Any]) -> None:
    stored = (
        session_service.sessions.get(TEMPLATE_APP, {})
        .get(APP_USER_ID, {})
        .get(session_id)
    )
    if stored is None:
        return
    stored.state.update(updates)


async def get_stored_session(session_id: str):
    return await session_service.get_session(
        app_name=TEMPLATE_APP,
        user_id=APP_USER_ID,
        session_id=session_id,
    )
