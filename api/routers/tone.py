from __future__ import annotations

import asyncio
import csv
import io
import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from openpyxl import Workbook

from api.errors import api_error
from api.helpers import update_session_state
from api.middleware.session_guard import require_session
from api import state
from api.models.requests import ToneApplyRequest, ToneEvaluateRequest, ToneUndoRequest
from api.models.responses import (
    ToneApplyResponse,
    ToneEvaluateResponse,
    ToneReevaluateResponse,
    ToneStoredResponse,
    ToneUndoResponse,
)
from api.services.preview import build_preview
from api.tone_batch.batch_tone import (
    LANG_LOCAL,
    MODEL_ID,
    PARAM_CUST_BRAND,
    build_warning,
    classify_text,
    top_emotion_scores,
    upsert_tone_evaluation_sync,
)
from shared.db import get_pool
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import resolve_body
from template_assistant.context import SessionContext
from template_assistant.ml.goemotions import scores_from_pipeline_result
from template_assistant.services import resolve_template
from template_assistant.subagents.tone_evaluation_subagent import (
    evaluate_tone,
    normalize_stored_tones,
)
from template_assistant.subagents.tone_suggestion_subagent import apply_tone_suggestions, undo_tone_suggestions
from template_assistant.utils.text import extract_plain_text

router = APIRouter(prefix="/tone", tags=["tone"])

_SUBJECT_TOKEN_PATTERN = re.compile(r"##[^#]+##")


def _strip_warning_from_tones(tones: dict[str, Any]) -> tuple[dict[str, float], str | None]:
    warning = tones.get("_warning")
    emotions = {
        str(k): float(v)
        for k, v in tones.items()
        if k != "_warning" and isinstance(v, (int, float))
    }
    warning_str = str(warning) if warning is not None else None
    return emotions, warning_str


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def _resolve_subject(
    template_name: str,
    subject: str | None,
) -> str:
    if not subject:
        return ""
    if not _SUBJECT_TOKEN_PATTERN.search(subject):
        return subject

    pool = get_pool()
    graph = await build_resolution_graph(pool, template_name)
    context = {"LANG_LOCAL": LANG_LOCAL, "PARAM_CUST_BRAND": PARAM_CUST_BRAND}
    result = await resolve_body(
        pool,
        state.redis_client,
        graph,
        subject,
        context,
        "tone-export",
        template_name,
    )
    if not result.unresolvable:
        return result.resolved_body
    return subject


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

    session_context = SessionContext(
        template_name=str(session_state["template_name"]),
        lang_local=str(session_state["lang_local"]),
        param_cust_brand=str(session_state["param_cust_brand"]),
        session_id=str(session_state["session_id"]),
    )
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
        plain_text=plain_text,
        plain_text_length=len(plain_text),
        warning=warning,
    )


@router.post("/reevaluate/{template_name}", response_model=ToneReevaluateResponse)
async def reevaluate_template_tone(template_name: str) -> ToneReevaluateResponse:
    if state.classifier is None:
        raise api_error(
            503,
            "ModelNotReady",
            "GoEmotions classifier is still loading. Retry in a few seconds.",
        )

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

    session_context = SessionContext(
        template_name=template_name,
        lang_local=LANG_LOCAL,
        param_cust_brand=PARAM_CUST_BRAND,
        session_id="tone-reevaluate",
    )
    try:
        resolution = await resolve_template(session_context)
    except ValueError as exc:
        raise api_error(404, "TemplateNotFound", str(exc)) from exc

    plain_text = extract_plain_text(resolution.resolved_body)
    warning = build_warning(plain_text=plain_text, unresolvable=resolution.unresolvable)
    scores = classify_text(state.classifier, plain_text)
    tones = top_emotion_scores(scores, top_n=3)
    if warning:
        tones["_warning"] = warning

    template_id = template_row["id"]
    database_url = __import__("os").environ.get("DATABASE_URL", "")

    def _upsert() -> None:
        import psycopg

        with psycopg.connect(database_url) as conn:
            upsert_tone_evaluation_sync(conn, template_id=template_id, tones=tones)

    await asyncio.get_running_loop().run_in_executor(state.refresh_executor, _upsert)

    emotions, warning_value = _strip_warning_from_tones(tones)
    return ToneReevaluateResponse(
        template_name=template_name,
        emotions=emotions,
        model=MODEL_ID,
        evaluated_at=_now_iso(),
        warning=warning_value,
    )


@router.get("/export")
async def export_tone_evaluations(
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
) -> Response:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.name, td.subject, td.summary, tte.tones
            FROM template t
            JOIN template_details td ON td.template_id = t.id
            JOIN template_tone_evaluations tte ON tte.template_id = t.id
            WHERE UPPER(tte.lang_local) = UPPER($1)
              AND UPPER(tte.param_cust_brand) = UPPER($2)
            ORDER BY t.name
            """,
            LANG_LOCAL,
            PARAM_CUST_BRAND,
        )

    export_rows: list[list[str | float]] = []
    headers = [
        "NAME",
        "SUBJECT",
        "SUMMARY",
        "TONE_1",
        "SCORE_1",
        "TONE_2",
        "SCORE_2",
        "TONE_3",
        "SCORE_3",
        "WARNING",
    ]

    subjects_to_resolve = {
        row["name"]: row["subject"]
        for row in rows
        if row["subject"] and _SUBJECT_TOKEN_PATTERN.search(row["subject"])
    }
    resolved_subjects: dict[str, str] = {}
    for name, subject in subjects_to_resolve.items():
        resolved_subjects[name] = await _resolve_subject(name, subject)

    for row in rows:
        raw_tones = row["tones"]
        if isinstance(raw_tones, str):
            raw_tones = json.loads(raw_tones)
        tones_dict = dict(raw_tones or {})
        warning = tones_dict.pop("_warning", "") or ""
        sorted_emotions = sorted(
            ((str(k), float(v)) for k, v in tones_dict.items() if isinstance(v, (int, float))),
            key=lambda item: item[1],
            reverse=True,
        )
        top3 = sorted_emotions[:3]
        while len(top3) < 3:
            top3.append(("", 0.0))

        subject = row["subject"] or ""
        if row["name"] in resolved_subjects:
            subject = resolved_subjects[row["name"]]

        export_rows.append(
            [
                row["name"],
                subject,
                row["summary"] or "",
                top3[0][0],
                top3[0][1],
                top3[1][0],
                top3[1][1],
                top3[2][0],
                top3[2][1],
                str(warning),
            ]
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    if format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Tone Evaluations"
        sheet.append(headers)
        for export_row in export_rows:
            sheet.append(export_row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        content = buffer.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"tone_evaluations_{timestamp}.xlsx"
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(export_rows)
        content = buffer.getvalue().encode("utf-8")
        media_type = "text/csv"
        filename = f"tone_evaluations_{timestamp}.csv"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stored/{session_id}", response_model=ToneStoredResponse)
async def get_stored_tone(
    session_id: str,
    session_state: dict[str, Any] = Depends(require_session),
) -> ToneStoredResponse:
    del session_id
    session_context = SessionContext(
        template_name=str(session_state["template_name"]),
        lang_local=str(session_state["lang_local"]),
        param_cust_brand=str(session_state["param_cust_brand"]),
        session_id=str(session_state["session_id"]),
    )
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
