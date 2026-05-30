from __future__ import annotations

import asyncio

from api.tone_batch import progress


def test_emit_tone_event_appends_to_list(redis_client):
    del redis_client
    job_id = "tone-test-progress"
    progress.emit_tone_event(job_id, "step_start", "Starting", step="load_templates")
    progress.emit_tone_event(job_id, "step_done", "Done", step="load_templates", count=1, total=1)

    events = progress.list_tone_events(job_id)
    assert len(events) == 2
    assert events[0].type == "step_start"
    assert events[1].step == "load_templates"


async def test_replay_and_tail_tone_events(redis_client):
    del redis_client
    job_id = "tone-test-replay"
    progress.emit_tone_event(job_id, "step_start", "A", step="s1")
    progress.emit_tone_event(job_id, "job_done", "Complete")

    replayed = [event async for event in progress.replay_tone_events(job_id)]
    assert len(replayed) == 2

    new_events, index = await progress.tail_tone_events(job_id, 1)
    assert index == 2
    assert len(new_events) == 1
    assert new_events[0].type == "job_done"
