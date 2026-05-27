from __future__ import annotations

from typing import Any

from fastapi import Depends

from api.errors import api_error
from api.helpers import get_stored_session


async def require_session(session_id: str) -> dict[str, Any]:
    session = await get_stored_session(session_id)
    if session is None:
        raise api_error(
            404,
            "SessionNotFound",
            f"No session found for session_id: {session_id}",
        )
    return dict(session.state)
