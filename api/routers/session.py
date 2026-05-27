from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status

from api.errors import api_error
from api.models.requests import CreateSessionRequest
from api.models.responses import CreateSessionResponse
from api.state import APP_USER_ID, TEMPLATE_APP, session_service
from shared.db import get_pool
from shared.resolution.graph_builder import build_resolution_graph
from template_assistant.eligibility import get_eligible_keys
from template_assistant.subagents.working_copy_subagent import get_working_copy

router = APIRouter(tags=["session"])

@router.post("/session", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSessionRequest) -> CreateSessionResponse:
    lang_local = body.lang_local.strip().upper()
    param_cust_brand = body.param_cust_brand.strip().upper()
    template_name = body.template_name.strip()

    pool = get_pool()
    async with pool.acquire() as conn:
        template_row = await conn.fetchrow(
            "SELECT id FROM template WHERE name = $1",
            template_name,
        )
    if template_row is None:
        raise api_error(
            404,
            "TemplateNotFound",
            f"Template not found: {template_name}",
        )

    session_id = str(uuid.uuid4())
    graph = await build_resolution_graph(pool, template_name)
    initial_state: dict[str, Any] = {
        "template_name": template_name,
        "lang_local": lang_local,
        "param_cust_brand": param_cust_brand,
        "session_id": session_id,
        "resolution_graph": dict(graph),
    }

    await session_service.create_session(
        app_name=TEMPLATE_APP,
        user_id=APP_USER_ID,
        state=initial_state,
        session_id=session_id,
    )

    session_state = dict(initial_state)
    eligible = await get_eligible_keys(session_state)
    overrides = await get_working_copy(session_state)

    return CreateSessionResponse(
        session_id=session_id,
        template_name=template_name,
        lang_local=lang_local,
        param_cust_brand=param_cust_brand,
        tone_key_count=len(eligible),
        working_copy_overrides=len(overrides),
    )
