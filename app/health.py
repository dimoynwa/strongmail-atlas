from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from app.async_utils import run_async_at_startup
from shared.config import DATABASE_URL, REDIS_URL
from shared.db import get_pool, init_pool
from shared.redis_client import get_redis, init_redis


@dataclass
class StatusIndicator:
    name: str
    healthy: bool
    error_message: str | None = None


@st.cache_resource
def run_health_checks() -> list[StatusIndicator]:
    results: list[StatusIndicator] = []

    try:
        async def _pg_check() -> None:
            try:
                get_pool()
            except RuntimeError:
                await init_pool(DATABASE_URL)
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

        run_async_at_startup(_pg_check())
        results.append(StatusIndicator("PostgreSQL", True))
    except Exception as exc:
        results.append(StatusIndicator("PostgreSQL", False, str(exc)))

    try:
        async def _cache_check() -> None:
            try:
                get_redis()
            except RuntimeError:
                await init_redis(REDIS_URL)
            client = get_redis()
            await client.ping()

        run_async_at_startup(_cache_check())
        results.append(StatusIndicator("Redis", True))
    except Exception as exc:
        results.append(StatusIndicator("Redis", False, str(exc)))

    try:
        from app.ml import load_classifier

        healthy = load_classifier() is not None
        if healthy:
            results.append(StatusIndicator("GoEmotions", True))
        else:
            results.append(StatusIndicator("GoEmotions", False, "classifier unavailable"))
    except Exception as exc:
        results.append(StatusIndicator("GoEmotions", False, str(exc)))

    return results
