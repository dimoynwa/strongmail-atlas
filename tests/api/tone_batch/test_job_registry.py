from __future__ import annotations

from api.tone_batch import job_registry, locks


def test_create_update_get_and_list_active(redis_client):
    del redis_client
    job_id = job_registry.generate_tone_job_id()
    created = job_registry.create_tone_job(job_id)
    assert created.status == "pending"
    assert job_id.startswith("tone-")

    updated = job_registry.update_tone_job(job_id, status="running")
    assert updated is not None
    assert updated.status == "running"

    fetched = job_registry.get_tone_job_status(job_id)
    assert fetched is not None
    assert fetched.job_id == job_id

    active = job_registry.list_active_tone_jobs()
    assert any(j.job_id == job_id for j in active)

    job_registry.update_tone_job(job_id, status="done", finished_at="2026-05-30T09:00:00Z")
    active_after = job_registry.list_active_tone_jobs()
    assert all(j.job_id != job_id for j in active_after)


def test_get_unknown_job_returns_none(redis_client):
    del redis_client
    assert job_registry.get_tone_job_status("tone-unknown") is None


def test_mark_orphaned_tone_jobs_failed(redis_client):
    del redis_client
    job_id = job_registry.generate_tone_job_id()
    job_registry.create_tone_job(job_id)
    job_registry.update_tone_job(job_id, status="running")
    locks.acquire_tone_lock(job_id)

    count = job_registry.mark_orphaned_tone_jobs_failed()
    assert count >= 1
    job = job_registry.get_tone_job_status(job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error == "Server restarted mid-job"
    assert locks.get_tone_lock_holder() is None
