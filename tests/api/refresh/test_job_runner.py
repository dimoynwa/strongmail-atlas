from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from api.refresh.job_runner import submit_job


async def test_submit_job_runs_in_executor():
    executor = ThreadPoolExecutor(max_workers=1)
    import api.state as state

    state.refresh_executor = executor
    seen: dict[str, str] = {}

    def job_fn(*, job_id: str, env: dict[str, str]) -> None:
        seen["job_id"] = job_id
        seen["env"] = env["DATABASE_URL"]

    task = submit_job(
        job_fn,
        job_id="refresh-test-123",
        env={"DATABASE_URL": "postgresql://test"},
    )
    await task
    assert seen["job_id"] == "refresh-test-123"
    assert seen["env"] == "postgresql://test"
    executor.shutdown(wait=False)
