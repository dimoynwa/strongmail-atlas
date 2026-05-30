from __future__ import annotations

from datetime import UTC, datetime

from api.refresh import job_registry, locks, progress
from api.refresh.pipeline_bridge import apply_env, get_responses_dir


def _finish_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_full_refresh_job(*, job_id: str, env: dict[str, str]) -> None:
    apply_env(env)
    job_registry.update(job_id, status="running")

    try:
        from strongmail_pipeline import ExtractionContext, ExtractionPipeline
        from strongmail_pipeline.steps import (
            BackfillBodyPlaceholderKeysStep,
            EvaluateTemplateTonesStep,
            FetchContentBlocksListStep,
            FetchContentBlocksRawStep,
            FetchDynamicContentPreviewsStep,
            FetchDynamicContentStep,
            FetchTemplatesListStep,
            FetchTemplatesRawStep,
            LogPipelineStartStep,
            SummarizeEmbedTemplatesStep,
        )

        responses = get_responses_dir()
        templates_out = responses / "templates.json"
        content_blocks_out = responses / "content_blocks.json"
        dynamic_json = responses / "dynamic_content.json"

        pipeline = ExtractionPipeline(
            [
                LogPipelineStartStep(),
                FetchTemplatesListStep(output_path=templates_out, headless=True),
                FetchContentBlocksListStep(output_path=content_blocks_out, headless=True),
                FetchDynamicContentStep(output_json_path=dynamic_json, headless=True),
                FetchDynamicContentPreviewsStep(
                    rules_json_path=dynamic_json,
                    headless=True,
                    skip_existing=False,
                ),
                FetchTemplatesRawStep(
                    templates_json_path=templates_out,
                    headless=True,
                    skip_existing=False,
                ),
                FetchContentBlocksRawStep(headless=True, skip_existing=False),
                EvaluateTemplateTonesStep(
                    batch_size=16,
                    tone_fill_missing=False,
                    tone_refresh_existing=True,
                ),
                SummarizeEmbedTemplatesStep(
                    batch_size=32,
                    fill_missing=False,
                    refresh_all=True,
                ),
                BackfillBodyPlaceholderKeysStep(),
            ]
        )

        steps = [
            ("fetch_templates_list", "Fetching templates list…"),
            ("fetch_content_blocks_list", "Fetching content blocks list…"),
            ("fetch_dynamic_rules_list", "Fetching dynamic rules list…"),
            ("fetch_dynamic_rule_previews", "Fetching dynamic rule previews…"),
            ("fetch_templates_raw", "Fetching template bodies…"),
            ("fetch_content_blocks_raw", "Fetching content block bodies…"),
            ("evaluate_all_tones", "Evaluating all template tones…"),
            ("embed_all_summaries", "Embedding all template summaries…"),
            ("backfill_placeholder_keys", "Backfilling placeholder keys…"),
        ]

        ctx = ExtractionContext(backfill_body_placeholder_keys=True)
        for step_name, message in steps:
            progress.emit_event(job_id, "step_start", message, step=step_name)

        ctx = pipeline.run(ctx)

        for step_name, _message in steps:
            progress.emit_event(job_id, "step_done", f"{step_name} complete", step=step_name)

        job_registry.update(job_id, status="done", finished_at=_finish_iso())
        progress.emit_event(job_id, "job_done", "Full refresh complete")
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
        locks.release_lock("full")
