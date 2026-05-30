from __future__ import annotations

from api.refresh.redis_sync import get_sync_redis

TEMPLATE_LOCK_TTL = 30 * 60
FULL_LOCK_TTL = 3 * 60 * 60


def _template_lock_key(template_name: str) -> str:
    return f"refresh-lock:template:{template_name}"


def _full_lock_key() -> str:
    return "refresh-lock:full"


def acquire_lock(
    lock_type: str,
    holder_job_id: str,
    *,
    target: str | None = None,
    ttl_seconds: int | None = None,
) -> bool:
    redis_client = get_sync_redis()
    if lock_type == "full":
        key = _full_lock_key()
        ttl = ttl_seconds or FULL_LOCK_TTL
    elif lock_type == "template":
        if not target:
            raise ValueError("target is required for template locks")
        key = _template_lock_key(target)
        ttl = ttl_seconds or TEMPLATE_LOCK_TTL
    else:
        raise ValueError(f"Unknown lock type: {lock_type}")

    return bool(redis_client.set(key, holder_job_id, nx=True, ex=ttl))


def release_lock(lock_type: str, *, target: str | None = None) -> None:
    redis_client = get_sync_redis()
    if lock_type == "full":
        key = _full_lock_key()
    elif lock_type == "template":
        if not target:
            raise ValueError("target is required for template locks")
        key = _template_lock_key(target)
    else:
        raise ValueError(f"Unknown lock type: {lock_type}")
    redis_client.delete(key)


def is_locked(lock_type: str, *, target: str | None = None) -> bool:
    return get_lock_holder(lock_type, target=target) is not None


def get_lock_holder(lock_type: str, *, target: str | None = None) -> str | None:
    redis_client = get_sync_redis()
    if lock_type == "full":
        key = _full_lock_key()
    elif lock_type == "template":
        if not target:
            raise ValueError("target is required for template locks")
        key = _template_lock_key(target)
    else:
        raise ValueError(f"Unknown lock type: {lock_type}")
    holder = redis_client.get(key)
    return holder if holder else None


def release_all_locks_for_job(job_id: str, *, target: str | None = None) -> None:
    redis_client = get_sync_redis()
    full_holder = redis_client.get(_full_lock_key())
    if full_holder == job_id:
        release_lock("full")
    if target:
        template_holder = redis_client.get(_template_lock_key(target))
        if template_holder == job_id:
            release_lock("template", target=target)
