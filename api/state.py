from __future__ import annotations

from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from general_agent.agent import root_agent as general_agent
from template_assistant.agent import root_agent as template_agent

APP_USER_ID = "default"
TEMPLATE_APP = "template_assistant"
GENERAL_APP = "general_agent"

session_service = InMemorySessionService()

template_runner = Runner(
    agent=template_agent,
    app_name=TEMPLATE_APP,
    session_service=session_service,
)

general_runner = Runner(
    agent=general_agent,
    app_name=GENERAL_APP,
    session_service=session_service,
)

db_pool = None
redis_client = None
classifier: Any | None = None
