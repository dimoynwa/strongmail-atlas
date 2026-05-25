from __future__ import annotations

from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins.base_plugin import BasePlugin

from shared.config import DATABASE_URL, REDIS_URL
from shared.db import get_pool, init_pool
from shared.redis_client import get_redis, init_redis


class RuntimeInitPlugin(BasePlugin):
    """Initialize PostgreSQL and Redis clients before the first agent run."""

    def __init__(self) -> None:
        super().__init__(name="runtime_init")
        self._initialized = False

    async def before_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        del invocation_context
        if self._initialized:
            return

        try:
            get_pool()
        except RuntimeError:
            await init_pool(DATABASE_URL)

        try:
            get_redis()
        except RuntimeError:
            await init_redis(REDIS_URL)

        self._initialized = True
