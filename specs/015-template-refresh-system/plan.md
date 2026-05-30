# Implementation Plan: [FEATURE]

**Branch**: `015-template-refresh-system` | **Date**: 2026-05-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-template-refresh-system/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build a background refresh system for the StrongMail Agent Studio FastAPI backend. This system allows administrators to trigger re-extraction of StrongMail content — either for a single named template or for the entire database — without restarting the server, and to monitor progress in real time via Server-Sent Events.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Redis, psycopg3, asyncpg, pytest, pytest-asyncio

**Storage**: PostgreSQL (via existing extraction pipeline), Redis (for job state, locks, and progress events)

**Testing**: pytest + pytest-asyncio, real Redis (no mocks), mock sync job functions.

**Target Platform**: Linux server (backend)

**Project Type**: web-service (FastAPI backend subsystem)

**Performance Goals**: Jobs run in background thread pool (`max_workers=2`) without blocking FastAPI event loop.

**Constraints**: `template_refresh` and `full_refresh` must use synchronous DB connections. `resolve_linked_blocks` must use asyncpg. Note: `psycopg3` is used only inside thread context (by pipeline functions). `asyncpg` is used only in the FastAPI async context (by `linked_blocks.py` only).

**Scale/Scope**: Handles single template refreshes and full system refreshes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Passed. No specific constitution rules violated.

## Project Structure

### Documentation (this feature)

```text
specs/015-template-refresh-system/
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
├── main.py
├── state.py
├── routers/
│   └── refresh.py
└── refresh/
    ├── __init__.py
    ├── job_registry.py
    ├── job_runner.py
    ├── locks.py
    ├── progress.py
    ├── template_refresh.py
    ├── full_refresh.py
    └── linked_blocks.py

tests/
└── api/
    └── refresh/
        ├── test_job_registry.py
        ├── test_locks.py
        ├── test_progress.py
        ├── test_linked_blocks.py
        └── test_refresh_integration.py
```

**Structure Decision**: Added a new `refresh` subsystem package under `api/` to encapsulate the background job logic, state management, and locking. Added a new router `refresh.py` under `api/routers/`. Added corresponding tests under `tests/api/refresh/`.

## Implementation Details

### Thread Executor in `api/state.py`
- Add `refresh_executor = ThreadPoolExecutor(max_workers=2)` to `api/state.py`.
- Add `refresh_executor.shutdown(wait=False)` to the lifespan teardown in `api/main.py`.

### Contracts

- `linked_blocks.py` is the only module permitted to use `asyncpg` or the shared `db_pool` from `api.state`.
- `template_refresh.py` and `full_refresh.py` must never import `asyncpg`.
- Only `job_registry.py` reads and writes `refresh-job:{job_id}` hash keys.
- Only `locks.py` reads and writes `refresh-lock:*` keys.
- `progress.py` reads `refresh-job:{job_id}:progress` list; it never writes to the job hash.
- `api/routers/refresh.py` calls `job_registry`, `locks`, `progress`, and `job_runner` only; it never accesses Redis directly.

### Startup Orphan Check
- In `api/main.py` lifespan startup, after Redis initialization, call `api.refresh.job_registry.mark_orphaned_jobs_failed(redis_client)`.
- This function scans for any `refresh-job:*` hash keys with `status="running"` and sets them to failed with `error="Server restarted mid-job"`, then releases their locks.

### SSE Polling
- `GET /refresh/stream/{job_id}` uses `StreamingResponse` with `media_type="text/event-stream"` and headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- The async generator first calls `replay_events()` to yield all buffered events, then polls `tail_events()` with `asyncio.sleep(0.25)` between polls.

### Pipeline Integration
- `template_refresh.py` and `full_refresh.py` import from the existing extraction pipeline modules.
- Both sync job functions accept an `env` dict containing `STRONGMAIL_PASSWORD`, `STRONGMAIL_ORG_ID`, `STRONGMAIL_USERNAME`, and `DATABASE_URL` — sourced from `os.environ` at the moment the endpoint is called.
- They call the existing pipeline step functions with `force_upsert=True`.
- They do NOT reimplement Playwright login, grid fetching, jsonedit interception, edit.do parsing, or rule DSL parsing. Reimplementing any extraction logic is explicitly forbidden.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
