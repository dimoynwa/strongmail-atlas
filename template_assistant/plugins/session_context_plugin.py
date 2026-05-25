from __future__ import annotations

import os

from google.adk.plugins.base_plugin import BasePlugin

from google.adk.agents.invocation_context import InvocationContext

_SESSION_ENV = {
    "template_name": "TEMPLATE_NAME",
    "lang_local": "LANG_LOCAL",
    "param_cust_brand": "PARAM_CUST_BRAND",
}


def default_session_state_from_env() -> dict[str, str]:
    """Build session context defaults from environment variables."""
    state: dict[str, str] = {}
    for state_key, env_key in _SESSION_ENV.items():
        value = os.getenv(env_key, "").strip()
        if value:
            state[state_key] = value
    return state


class SessionContextPlugin(BasePlugin):
    """Seed ADK session state with template context before each run."""

    def __init__(self) -> None:
        super().__init__(name="session_context")

    async def before_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        session = invocation_context.session
        state = session.state
        state["session_id"] = session.id

        for state_key, env_key in _SESSION_ENV.items():
            if state.get(state_key):
                continue
            value = os.getenv(env_key, "").strip()
            if value:
                state[state_key] = value
