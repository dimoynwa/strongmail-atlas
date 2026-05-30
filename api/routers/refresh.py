from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import state
from api.refresh import job_registry, locks, progress
from api.refresh.full_refresh import run_full_refresh_job
from api.refresh.job_runner import submit_job
from api.refresh.linked_blocks import resolve_linked_blocks
from api.refresh.template_refresh import run_template_refresh_job

router = APIRouter(prefix="/refresh", tags=["refresh"])


class StartJobResponse(BaseModel):
    job_id: str


class BlockedResponse(BaseModel):
    job_id: str | None
    status: str
    locked_by: str


class ActiveJobsResponse(BaseModel):
    jobs: list[dict]


def _read_env() -> dict[str, str]:
    return {
        "STRONGMAIL_PASSWORD": os.environ.get("STRONGMAIL_PASSWORD", ""),
        "STRONGMAIL_ORG_ID": os.environ.get("STRONGMAIL_ORG_ID", "Skrill"),
        "STRONGMAIL_USERNAME": os.environ.get("STRONGMAIL_USERNAME", "io.teamprod"),
        "DATABASE_URL": os.environ.get("DATABASE_URL", ""),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    }


def _require_credentials() -> dict[str, str]:
    env = _read_env()
    if not env["STRONGMAIL_PASSWORD"]:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ServiceUnavailable",
                "message": "STRONGMAIL_PASSWORD is not configured",
                "detail": None,
            },
        )
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


@router.post("/template/{template_name}", response_model=StartJobResponse)
async def start_template_refresh(template_name: str) -> StartJobResponse:
    env = _require_credentials()

    full_holder = await asyncio.to_thread(locks.get_lock_holder, "full")
    if full_holder:
        raise _blocked(full_holder)

    template_holder = await asyncio.to_thread(
        locks.get_lock_holder, "template", target=template_name
    )
    if template_holder:
        raise _blocked(template_holder)

    if state.db_pool is None:
        raise HTTPException(status_code=503, detail="Database pool not initialized")

    job_id = job_registry.generate_job_id()
    await asyncio.to_thread(job_registry.create, job_id, "template", target=template_name)

    acquired = await asyncio.to_thread(
        locks.acquire_lock, "template", job_id, target=template_name
    )
    if not acquired:
        holder = await asyncio.to_thread(
            locks.get_lock_holder, "template", target=template_name
        )
        await asyncio.to_thread(
            job_registry.update,
            job_id,
            status="failed",
            error="Could not acquire template lock",
        )
        raise _blocked(holder or "unknown")

    progress.emit_event(
        job_id,
        "step_start",
        f"Resolving linked blocks for {template_name!r}…",
        step="resolve_linked_blocks",
    )
    try:
        linked = await resolve_linked_blocks(state.db_pool, template_name)
    except ValueError as exc:
        await asyncio.to_thread(
            job_registry.update,
            job_id,
            status="failed",
            error=str(exc),
        )
        await asyncio.to_thread(locks.release_lock, "template", target=template_name)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    progress.emit_event(
        job_id,
        "step_done",
        f"Resolved {len(linked.block_ids)} block(s), {len(linked.rule_ids)} rule(s)",
        step="resolve_linked_blocks",
        count=len(linked.block_ids),
        total=len(linked.rule_ids),
    )

    submit_job(
        run_template_refresh_job,
        job_id=job_id,
        env=env,
        template_name=template_name,
        linked=linked,
    )
    return StartJobResponse(job_id=job_id)


@router.post("/full", response_model=StartJobResponse)
async def start_full_refresh() -> StartJobResponse:
    env = _require_credentials()

    if await asyncio.to_thread(locks.is_locked, "full"):
        holder = await asyncio.to_thread(locks.get_lock_holder, "full")
        raise _blocked(holder or "unknown")

    for job in await asyncio.to_thread(job_registry.list_active):
        if job.status in ("pending", "running"):
            raise _blocked(job.job_id)

    job_id = job_registry.generate_job_id()
    await asyncio.to_thread(job_registry.create, job_id, "full")

    acquired = await asyncio.to_thread(locks.acquire_lock, "full", job_id)
    if not acquired:
        holder = await asyncio.to_thread(locks.get_lock_holder, "full")
        await asyncio.to_thread(
            job_registry.update,
            job_id,
            status="failed",
            error="Could not acquire full refresh lock",
        )
        raise _blocked(holder or "unknown")

    submit_job(run_full_refresh_job, job_id=job_id, env=env)
    return StartJobResponse(job_id=job_id)


@router.get("/status/{job_id}")
async def get_job_status(job_id: str) -> dict:
    job = await asyncio.to_thread(job_registry.get_status, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job.to_dict()


@router.get("/active", response_model=ActiveJobsResponse)
async def list_active_jobs() -> ActiveJobsResponse:
    jobs = await asyncio.to_thread(job_registry.list_active)
    summaries = [
        {
            "job_id": job.job_id,
            "type": job.type,
            "target": job.target,
            "status": job.status,
            "started_at": job.started_at,
        }
        for job in jobs
    ]
    return ActiveJobsResponse(jobs=summaries)


async def _sse_generator(job_id: str) -> AsyncIterator[str]:
    async for event in progress.replay_events(job_id):
        yield f"data: {json.dumps(event.to_dict())}\n\n"
        if event.type in ("job_done", "job_failed"):
            return

    async for event in progress.stream_events(job_id):
        yield f"data: {json.dumps(event.to_dict())}\n\n"


@router.get("/stream/{job_id}")
async def stream_job_progress(job_id: str) -> StreamingResponse:
    job = await asyncio.to_thread(job_registry.get_status, job_id)
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
