from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from api.refresh import job_registry, locks, progress
from api.refresh.models import LinkedBlocksResult


@pytest.fixture
def template_env(monkeypatch):
    monkeypatch.setenv("STRONGMAIL_PASSWORD", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:15433/strongmail_tov_test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


async def _seed_template(db_pool, name: str = "RefreshTemplate") -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO template (id, name) VALUES ('rt1', $1)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """,
            name,
        )


@pytest.mark.asyncio
async def test_post_template_refresh_returns_job_id(api_client, db_pool, template_env):
    await _seed_template(db_pool)

    with patch("api.routers.refresh.submit_job") as submit_mock:
        response = await api_client.post("/refresh/template/RefreshTemplate")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"].startswith("refresh-")
    submit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_template_refresh_conflict_409(api_client, db_pool, template_env):
    await _seed_template(db_pool)
    locks.acquire_lock("template", "existing-job", target="RefreshTemplate")

    response = await api_client.post("/refresh/template/RefreshTemplate")
    assert response.status_code == 409
    detail = response.json()
    assert detail["status"] == "blocked"
    assert detail["locked_by"] == "existing-job"


@pytest.mark.asyncio
async def test_template_refresh_503_without_password(api_client, db_pool, monkeypatch):
    await _seed_template(db_pool)
    monkeypatch.delenv("STRONGMAIL_PASSWORD", raising=False)

    response = await api_client.post("/refresh/template/RefreshTemplate")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_job_failure_releases_lock_and_emits_job_failed(api_client, db_pool, template_env):
    await _seed_template(db_pool)
    linked = LinkedBlocksResult(block_ids=[], rule_ids=[], template_id="rt1")

    def failing_job(**kwargs):
        job_id = kwargs["job_id"]
        progress.emit_event(job_id, "job_failed", "boom")
        job_registry.update(job_id, status="failed", error="boom")
        locks.release_lock("template", target="RefreshTemplate")

    with patch("api.routers.refresh.submit_job", side_effect=lambda fn, **kw: fn(**kw)):
        with patch("api.routers.refresh.run_template_refresh_job", side_effect=failing_job):
            start = await api_client.post("/refresh/template/RefreshTemplate")
            job_id = start.json()["job_id"]

    job = job_registry.get_status(job_id)
    assert job is not None
    assert job.status == "failed"
    events = progress.list_events(job_id)
    assert any(e.type == "job_failed" for e in events)
    assert locks.get_lock_holder("template", target="RefreshTemplate") is None


@pytest.mark.asyncio
async def test_get_status_and_active(api_client, db_pool, template_env):
    await _seed_template(db_pool)
    job_id = job_registry.generate_job_id()
    job_registry.create(job_id, "template", target="RefreshTemplate")
    job_registry.update(job_id, status="running")

    status_resp = await api_client.get(f"/refresh/status/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "running"

    active_resp = await api_client.get("/refresh/active")
    assert active_resp.status_code == 200
    assert any(j["job_id"] == job_id for j in active_resp.json()["jobs"])

    missing = await api_client.get("/refresh/status/refresh-missing")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_active_empty(api_client, template_env):
    response = await api_client.get("/refresh/active")
    assert response.status_code == 200
    assert response.json()["jobs"] == []


@pytest.mark.asyncio
async def test_sse_stream_replays_events(api_client, db_pool, template_env):
    await _seed_template(db_pool)
    job_id = job_registry.generate_job_id()
    job_registry.create(job_id, "template", target="RefreshTemplate")
    progress.emit_event(job_id, "step_start", "Start", step="fetch_template_body")
    progress.emit_event(job_id, "job_done", "Done")
    job_registry.update(job_id, status="done")

    async with api_client.stream("GET", f"/refresh/stream/{job_id}") as response:
        assert response.status_code == 200
        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                chunks.append(json.loads(line.removeprefix("data:").strip()))

    assert chunks[0]["type"] == "step_start"
    assert chunks[-1]["type"] == "job_done"


@pytest.mark.asyncio
async def test_full_refresh_503_without_password(api_client, template_env, monkeypatch):
    monkeypatch.delenv("STRONGMAIL_PASSWORD", raising=False)
    response = await api_client.post("/refresh/full")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_full_refresh_starts_job(api_client, template_env):
    with patch("api.routers.refresh.submit_job") as submit_mock:
        response = await api_client.post("/refresh/full")
    assert response.status_code == 200
    submit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_orphan_check_on_startup(api_client, db_pool, template_env):
    job_id = job_registry.generate_job_id()
    job_registry.create(job_id, "template", target="orphan")
    job_registry.update(job_id, status="running")
    locks.acquire_lock("template", job_id, target="orphan")

    count = job_registry.mark_orphaned_jobs_failed()
    assert count >= 1
