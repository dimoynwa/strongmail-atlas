from __future__ import annotations

from api.refresh import job_registry


def test_create_update_get_and_list_active(redis_client):
    del redis_client
    job_id = job_registry.generate_job_id()
    created = job_registry.create(job_id, "template", target="my-template")
    assert created.status == "pending"
    assert created.target == "my-template"

    updated = job_registry.update(job_id, status="running")
    assert updated is not None
    assert updated.status == "running"

    fetched = job_registry.get_status(job_id)
    assert fetched is not None
    assert fetched.job_id == job_id

    active = job_registry.list_active()
    assert any(j.job_id == job_id for j in active)

    job_registry.update(job_id, status="done", finished_at="2026-05-30T09:00:00Z")
    active_after = job_registry.list_active()
    assert all(j.job_id != job_id for j in active_after)


def test_get_unknown_job_returns_none(redis_client):
    del redis_client
    assert job_registry.get_status("refresh-unknown") is None


def test_mark_orphaned_jobs_failed(redis_client):
    del redis_client
    job_id = job_registry.generate_job_id()
    job_registry.create(job_id, "template", target="orphan-tpl")
    job_registry.update(job_id, status="running")
    locks = __import__("api.refresh.locks", fromlist=["acquire_lock"]).acquire_lock
    locks("template", job_id, target="orphan-tpl")

    count = job_registry.mark_orphaned_jobs_failed()
    assert count >= 1
    job = job_registry.get_status(job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error == "Server restarted mid-job"
