from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import state
from api.tone_batch import job_registry, locks, progress
from api.tone_batch.job_runner import submit_tone_job

router = APIRouter(tags=["tone-batch"])


class StartToneJobResponse(BaseModel):
    job_id: str
    status: str = "pending"


class ActiveToneJobsResponse(BaseModel):
    jobs: list[dict]


def _read_env() -> dict[str, str]:
    return {
        "DATABASE_URL": os.environ.get("DATABASE_URL", ""),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    }


def _require_database() -> dict[str, str]:
    env = _read_env()
    if not env["DATABASE_URL"]:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ServiceUnavailable",
                "message": "DATABASE_URL is not configured",
                "detail": None,
            },
        )
    return env


def _blocked(locked_by: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "error": "Conflict",
            "job_id": None,
            "status": "blocked",
            "locked_by": locked_by,
        },
    )


@router.post("/batch-reevaluate", status_code=202, response_model=StartToneJobResponse)
async def start_batch_reevaluate() -> StartToneJobResponse:
    env = _require_database()

    if state.classifier is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ModelNotReady",
                "message": "GoEmotions classifier is still loading. Retry in a few seconds.",
                "detail": None,
            },
        )

    holder = await asyncio.to_thread(locks.get_tone_lock_holder)
    if holder:
        raise _blocked(holder)

    job_id = job_registry.generate_tone_job_id()
    await asyncio.to_thread(job_registry.create_tone_job, job_id)

    acquired = await asyncio.to_thread(locks.acquire_tone_lock, job_id)
    if not acquired:
        holder = await asyncio.to_thread(locks.get_tone_lock_holder)
        await asyncio.to_thread(
            job_registry.update_tone_job,
            job_id,
            status="failed",
            error="Could not acquire tone batch lock",
        )
        raise _blocked(holder or "unknown")

    submit_tone_job(job_id=job_id, env=env, classifier=state.classifier)
    return StartToneJobResponse(job_id=job_id)


@router.get("/batch-status/{job_id}")
async def get_batch_status(job_id: str) -> dict:
    job = await asyncio.to_thread(job_registry.get_tone_job_status, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job.to_dict()


@router.get("/batch-active", response_model=ActiveToneJobsResponse)
async def list_active_batch_jobs() -> ActiveToneJobsResponse:
    jobs = await asyncio.to_thread(job_registry.list_active_tone_jobs)
    summaries = [
        {
            "job_id": job.job_id,
            "status": job.status,
            "started_at": job.started_at,
        }
        for job in jobs
    ]
    return ActiveToneJobsResponse(jobs=summaries)


async def _sse_generator(job_id: str) -> AsyncIterator[str]:
    async for event in progress.replay_tone_events(job_id):
        yield f"data: {json.dumps(event.to_dict())}\n\n"
        if event.type in ("job_done", "job_failed"):
            return

    async for event in progress.stream_tone_events(job_id):
        yield f"data: {json.dumps(event.to_dict())}\n\n"


@router.get("/batch-stream/{job_id}")
async def stream_batch_progress(job_id: str) -> StreamingResponse:
    job = await asyncio.to_thread(job_registry.get_tone_job_status, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return StreamingResponse(
        _sse_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
