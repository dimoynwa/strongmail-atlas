from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.errors import api_error
from api.helpers import get_resolution_graph, utc_now_iso
from api.middleware.session_guard import require_session
from api.models.requests import WorkingCopyPatchRequest
from api.models.responses import (
    WorkingCopyDeleteResponse,
    WorkingCopyOverride,
    WorkingCopyPatchResponse,
    WorkingCopyResponse,
)
from shared.redis_client import get_redis
from template_assistant.context import validate_session_context
from template_assistant.services import working_copy_key
from template_assistant.subagents.working_copy_subagent import get_working_copy

router = APIRouter(prefix="/working-copy", tags=["working-copy"])


@router.get("/{session_id}", response_model=WorkingCopyResponse)
async def get_working_copy_endpoint(
    session_id: str,
    session_state: dict[str, Any] = Depends(require_session),
) -> WorkingCopyResponse:
    overrides_map = await get_working_copy(session_state)
    overrides = [
        WorkingCopyOverride(key=key, value=value, set_at=None)
        for key, value in sorted(overrides_map.items())
    ]
    total = len(overrides)
    return WorkingCopyResponse(
        session_id=session_id,
        overrides=overrides,
        total_overrides=total,
        session_has_changes=total > 0,
    )


@router.patch("/{session_id}", response_model=WorkingCopyPatchResponse)
async def patch_working_copy(
    session_id: str,
    body: WorkingCopyPatchRequest,
    session_state: dict[str, Any] = Depends(require_session),
) -> WorkingCopyPatchResponse:
    del session_id
    canonical_key = body.key.upper()
    graph = await get_resolution_graph(session_state)
    if canonical_key not in graph:
        session_context = validate_session_context(session_state)
        raise api_error(
            404,
            "KeyNotInGraph",
            f"{canonical_key} is not in the resolution graph for {session_context.template_name}",
        )

    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    wc_key = working_copy_key(session_context)
    try:
        previous_value = await redis_client.hget(wc_key, canonical_key)
        await redis_client.hset(wc_key, canonical_key, body.value)
    except Exception as exc:
        raise api_error(500, "RedisWriteFailed", f"Failed to write working copy: {exc}") from exc

    return WorkingCopyPatchResponse(
        key=canonical_key,
        value=body.value,
        previous_value=previous_value,
        success=True,
    )


@router.delete("/{session_id}", response_model=WorkingCopyDeleteResponse)
async def delete_working_copy(
    session_id: str,
    session_state: dict[str, Any] = Depends(require_session),
) -> WorkingCopyDeleteResponse:
    del session_id
    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    wc_key = working_copy_key(session_context)
    try:
        keys_cleared = await redis_client.hlen(wc_key)
        if keys_cleared:
            await redis_client.delete(wc_key)
    except Exception as exc:
        raise api_error(503, "RedisUnavailable", f"Redis unavailable: {exc}") from exc

    return WorkingCopyDeleteResponse(keys_cleared=keys_cleared, success=True)


@router.get("/{session_id}/export")
async def export_working_copy(
    session_id: str,
    session_state: dict[str, Any] = Depends(require_session),
) -> JSONResponse:
    session_context = validate_session_context(session_state)
    overrides = await get_working_copy(session_state)
    exported_at = utc_now_iso()
    filename = (
        f"{session_context.template_name}_working_copy_"
        f"{exported_at[:10].replace('-', '')}.json"
    )
    payload = {
        "template_name": session_context.template_name,
        "lang_local": session_context.lang_local,
        "param_cust_brand": session_context.param_cust_brand,
        "exported_at": exported_at,
        "overrides": overrides,
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
