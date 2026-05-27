from __future__ import annotations

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.agents.invocation_context import InvocationContext

from shared.config import DATABASE_URL
from shared.db import get_pool, init_pool


class DbInitPlugin(BasePlugin):
    """Initialize PostgreSQL before the first General Agent run (no Redis)."""

    def __init__(self) -> None:
        super().__init__(name="general_agent_db_init")
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

        self._initialized = True
