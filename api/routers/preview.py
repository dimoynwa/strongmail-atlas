from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from api.errors import api_error
from api.middleware.session_guard import require_session
from api.models.responses import PreviewResponse, UnresolvableKey
from api.services.preview import build_preview

router = APIRouter(tags=["preview"])


@router.get("/preview/{session_id}", response_model=PreviewResponse)
async def get_preview(
    session_id: str,
    highlight_modified: bool = Query(default=True),
    session_state: dict[str, Any] = Depends(require_session),
) -> PreviewResponse:
    del session_id
    try:
        result = await build_preview(session_state, highlight_modified=highlight_modified)
    except Exception as exc:
        raise api_error(500, "ResolutionFailed", f"Template resolution failed: {exc}") from exc

    return PreviewResponse(
        resolved_html=result["resolved_html"],
        resolved_text=result["resolved_text"],
        unresolvable_keys=[
            UnresolvableKey(**entry) for entry in result["unresolvable_keys"]
        ],
        total_placeholders=result["total_placeholders"],
        resolved_count=result["resolved_count"],
        unresolvable_count=result["unresolvable_count"],
        evaluated_from=result["evaluated_from"],
    )
