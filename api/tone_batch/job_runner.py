from __future__ import annotations

import asyncio
from typing import Any

from api import state
from api.tone_batch.batch_tone import run_batch_tone_job


def submit_tone_job(
    *,
    job_id: str,
    env: dict[str, str],
    classifier: Any,
) -> asyncio.Task[None]:
    loop = asyncio.get_running_loop()

    def _run() -> None:
        run_batch_tone_job(job_id=job_id, env=env, classifier=classifier)

    return loop.run_in_executor(state.refresh_executor, _run)
