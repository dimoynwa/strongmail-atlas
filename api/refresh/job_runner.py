from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from api import state


def submit_job(
    job_fn: Callable[..., None],
    *,
    job_id: str,
    env: dict[str, str],
    **kwargs: Any,
) -> asyncio.Task[None]:
    loop = asyncio.get_running_loop()

    def _run() -> None:
        job_fn(job_id=job_id, env=env, **kwargs)

    return loop.run_in_executor(state.refresh_executor, _run)
