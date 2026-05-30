from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from api.refresh import locks
from api.refresh.models import JobStatus, JobType, RefreshJob
from api.refresh.redis_sync import get_sync_redis

JOB_TTL_SECONDS = 24 * 60 * 60


def _job_key(job_id: str) -> str:
    return f"refresh-job:{job_id}"


def _progress_key(job_id: str) -> str:
    return f"refresh-job:{job_id}:progress"


def generate_job_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"refresh-{ts}-{uuid4().hex[:8]}"


def _empty_to_none(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def _hash_to_job(job_id: str, data: dict[str, str]) -> RefreshJob:
    return RefreshJob(
        job_id=job_id,
        type=data["type"],  # type: ignore[arg-type]
        target=_empty_to_none(data.get("target")),
        status=data["status"],  # type: ignore[arg-type]
        started_at=data["started_at"],
        finished_at=_empty_to_none(data.get("finished_at")),
        error=_empty_to_none(data.get("error")),
    )


def create(job_id: str, job_type: JobType, *, target: str | None = None) -> RefreshJob:
    redis_client = get_sync_redis()
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    mapping = {
        "type": job_type,
        "target": target or "",
        "status": "pending",
        "started_at": started_at,
        "finished_at": "",
        "error": "",
    }
    redis_client.hset(_job_key(job_id), mapping=mapping)
    return _hash_to_job(job_id, mapping)


def update(
    job_id: str,
    *,
    status: JobStatus | None = None,
    finished_at: str | None = None,
    error: str | None = None,
) -> RefreshJob | None:
    redis_client = get_sync_redis()
    key = _job_key(job_id)
    if not redis_client.exists(key):
        return None

    updates: dict[str, str] = {}
    if status is not None:
        updates["status"] = status
    if finished_at is not None:
        updates["finished_at"] = finished_at
    if error is not None:
        updates["error"] = error.replace("\n", " ").replace("\r", " ")[:4000]
    if updates:
        redis_client.hset(key, mapping=updates)

    if status in ("done", "failed"):
        set_ttl(job_id)

    data = redis_client.hgetall(key)
    return _hash_to_job(job_id, data)


def get_status(job_id: str) -> RefreshJob | None:
    redis_client = get_sync_redis()
    data = redis_client.hgetall(_job_key(job_id))
    if not data:
        return None
    return _hash_to_job(job_id, data)


def list_active() -> list[RefreshJob]:
    redis_client = get_sync_redis()
    jobs: list[RefreshJob] = []
    for key in redis_client.scan_iter("refresh-job:*"):
        if key.endswith(":progress"):
            continue
        job_id = key.removeprefix("refresh-job:")
        data = redis_client.hgetall(key)
        if not data:
            continue
        job = _hash_to_job(job_id, data)
        if job.status in ("pending", "running"):
            jobs.append(job)
    jobs.sort(key=lambda j: j.started_at)
    return jobs


def set_ttl(job_id: str) -> None:
    redis_client = get_sync_redis()
    redis_client.expire(_job_key(job_id), JOB_TTL_SECONDS)
    redis_client.expire(_progress_key(job_id), JOB_TTL_SECONDS)


def mark_orphaned_jobs_failed(redis_url: str | None = None) -> int:
    import os

    if redis_url:
        os.environ.setdefault("REDIS_URL", redis_url)

    redis_client = get_sync_redis()
    count = 0
    for key in redis_client.scan_iter("refresh-job:*"):
        if key.endswith(":progress"):
            continue
        data = redis_client.hgetall(key)
        if data.get("status") != "running":
            continue
        job_id = key.removeprefix("refresh-job:")
        target = _empty_to_none(data.get("target"))
        update(job_id, status="failed", error="Server restarted mid-job")
        locks.release_all_locks_for_job(job_id, target=target)
        count += 1
    return count
