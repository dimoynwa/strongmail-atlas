from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from api.refresh import job_registry, locks, progress
from api.refresh.models import LinkedBlocksResult
from api.refresh.pipeline_bridge import apply_env, get_responses_dir


def _finish_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _emit_step(
    job_id: str,
    step: str,
    message: str,
    runner: Callable[[], None],
) -> None:
    progress.emit_event(job_id, "step_start", message, step=step)
    try:
        runner()
    except Exception as exc:
        progress.emit_event(
            job_id,
            "step_error",
            f"{step} failed: {exc}",
            step=step,
        )
        raise
    progress.emit_event(job_id, "step_done", f"{step} complete", step=step)


def run_template_refresh_job(
    *,
    job_id: str,
    env: dict[str, str],
    template_name: str,
    linked: LinkedBlocksResult,
) -> None:
    apply_env(env)
    job_registry.update(job_id, status="running")

    try:
        from strongmail_pipeline import ExtractionContext
        from strongmail_pipeline.database import DatabaseManager
        from strongmail_pipeline.steps import (
            EvaluateTemplateTonesStep,
            FetchContentBlocksRawStep,
            FetchDynamicContentPreviewsStep,
            FetchTemplatesListStep,
            FetchTemplatesRawStep,
            SummarizeEmbedTemplatesStep,
        )

        responses = get_responses_dir()
        templates_out = responses / "templates.json"
        dynamic_json = responses / "dynamic_content.json"
        template_id = linked.template_id
        skip_tone = os.environ.get("PIPELINE_SKIP_TONE", "").lower() in ("1", "true", "yes")
        skip_summary = os.environ.get("PIPELINE_SKIP_SUMMARY_EMBED", "").lower() in (
            "1",
            "true",
            "yes",
        )

        ctx = ExtractionContext(
            force_template_ids=[template_id],
            skip_evaluate_template_tones=skip_tone,
            skip_summarize_template_embeddings=skip_summary,
        )

        def _fetch_template_body() -> None:
            FetchTemplatesListStep(output_path=templates_out, headless=True).run(ctx)
            FetchTemplatesRawStep(
                templates_json_path=templates_out,
                headless=True,
                skip_existing=False,
            ).run(ctx)

        def _fetch_content_blocks() -> None:
            FetchContentBlocksRawStep(headless=True, skip_existing=False).run(ctx)

        def _fetch_dynamic_rules() -> None:
            if not linked.rule_ids:
                ctx.state["dynamic_content_details_upserted"] = 0
                return
            db = DatabaseManager()
            rules: list[dict] = []
            for rule_id in linked.rule_ids:
                row = db.get_dynamic_content(rule_id)
                if row is not None:
                    rules.append({"id": rule_id, "name": row.name})
                else:
                    rules.append({"id": rule_id, "name": rule_id})
            ctx.state["dynamic_content_rules"] = rules
            FetchDynamicContentPreviewsStep(
                rules_json_path=dynamic_json,
                headless=True,
                skip_existing=False,
            ).run(ctx)

        def _evaluate_tone() -> None:
            EvaluateTemplateTonesStep(
                batch_size=16,
                tone_fill_missing=False,
                tone_refresh_existing=True,
            ).run(ctx)

        def _embed_summary() -> None:
            SummarizeEmbedTemplatesStep(
                batch_size=32,
                fill_missing=False,
                refresh_all=False,
            ).run(ctx)

        _emit_step(
            job_id,
            "fetch_template_body",
            f"Fetching template body for {template_name!r}…",
            _fetch_template_body,
        )
        _emit_step(
            job_id,
            "fetch_content_blocks",
            f"Fetching linked content blocks for {template_name!r}…",
            _fetch_content_blocks,
        )
        _emit_step(
            job_id,
            "fetch_dynamic_rules",
            f"Fetching dynamic rules for {template_name!r}…",
            _fetch_dynamic_rules,
        )
        if not skip_tone:
            _emit_step(
                job_id,
                "evaluate_tone",
                f"Evaluating tone for {template_name!r}…",
                _evaluate_tone,
            )
        if not skip_summary:
            _emit_step(
                job_id,
                "embed_summary",
                f"Embedding summary for {template_name!r}…",
                _embed_summary,
            )

        job_registry.update(job_id, status="done", finished_at=_finish_iso())
        progress.emit_event(job_id, "job_done", f"Template refresh complete for {template_name!r}")
    except Exception as exc:
        job_registry.update(
            job_id,
            status="failed",
            finished_at=_finish_iso(),
            error=str(exc),
        )
        progress.emit_event(job_id, "job_failed", str(exc))
        raise
    finally:
        locks.release_lock("template", target=template_name)
        full_holder = locks.get_lock_holder("full")
        if full_holder == job_id:
            locks.release_lock("full")
