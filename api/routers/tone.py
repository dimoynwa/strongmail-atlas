from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.errors import api_error
from api.helpers import update_session_state
from api.middleware.session_guard import require_session
from api import state
from api.models.requests import ToneApplyRequest, ToneEvaluateRequest, ToneUndoRequest
from api.models.responses import (
    ToneApplyResponse,
    ToneEvaluateResponse,
    ToneStoredResponse,
    ToneUndoResponse,
)
from api.services.preview import build_preview
from shared.db import get_pool
from template_assistant.context import validate_session_context
from template_assistant.ml.goemotions import scores_from_pipeline_result
from template_assistant.subagents.tone_evaluation_subagent import (
    evaluate_tone,
    normalize_stored_tones,
)
from template_assistant.subagents.tone_suggestion_subagent import apply_tone_suggestions, undo_tone_suggestions
from template_assistant.utils.text import extract_plain_text

router = APIRouter(prefix="/tone", tags=["tone"])


@router.post("/evaluate/{session_id}", response_model=ToneEvaluateResponse)
async def evaluate_tone_endpoint(
    session_id: str,
    body: ToneEvaluateRequest | None = None,
    session_state: dict[str, Any] = Depends(require_session),
) -> ToneEvaluateResponse:
    del session_id
    if state.classifier is None:
        raise api_error(
            503,
            "ModelNotReady",
            "GoEmotions classifier is still loading. Retry in a few seconds.",
        )

    top_n = body.top_n if body else 5
    preview = await build_preview(session_state, highlight_modified=False)
    plain_text = preview["resolved_text"] or extract_plain_text(preview["resolved_html"])

    if plain_text:
        raw_scores = state.classifier(plain_text)
        if isinstance(raw_scores, list) and raw_scores and isinstance(raw_scores[0], list):
            scores = scores_from_pipeline_result(raw_scores[0])
        else:
            scores = scores_from_pipeline_result(raw_scores)
    else:
        result = await evaluate_tone(session_state)
        scores = result.scores

    sorted_scores = dict(
        sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
    )

    session_context = validate_session_context(session_state)
    warning = None
    if session_context.lang_local != "EN":
        warning = (
            f"GoEmotions is English-optimised; results for lang_local="
            f"{session_context.lang_local} may be less accurate."
        )

    return ToneEvaluateResponse(
        emotions=sorted_scores,
        model="go_emotions",
        evaluated_from=preview["evaluated_from"],
        plain_text_length=len(plain_text),
        warning=warning,
    )


@router.get("/stored/{session_id}", response_model=ToneStoredResponse)
async def get_stored_tone(
    session_id: str,
    session_state: dict[str, Any] = Depends(require_session),
) -> ToneStoredResponse:
    del session_id
    session_context = validate_session_context(session_state)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT tte.tones, tte.evaluated_at, tte.model_id
            FROM template t
            JOIN template_tone_evaluations tte ON tte.template_id = t.id
            WHERE t.name = $1
              AND UPPER(tte.lang_local) = UPPER($2)
              AND UPPER(tte.param_cust_brand) = UPPER($3)
            ORDER BY tte.evaluated_at DESC
            LIMIT 1
            """,
            session_context.template_name,
            session_context.lang_local,
            session_context.param_cust_brand,
        )

    if row is None:
        return ToneStoredResponse(
            emotions=None,
            evaluated_at=None,
            model_id=None,
            source="none",
        )

    emotions = normalize_stored_tones(row["tones"])

    evaluated_at = row["evaluated_at"]
    if evaluated_at is not None:
        evaluated_at = evaluated_at.replace(tzinfo=None).isoformat() + "Z"

    return ToneStoredResponse(
        emotions=emotions,
        evaluated_at=evaluated_at,
        model_id=row["model_id"],
        source="template_tone_evaluations",
    )


@router.post("/apply/{session_id}", response_model=ToneApplyResponse)
async def apply_tone(
    session_id: str,
    body: ToneApplyRequest | None = None,
    session_state: dict[str, Any] = Depends(require_session),
) -> ToneApplyResponse:
    pending = session_state.get("pending_suggestions") or session_state.get("suggestions") or []
    if not pending:
        return ToneApplyResponse(
            applied=0,
            keys=[],
            message="No pending suggestions to apply.",
        )

    filter_keys = {key.upper() for key in body.keys} if body and body.keys else None
    selected = [
        item
        for item in pending
        if filter_keys is None or item.get("key", "").upper() in filter_keys
    ]
    if not selected:
        return ToneApplyResponse(
            applied=0,
            keys=[],
            message="No pending suggestions to apply.",
        )

    try:
        result = await apply_tone_suggestions(selected, session_state)
    except Exception as exc:
        raise api_error(500, "ApplyFailed", f"Failed to apply tone suggestions: {exc}") from exc

    applied_keys = [item.get("key", "") for item in selected if item.get("key")]
    update_session_state(
        session_id,
        {"pending_suggestions": [], "suggestions": []},
    )

    return ToneApplyResponse(
        applied=result.get("applied", len(selected)),
        keys=applied_keys,
        message=result.get("message", f"Applied {len(selected)} tone rewrite(s)."),
    )


@router.post("/undo/{session_id}", response_model=ToneUndoResponse)
async def undo_tone(
    session_id: str,
    body: ToneUndoRequest | None = None,
    session_state: dict[str, Any] = Depends(require_session),
) -> ToneUndoResponse:
    del session_id
    keys = body.keys if body else None
    result = await undo_tone_suggestions(keys, session_state)
    return ToneUndoResponse(
        restored=result["restored"],
        message=result["message"],
        snapshot_cleared=result["snapshot_cleared"],
    )
