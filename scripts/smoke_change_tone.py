"""Smoke test: tone suggestion flow via Template Assistant agent.

Run against a live session with template NFY_SM_REGISTERED (or override TEMPLATE_NAME).
Expected: structural keys (e.g. EN.FOOTER_COPYRIGHT) never appear in tone suggestions.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from shared.config import DATABASE_URL, REDIS_URL
from shared.db import close_pool, init_pool
from shared.redis_client import init_redis
from shared.utils import call_agent_async
from template_assistant.agent import root_agent

import uuid

# TEMPLATE_NAME = "NFY_PASSWORD_CREATED"
TEMPLATE_NAME = "NFY_SM_REGISTERED"
APP_NAME = "template_assistant"
USER_ID = "test_user"
SESSION_ID = "smoke_change_tone_test-001-" + uuid.uuid4().hex

QUERIES = [
    "Make this template feel more admirational.",
    # Expect: diff showing only tone-bearing keys, no footer/header keys
    # "Apply all the suggested changes.",
    # Expect: confirmation of applied keys
    # "What changes have I made in this session?",
    # Expect: only the tone-bearing keys appear
    # "Undo the tone changes.",
    # Expect: all keys restored to pre-suggestion values
]


async def e2e_test() -> None:
    await init_pool(DATABASE_URL)
    redis = await init_redis(REDIS_URL)

    try:
        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            state={
                "template_name": TEMPLATE_NAME,
                "lang_local": "EN",
                "param_cust_brand": "SKRILL",
                "session_id": SESSION_ID,
                "user_name": "Dimo",
            },
        )
        runner = Runner(
            agent=root_agent,
            app_name=APP_NAME,
            session_service=session_service,
        )
        for query in QUERIES:
            await call_agent_async(runner, USER_ID, session.id, query)

        while True:
            query = input("Enter a query: ")
            if query == "exit":
                break
            await call_agent_async(runner, USER_ID, session.id, query)
    finally:
        await close_pool()
        await redis.aclose()

if __name__ == "__main__":
    asyncio.run(e2e_test())
