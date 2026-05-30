from __future__ import annotations

from api.refresh.redis_sync import get_sync_redis

BATCH_LOCK_TTL = 2 * 60 * 60
BATCH_LOCK_KEY = "tone-lock:batch"


def acquire_tone_lock(holder_job_id: str, *, ttl_seconds: int | None = None) -> bool:
    redis_client = get_sync_redis()
    ttl = ttl_seconds or BATCH_LOCK_TTL
    return bool(redis_client.set(BATCH_LOCK_KEY, holder_job_id, nx=True, ex=ttl))


def release_tone_lock() -> None:
    get_sync_redis().delete(BATCH_LOCK_KEY)


def is_tone_locked() -> bool:
    return get_tone_lock_holder() is not None


def get_tone_lock_holder() -> str | None:
    holder = get_sync_redis().get(BATCH_LOCK_KEY)
    return holder if holder else None
