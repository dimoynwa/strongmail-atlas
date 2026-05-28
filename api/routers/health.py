from __future__ import annotations

import time

from fastapi import APIRouter

from api import state
from api.models.responses import HealthResponse
from api.state import APP_USER_ID, TEMPLATE_APP, session_service
from shared.db import get_pool
from shared.redis_client import get_redis

router = APIRouter(tags=["health"])


def _aggregate_status(component_statuses: list[str]) -> str:
    if any(status == "unavailable" for status in component_statuses):
        return "unavailable"
    if any(status == "degraded" for status in component_statuses):
        return "degraded"
    return "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    components: dict[str, dict] = {}

    postgres_status = "ok"
    postgres_latency = None
    try:
        start = time.perf_counter()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        postgres_latency = int((time.perf_counter() - start) * 1000)
    except Exception:
        postgres_status = "unavailable"

    components["postgres"] = {"status": postgres_status, "latency_ms": postgres_latency}

    redis_status = "ok"
    redis_latency = None
    try:
        start = time.perf_counter()
        client = get_redis()
        await client.ping()
        redis_latency = int((time.perf_counter() - start) * 1000)
    except Exception:
        redis_status = "unavailable"

    components["redis"] = {"status": redis_status, "latency_ms": redis_latency}

    if state.classifier is None:
        go_status = "degraded"
        go_model = None
    else:
        go_status = "ok"
        go_model = "SamLowe/roberta-base-go_emotions"

    components["go_emotions"] = {"status": go_status, "model": go_model}

    active_sessions = 0
    try:
        active_sessions = len(session_service.sessions.get(TEMPLATE_APP, {}).get(APP_USER_ID, {}))
    except Exception:
        pass

    components["adk"] = {"status": "ok", "active_sessions": active_sessions}

    critical = [components["postgres"]["status"], components["redis"]["status"]]
    overall = _aggregate_status(critical + [go_status])

    return HealthResponse(status=overall, components=components)
