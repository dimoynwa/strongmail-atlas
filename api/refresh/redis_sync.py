from __future__ import annotations

import os

import redis

_client: redis.Redis | None = None


def get_sync_redis() -> redis.Redis:
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _client = redis.Redis.from_url(url, decode_responses=True)
    return _client


def reset_sync_redis() -> None:
    global _client
    _client = None
