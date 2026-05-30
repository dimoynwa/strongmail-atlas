# Implementation Plan: Tone Batch Operations

**Branch**: `016-tone-batch-operations` | **Date**: 2026-05-30 | **Spec**: specs/016-tone-batch-operations/spec.md

## Summary

This plan outlines the technical design for Spec 016 — Tone Batch Operations. It adds a `plain_text` response field to the existing single-session evaluate endpoint, introduces a session-independent single-template reevaluate endpoint, creates a batch tone job system mirroring the existing refresh jobs, and provides an endpoint to export tone evaluation results as CSV or Excel.

## Technical Context

**Language/Version**: Python (FastAPI backend)

**Primary Dependencies**: FastAPI, psycopg3 (sync), asyncpg (async), redis-py, trafilatura, openpyxl, stdlib csv.

**Storage**: PostgreSQL (template_tone_evaluations table), Redis (locks and job state)

**Testing**: pytest, pytest-asyncio (real PostgreSQL and Redis)

**Project Type**: Backend API extension

**Constraints**:
- The batch system MUST share the existing `ThreadPoolExecutor` (`refresh_executor` in `api/state.py`). A second executor MUST NOT be created.
- The `api/tone_batch/models.py` MUST import `ProgressEvent` from `api.refresh.models` instead of redefining it.
- Single global lock (`tone-lock:batch`) for the batch tone job MUST be fully isolated from refresh locks (`refresh-lock:*`).
- **Idempotency**: The `/tone/reevaluate` endpoint MUST be idempotent. Calling it twice for the same `template_name` must produce the same DB row using an upsert (ON CONFLICT DO UPDATE), rather than an insert.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
Since `constitution.md` has no specific gates or rules that are violated by this pure backend addition, this gate passes.

## Async/Sync Boundary

  FastAPI async context
    │
    ├── resolve_template / build_graph — asyncpg, db_pool (reads only)
    ├── export query — asyncpg, db_pool (read only)
    ├── /tone/reevaluate DB write — asyncio.get_event_loop().run_in_executor(
    │       state.refresh_executor, _upsert_tone_sync, ...)
    │
    └── loop.run_in_executor(state.refresh_executor, run_batch_tone_job, ...)
              │
              └── Thread context (sync only)
                      └── batch_tone.run_batch_tone_job()
                              ├── psycopg3 sync connections for DB writes
                              └── state.classifier for GoEmotions (thread-safe read). MUST receive `state.classifier` directly as an argument from the async caller, rather than calling `get_classifier()` itself, to avoid redundant model load checks inside the thread.

## Startup Changes

`api/main.py` lifespan handler gains:
```python
from api.tone_batch.job_registry import mark_orphaned_tone_jobs_failed
...
mark_orphaned_tone_jobs_failed(state.redis_client)   # after existing orphan check
```

## Batch Job Progress Events

- step "load_templates": `step_start` → (load) → `step_done` with `count=N`
- step "resolve_and_evaluate": `step_start` → `item_done` per template (`count=i`, `total=N`) → `step_done` / `step_error` per failed template (continue, don't abort)
- step "store_results": `step_start` → `step_done` with `count=upserted`
- final: `job_done` or `job_failed`

## Export Implementation Notes

- Single SQL query (no N+1): JOIN `template` + `template_details` + `template_tone_evaluations` WHERE `lang_local='EN'` AND `param_cust_brand='SKRILL'`
- SUBJECT resolution: after the query, resolve subjects that contain `##...##` tokens using `build_graph` + `resolve_key` per template (`asyncpg`). This MUST use graph resolution only and MUST NOT use a working copy (no Redis). Batch this — do not open a separate connection per template.
- WARNING extraction: `tones_jsonb.get("_warning", "")` — done in Python after fetch.
- `openpyxl` for xlsx; stdlib `csv` module for csv.
- Streaming response not required — buffer full result in memory then return.

## Locking Response

The locking response strictly matches the refresh pattern.
202 on success:
```json
{
  "job_id": "tone-20260530143022-a3f7c912",
  "status": "pending"
}
```
409 on conflict:
```json
{
  "job_id": null,
  "status": "blocked",
  "locked_by": "tone-20260530143000-b1e2f345"
}
```

## Project Structure

### Documentation (this feature)

```text
specs/016-tone-batch-operations/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
api/
├── routers/
│   ├── tone.py              ← MODIFIED (extend evaluate response + add reevaluate + export)
│   └── tone_batch.py        ← NEW (4 batch endpoints)
└── tone_batch/
    ├── __init__.py
    ├── models.py            ← ToneJob dataclass, ToneJobStatus Literal, ProgressEvent reuse from refresh/models.py (import, not copy)
    ├── job_registry.py      ← create_tone_job, update_tone_job, get_tone_job_status, list_active_tone_jobs, set_tone_job_ttl, mark_orphaned_tone_jobs_failed
    ├── locks.py             ← acquire_tone_lock, release_tone_lock, is_tone_locked, get_tone_lock_holder (key: tone-lock:batch, TTL 2h)
    ├── progress.py          ← emit_tone_event, replay_tone_events, tail_tone_events (operates on tone-job:{job_id}:progress list)
    ├── job_runner.py        ← submit_tone_job() — uses api/state.refresh_executor
    └── batch_tone.py        ← run_batch_tone_job() sync function — psycopg3, never asyncpg, never state.db_pool

tests/
└── api/
    └── tone_batch/
        ├── test_job_registry.py
        ├── test_locks.py            ← MUST include a test verifying lock isolation between tone-lock:batch and refresh-lock:* (acquiring one must not affect the other)
        ├── test_progress.py
        ├── test_job_runner.py
        ├── test_batch_tone_integration.py
        ├── test_tone_reevaluate.py
        ├── test_tone_evaluate_plain_text.py
        └── test_tone_export.py
```

**Structure Decision**: The source code changes are tightly isolated inside the FastAPI app (`api/`). The batch logic gets its own `api/tone_batch` module modeled after `api/refresh`. Router definitions are cleanly separated, and tests follow the same structure.
