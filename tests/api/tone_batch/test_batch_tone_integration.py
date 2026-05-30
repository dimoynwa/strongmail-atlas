from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from api.tone_batch import job_registry, locks, progress


async def _seed_template(db_pool, *, template_id: str, name: str) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO template (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
            template_id,
            name,
        )
        await conn.execute(
            """
            INSERT INTO template_details
                (template_id, lang_local, param_cust_brand, subject, summary, html, text)
            VALUES ($1, 'EN', 'SKRILL', 'Subject', 'Summary', '<p>Long enough body text for evaluation here.</p>', '')
            """,
            template_id,
        )


from shared.config import get_test_database_url


@pytest.fixture
def tone_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", get_test_database_url())


@pytest.mark.asyncio
async def test_batch_reevaluate_returns_job_id(api_client, db_pool, tone_env):
    import api.state as state

    await _seed_template(db_pool, template_id="bt1", name="BatchTemplate")
    state.classifier = lambda text: [{"label": "joy", "score": 0.8}]

    response = await api_client.post("/tone/batch-reevaluate")
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("tone-")
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_batch_reevaluate_conflict_while_running(api_client, db_pool, tone_env):
    import api.state as state

    await _seed_template(db_pool, template_id="bt2", name="BatchTemplate2")
    state.classifier = lambda text: [{"label": "joy", "score": 0.8}]
    locks.acquire_tone_lock("tone-running-job")

    response = await api_client.post("/tone/batch-reevaluate")
    assert response.status_code == 409
    detail = response.json()
    assert detail["status"] == "blocked"
    assert detail["locked_by"] == "tone-running-job"


@pytest.mark.asyncio
async def test_batch_job_releases_lock_on_completion(api_client, db_pool, tone_env):
    import api.state as state

    await _seed_template(db_pool, template_id="bt3", name="BatchTemplate3")
    state.classifier = lambda text: [
        {"label": "joy", "score": 0.9},
        {"label": "admiration", "score": 0.7},
        {"label": "approval", "score": 0.5},
    ]

    with patch("api.routers.tone_batch.submit_tone_job") as submit_mock:
        def run_sync(**kwargs):
            from api.tone_batch.batch_tone import run_batch_tone_job

            run_batch_tone_job(**kwargs)

        submit_mock.side_effect = run_sync
        start = await api_client.post("/tone/batch-reevaluate")
        job_id = start.json()["job_id"]

    job = job_registry.get_tone_job_status(job_id)
    assert job is not None
    assert job.status == "done"
    assert locks.get_tone_lock_holder() is None
    events = progress.list_tone_events(job_id)
    assert any(event.type == "job_done" for event in events)


@pytest.mark.asyncio
async def test_batch_stream_and_export(api_client, db_pool, tone_env):
    import api.state as state

    await _seed_template(db_pool, template_id="bt4", name="BatchTemplate4")
    state.classifier = lambda text: [
        {"label": "joy", "score": 0.9},
        {"label": "admiration", "score": 0.7},
        {"label": "approval", "score": 0.5},
    ]

    with patch("api.routers.tone_batch.submit_tone_job") as submit_mock:
        submit_mock.side_effect = lambda **kwargs: __import__(
            "api.tone_batch.batch_tone", fromlist=["run_batch_tone_job"]
        ).run_batch_tone_job(**kwargs)
        start = await api_client.post("/tone/batch-reevaluate")
        job_id = start.json()["job_id"]

    stream_resp = await api_client.get(f"/tone/batch-stream/{job_id}")
    assert stream_resp.status_code == 200
    assert "job_done" in stream_resp.text

    export_resp = await api_client.get("/tone/export")
    assert export_resp.status_code == 200
    assert b"TONE_1" in export_resp.content
    assert b"BatchTemplate4" in export_resp.content
    assert b"joy" in export_resp.content
