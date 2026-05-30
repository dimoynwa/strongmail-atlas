from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from api.refresh.models import EventType, ProgressEvent
from api.refresh.redis_sync import get_sync_redis


def _progress_key(job_id: str) -> str:
    return f"refresh-job:{job_id}:progress"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit_event(
    job_id: str,
    event_type: EventType,
    message: str,
    *,
    step: str | None = None,
    count: int | None = None,
    total: int | None = None,
) -> ProgressEvent:
    event = ProgressEvent(
        type=event_type,
        step=step,
        message=message,
        count=count,
        total=total,
        timestamp=_now_iso(),
    )
    get_sync_redis().rpush(_progress_key(job_id), json.dumps(event.to_dict()))
    return event


def list_events(job_id: str) -> list[ProgressEvent]:
    raw_items = get_sync_redis().lrange(_progress_key(job_id), 0, -1)
    events: list[ProgressEvent] = []
    for raw in raw_items:
        data = json.loads(raw)
        events.append(
            ProgressEvent(
                type=data["type"],
                step=data.get("step"),
                message=data["message"],
                count=data.get("count"),
                total=data.get("total"),
                timestamp=data["timestamp"],
            )
        )
    return events


async def replay_events(job_id: str) -> AsyncIterator[ProgressEvent]:
    for event in list_events(job_id):
        yield event


async def tail_events(job_id: str, start_index: int) -> tuple[list[ProgressEvent], int]:
    events = list_events(job_id)
    new_events = events[start_index:]
    return new_events, len(events)


async def stream_events(job_id: str) -> AsyncIterator[ProgressEvent]:
    index = 0
    while True:
        new_events, index = await tail_events(job_id, index)
        for event in new_events:
            yield event
            if event.type in ("job_done", "job_failed"):
                return
        await asyncio.sleep(0.25)
