from __future__ import annotations

import json
import os
import re
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

from api.tone_batch import job_registry, locks, progress
from shared.resolution.resolver import PLACEHOLDER_PATTERN, ReasonCode, UnresolvableEntry
from shared.resolution.rule_parser import parse_rule_to_ast
from shared.resolution.namespace import normalize_key
from shared.resolution.preprocessors import (
    is_synthetic_context_key,
    parameters_get_ci,
    preprocess_key,
)
from shared.resolution.sm_rule_evaluator import _evaluate_condition, _normalize_return_value
from template_assistant.ml.goemotions import scores_from_pipeline_result
from template_assistant.services import select_reachability_body
from template_assistant.utils.text import extract_plain_text

LANG_LOCAL = "EN"
PARAM_CUST_BRAND = "SKRILL"
MODEL_ID = "goemotions"
MIN_TEXT_CHARS = 20


@dataclass(frozen=True)
class TemplateRow:
    template_id: str
    template_name: str
    html: str
    text: str


def _finish_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolution_context() -> dict[str, str]:
    return {"LANG_LOCAL": LANG_LOCAL, "PARAM_CUST_BRAND": PARAM_CUST_BRAND}


def _lookup_context_value(expanded: str, context: dict[str, str]) -> str | None:
    value = parameters_get_ci(context, expanded)
    if value is None or value == "":
        return None
    return value


def _evaluate_sm_rule_sync(
    conn: psycopg.Connection,
    rule_name: str,
    context: dict[str, str],
) -> str | ReasonCode:
    full_key = rule_name if rule_name.startswith("SM_RULE_") else f"SM_RULE_{rule_name}"
    stripped_name = full_key[8:]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dcd.rule_text
            FROM dynamic_content d
            JOIN dynamic_content_details dcd ON dcd.dynamic_content_id = d.id
            WHERE d.name = %s OR d.name = %s
            ORDER BY (d.name = %s) DESC
            LIMIT 1
            """,
            (stripped_name, full_key, stripped_name),
        )
        row = cur.fetchone()

    if row is None:
        return ReasonCode.MISSING_KEY

    rule_text = row[0]
    if rule_text is None or not str(rule_text).strip():
        return ReasonCode.INVALID_RULE

    ast = parse_rule_to_ast(str(rule_text))
    if not ast.get("valid", False):
        return ReasonCode.INVALID_RULE

    condition = ast.get("condition", {})
    is_true = _evaluate_condition(condition, context)
    branch_val = ast.get("then") if is_true else ast.get("else")
    if branch_val is None:
        return ""
    return _normalize_return_value(branch_val) or ""


def _resolve_node_sync(
    raw_key: str,
    conn: psycopg.Connection,
    graph: types.MappingProxyType[str, str],
    context: dict[str, str],
    visiting: list[str],
    unresolvable: list[UnresolvableEntry],
    resolved_keys: set[str] | None = None,
) -> str | None:
    canonical = normalize_key(raw_key)
    expanded = preprocess_key(canonical, context)

    if resolved_keys is not None:
        resolved_keys.add(expanded)

    if is_synthetic_context_key(expanded) and expanded in context:
        return context[expanded]

    if expanded in visiting:
        cycle_path = visiting + [expanded]
        unresolvable.append(
            UnresolvableEntry(expanded, ReasonCode.CYCLE, " → ".join(cycle_path))
        )
        return None

    visiting.append(expanded)
    try:
        val = graph.get(expanded)
        if val is None:
            if expanded.startswith("SM_RULE_"):
                sm_rule_count = sum(1 for v in visiting if v.startswith("SM_RULE_"))
                if sm_rule_count > 10:
                    unresolvable.append(
                        UnresolvableEntry(expanded, ReasonCode.CYCLE, "SM_RULE chain > 10 hops")
                    )
                    return None
                res = _evaluate_sm_rule_sync(conn, expanded, context)
                if isinstance(res, ReasonCode):
                    if res == ReasonCode.MISSING_KEY:
                        unresolvable.append(
                            UnresolvableEntry(expanded, ReasonCode.MISSING_KEY, "Rule not found")
                        )
                    elif res == ReasonCode.INVALID_RULE:
                        unresolvable.append(
                            UnresolvableEntry(expanded, ReasonCode.INVALID_RULE, "Invalid rule AST")
                        )
                    return None
                val = res
                if val.startswith("SM_RULE_") or re.match(r"^[A-Z0-9_.]+$", val):
                    resolved_val = _resolve_node_sync(
                        val,
                        conn,
                        graph,
                        context,
                        visiting,
                        unresolvable,
                        resolved_keys,
                    )
                    if resolved_val is None:
                        unresolvable.append(
                            UnresolvableEntry(
                                expanded,
                                ReasonCode.BROKEN_RULE_CHAIN,
                                f"Target key {val} missing",
                            )
                        )
                        return None
                    return resolved_val
            else:
                context_val = _lookup_context_value(expanded, context)
                if context_val is not None:
                    val = context_val
                else:
                    unresolvable.append(
                        UnresolvableEntry(
                            expanded,
                            ReasonCode.MISSING_KEY,
                            "Missing key in graph",
                        )
                    )
                    return None

        result_parts: list[str] = []
        last_index = 0
        for match in PLACEHOLDER_PATTERN.finditer(val):
            result_parts.append(val[last_index : match.start()])
            inner_resolved = _resolve_node_sync(
                match.group(0),
                conn,
                graph,
                context,
                visiting,
                unresolvable,
                resolved_keys,
            )
            if inner_resolved is not None:
                result_parts.append(inner_resolved)
            else:
                result_parts.append(match.group(0))
            last_index = match.end()
        result_parts.append(val[last_index:])
        return "".join(result_parts)
    finally:
        visiting.pop()


def _resolve_body_sync(
    conn: psycopg.Connection,
    graph: types.MappingProxyType[str, str],
    body: str,
    context: dict[str, str],
    accumulated_keys: set[str] | None = None,
) -> tuple[str, list[UnresolvableEntry]]:
    unresolvable: list[UnresolvableEntry] = []
    resolved_keys = accumulated_keys if accumulated_keys is not None else set()
    result_parts: list[str] = []
    last_index = 0
    for match in PLACEHOLDER_PATTERN.finditer(body):
        result_parts.append(body[last_index : match.start()])
        resolved_val = _resolve_node_sync(
            match.group(0),
            conn,
            graph,
            context,
            [],
            unresolvable,
            resolved_keys,
        )
        if resolved_val is not None:
            result_parts.append(resolved_val)
        else:
            result_parts.append(match.group(0))
        last_index = match.end()
    result_parts.append(body[last_index:])
    return "".join(result_parts), unresolvable


def _build_graph_sync(conn: psycopg.Connection, template_name: str) -> types.MappingProxyType[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM template WHERE name = %s", (template_name,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Template not found: {template_name!r}")
        cur.execute(
            """
            SELECT DISTINCT ON (kv.field_key) kv.field_key, kv.field_value
            FROM template t
            JOIN template_content_block tcb ON tcb.template_id = t.id
            JOIN content_block cb ON cb.id = tcb.content_block_id
            JOIN content_block_details cbd ON cbd.content_block_id = cb.id
            JOIN content_block_kv kv ON kv.content_block_details_id = cbd.id
            WHERE t.name = %s
            ORDER BY kv.field_key, cbd.id ASC
            """,
            (template_name,),
        )
        rows = cur.fetchall()
    graph_dict = {field_key.upper(): field_value for field_key, field_value in rows}
    return types.MappingProxyType(graph_dict)


def _load_templates_sync(conn: psycopg.Connection) -> list[TemplateRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.name, COALESCE(td.html, ''), COALESCE(td.text, '')
            FROM template t
            JOIN template_details td ON td.template_id = t.id
            ORDER BY t.name
            """
        )
        rows = cur.fetchall()
    return [
        TemplateRow(template_id=row[0], template_name=row[1], html=row[2], text=row[3])
        for row in rows
    ]


def build_warning(*, plain_text: str, unresolvable: list[UnresolvableEntry]) -> str | None:
    parts: list[str] = []
    if len(plain_text) < MIN_TEXT_CHARS:
        parts.append("no_meaningful_text")
    if unresolvable:
        parts.append("unresolvable_keys")
    return ",".join(parts) if parts else None


def top_emotion_scores(scores: dict[str, float], *, top_n: int = 3) -> dict[str, float]:
    return dict(sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n])


def classify_text(classifier: Any, plain_text: str) -> dict[str, float]:
    if not plain_text:
        return {}
    raw_scores = classifier(plain_text)
    if isinstance(raw_scores, list) and raw_scores and isinstance(raw_scores[0], list):
        return scores_from_pipeline_result(raw_scores[0])
    return scores_from_pipeline_result(raw_scores)


def evaluate_template_sync(
    conn: psycopg.Connection,
    template: TemplateRow,
    classifier: Any,
) -> dict[str, Any]:
    graph = _build_graph_sync(conn, template.template_name)
    context = _resolution_context()
    body = select_reachability_body(template.html, template.text)
    accumulated_keys: set[str] = set()
    resolved_body, unresolvable = _resolve_body_sync(
        conn,
        graph,
        body,
        context,
        accumulated_keys=accumulated_keys,
    )
    plain_text = extract_plain_text(resolved_body)
    warning = build_warning(plain_text=plain_text, unresolvable=unresolvable)
    scores = classify_text(classifier, plain_text)
    tones = top_emotion_scores(scores, top_n=3)
    if warning:
        tones["_warning"] = warning
    return tones


def upsert_tone_evaluation_sync(
    conn: psycopg.Connection,
    *,
    template_id: str,
    tones: dict[str, Any],
) -> None:
    tones_json = json.dumps({str(k): v for k, v in tones.items()})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO template_tone_evaluations
                (template_id, model_id, lang_local, param_cust_brand, tones, evaluated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (template_id, model_id, lang_local, param_cust_brand)
            DO UPDATE SET
                tones = EXCLUDED.tones,
                evaluated_at = EXCLUDED.evaluated_at
            """,
            (template_id, MODEL_ID, LANG_LOCAL, PARAM_CUST_BRAND, tones_json),
        )
    conn.commit()


def run_batch_tone_job(*, job_id: str, env: dict[str, str], classifier: Any) -> None:
    for key, value in env.items():
        if value:
            os.environ[key] = value

    database_url = env.get("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    job_registry.update_tone_job(job_id, status="running")

    try:
        progress.emit_tone_event(job_id, "step_start", "Loading templates…", step="load_templates")
        with psycopg.connect(database_url) as conn:
            templates = _load_templates_sync(conn)
            progress.emit_tone_event(
                job_id,
                "step_done",
                f"Loaded {len(templates)} template(s)",
                step="load_templates",
                count=len(templates),
            )

            progress.emit_tone_event(
                job_id,
                "step_start",
                "Resolving and evaluating templates…",
                step="resolve_and_evaluate",
            )
            results: list[tuple[str, dict[str, Any]]] = []
            total = len(templates)
            for index, template in enumerate(templates, start=1):
                try:
                    tones = evaluate_template_sync(conn, template, classifier)
                    results.append((template.template_id, tones))
                    progress.emit_tone_event(
                        job_id,
                        "item_done",
                        f"Evaluated {template.template_name!r}",
                        step="resolve_and_evaluate",
                        count=index,
                        total=total,
                    )
                except Exception as exc:
                    progress.emit_tone_event(
                        job_id,
                        "step_error",
                        f"{template.template_name}: {exc}",
                        step="resolve_and_evaluate",
                        count=index,
                        total=total,
                    )

            progress.emit_tone_event(
                job_id,
                "step_done",
                f"Evaluated {len(results)} template(s)",
                step="resolve_and_evaluate",
                count=len(results),
                total=total,
            )

            progress.emit_tone_event(job_id, "step_start", "Storing results…", step="store_results")
            upserted = 0
            for template_id, tones in results:
                upsert_tone_evaluation_sync(conn, template_id=template_id, tones=tones)
                upserted += 1
            progress.emit_tone_event(
                job_id,
                "step_done",
                f"Stored {upserted} evaluation(s)",
                step="store_results",
                count=upserted,
            )

        job_registry.update_tone_job(job_id, status="done", finished_at=_finish_iso())
        progress.emit_tone_event(job_id, "job_done", "Batch tone evaluation complete")
    except Exception as exc:
        job_registry.update_tone_job(
            job_id,
            status="failed",
            finished_at=_finish_iso(),
            error=str(exc),
        )
        progress.emit_tone_event(job_id, "job_failed", str(exc))
        raise
    finally:
        locks.release_tone_lock()
