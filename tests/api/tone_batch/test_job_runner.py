from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from api.tone_batch.job_runner import submit_tone_job


async def test_submit_tone_job_runs_in_executor():
    executor = ThreadPoolExecutor(max_workers=1)
    import api.state as state

    state.refresh_executor = executor
    seen: dict[str, object] = {}

    def fake_batch(*, job_id: str, env: dict[str, str], classifier: object) -> None:
        seen["job_id"] = job_id
        seen["env"] = env["DATABASE_URL"]
        seen["classifier"] = classifier

    with patch("api.tone_batch.job_runner.run_batch_tone_job", side_effect=fake_batch):
        task = submit_tone_job(
            job_id="tone-test-123",
            env={"DATABASE_URL": "postgresql://test"},
            classifier="mock-classifier",
        )
        await task
    assert seen["job_id"] == "tone-test-123"
    assert seen["env"] == "postgresql://test"
    assert seen["classifier"] == "mock-classifier"
    executor.shutdown(wait=False)
