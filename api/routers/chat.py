from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from google.genai import types

from api.errors import api_error
from api.helpers import get_stored_session
from api.models.requests import ChatStreamRequest
from api.state import (
    APP_USER_ID,
    GENERAL_APP,
    general_runner,
    session_service,
    template_runner,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy

router = APIRouter(tags=["chat"])


def _normalize_diff_suggestions(pending: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in pending:
        normalized.append(
            {
                "key": item["key"],
                "old_value": item.get("old_value") or item.get("current_value", ""),
                "new_value": item.get("new_value") or item.get("suggested_value", ""),
            }
        )
    return normalized


def _pending_diff(session_state: dict[str, Any]) -> dict[str, Any] | None:
    pending = session_state.get("pending_suggestions") or session_state.get("suggestions")
    if not pending:
        return None
    return {
        "suggestions": _normalize_diff_suggestions(pending),
        "snapshot_overwritten": bool(session_state.get("snapshot_overwritten", False)),
    }


@router.post("/chat/stream")
async def chat_stream(body: ChatStreamRequest) -> StreamingResponse:
    if body.agent not in ("template", "general"):
        raise api_error(400, "InvalidAgent", 'agent must be "template" or "general"')

    runner = template_runner if body.agent == "template" else general_runner

    if body.agent == "template":
        if not body.session_id:
            raise api_error(400, "MissingSessionId", "session_id is required for template agent")
        session = await get_stored_session(body.session_id)
        if session is None:
            raise api_error(
                404,
                "SessionNotFound",
                f"No ADK session found for session_id: {body.session_id}",
            )
        session_id = body.session_id
    else:
        session_id = body.session_id or str(uuid.uuid4())
        if body.session_id:
            session = await session_service.get_session(
                app_name=GENERAL_APP,
                user_id=APP_USER_ID,
                session_id=session_id,
            )
            if session is None:
                await session_service.create_session(
                    app_name=GENERAL_APP,
                    user_id=APP_USER_ID,
                    state={"session_id": session_id},
                    session_id=session_id,
                )
        else:
            await session_service.create_session(
                app_name=GENERAL_APP,
                user_id=APP_USER_ID,
                state={"session_id": session_id},
                session_id=session_id,
            )

    message = types.Content(role="user", parts=[types.Part(text=body.message)])

    async def generate():
        wc_before: dict[str, str] = {}
        if body.agent == "template" and body.session_id:
            try:
                stored = await get_stored_session(body.session_id)
                if stored is not None:
                    wc_before = await get_working_copy(dict(stored.state))
            except Exception:
                wc_before = {}

        try:
            async for event in runner.run_async(
                user_id=APP_USER_ID,
                session_id=session_id,
                new_message=message,
            ):
                function_calls = event.get_function_calls()
                if function_calls:
                    tool_name = function_calls[0].name
                    yield f"data: {json.dumps({'type': 'tool', 'name': tool_name})}\n\n"
                    continue

                if event.content and not event.is_final_response():
                    for part in event.content.parts or []:
                        if hasattr(part, "text") and part.text:
                            yield f"data: {json.dumps({'type': 'token', 'text': part.text})}\n\n"
                    continue

                if event.is_final_response():
                    text = ""
                    if event.content and event.content.parts:
                        text = event.content.parts[0].text or ""

                    diff = None
                    if body.agent == "template" and body.session_id:
                        stored = await get_stored_session(body.session_id)
                        if stored is not None:
                            diff = _pending_diff(dict(stored.state))

                    yield f"data: {json.dumps({'type': 'final', 'text': text, 'diff': diff})}\n\n"

                    if body.agent == "template" and body.session_id:
                        try:
                            stored = await get_stored_session(body.session_id)
                            if stored is not None:
                                wc_after = await get_working_copy(dict(stored.state))
                                if wc_after != wc_before:
                                    yield f"data: {json.dumps({'type': 'wc_updated'})}\n\n"
                        except Exception:
                            pass
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
