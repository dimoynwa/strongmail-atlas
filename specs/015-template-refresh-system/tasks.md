---
description: "Task list for Template Refresh System (Backend Only)"
---

# Tasks: Template Refresh System (Backend Only)

**Input**: Design documents from `/specs/015-template-refresh-system/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/contracts.md, quickstart.md

**Tests**: Tests are explicitly requested in the plan.md (pytest + pytest-asyncio, real Redis, mock sync job functions).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create `api/refresh/__init__.py` to initialize the package
- [X] T002 Update `api/state.py` to add `refresh_executor = ThreadPoolExecutor(max_workers=2)`
- [X] T003 Update `api/main.py` lifespan teardown to call `refresh_executor.shutdown(wait=False)`
- [X] T004a [P] Create `api/refresh/models.py` with all shared types and dataclasses: `JobType`, `JobStatus`, `EventType`, `RefreshJob`, `ProgressEvent`, `LinkedBlocksResult`. This is the single source of truth for all types in the refresh subsystem.
- [X] T004b Update `job_registry.py`, `locks.py`, and `progress.py` to import their types from `api/refresh/models.py`. Remove the dataclass definitions from T007's scope. (Note: T004a must complete before T005, T007, T010).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Implement `api/refresh/locks.py` with `acquire_lock`, `release_lock`, `is_locked`, and `get_lock_holder` functions using Redis SET NX EX
- [X] T006 [P] Write tests for `locks.py` in `tests/api/refresh/test_locks.py` (acquire, double-acquire blocked, release, orphan TTL expiry)
- [X] T007 [P] Implement `api/refresh/job_registry.py` functions: create, update, get_status, list_active, set_ttl
- [X] T008 [P] Write tests for `job_registry.py` in `tests/api/refresh/test_job_registry.py` (create, update status, get, list_active, ttl)
- [X] T007a Implement `mark_orphaned_jobs_failed(redis_client)` in `api/refresh/job_registry.py`. This function scans Redis for refresh-job:* keys with status="running", updates each to status="failed" with error="Server restarted mid-job", and calls locks.release_lock() for each. Depends on T007 (job_registry) and T005 (locks).
- [X] T009 Implement `api/refresh/job_runner.py` with `submit_job()` to bridge async to thread pool using `run_in_executor`
- [X] T009a [P] Write tests for `api/refresh/job_runner.py` in `tests/api/refresh/test_job_runner.py`. Verify that `submit_job()` submits to `refresh_executor` via `run_in_executor` and that the sync job function receives the correct `job_id` and `env` dict arguments.
- [X] T010 Implement `api/refresh/progress.py` with `emit_event()` to append to Redis list
- [X] T011 [P] Write tests for `progress.py` in `tests/api/refresh/test_progress.py` (emit_event)
- [X] T012 Update `api/main.py` lifespan startup to call `api.refresh.job_registry.mark_orphaned_jobs_failed(redis_client)`
- [X] T013 [P] Write integration test for orphan check in `tests/api/refresh/test_refresh_integration.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Single Template Refresh (Priority: P1) 🎯 MVP

**Goal**: Trigger a refresh for a specific template so that its content, linked blocks, rules, tone scores, and embeddings are updated immediately.

**Independent Test**: Trigger a refresh for a single template and verify that its content and related entities are updated in the database.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US1] Write test for `linked_blocks.py` in `tests/api/refresh/test_linked_blocks.py`
- [X] T015 [P] [US1] Write E2E integration test in `tests/api/refresh/test_refresh_integration.py` covering full sequence: POST /refresh/template -> GET /refresh/status -> SSE stream receives step_start / step_done / job_done events in order
- [X] T016 [P] [US1] Write integration test for 409 conflict in `tests/api/refresh/test_refresh_integration.py` verifying a second POST /refresh/template/{same_name} while the first is running returns 409 with locked_by set to the first job's job_id
- [X] T016b [P] [US1] Write integration test for job failure path in `tests/api/refresh/test_refresh_integration.py` — mock `run_template_refresh_job` to raise an exception and verify: job status becomes "failed", error field is populated, a `job_failed` event appears in the SSE stream, and the Redis lock is released.
- [X] T017 [P] [US1] Write integration test for 503 when `STRONGMAIL_PASSWORD` is unset in `tests/api/refresh/test_refresh_integration.py`

### Implementation for User Story 1

- [X] T018 [P] [US1] Implement `api/refresh/linked_blocks.py` with `resolve_linked_blocks` using `asyncpg` and `db_pool`
- [X] T019 [US1] Implement `api/refresh/template_refresh.py` with `run_template_refresh_job` sync function (depends on T018, import existing pipeline, `force_upsert=True`)
- [X] T020 [US1] Implement `POST /refresh/template/{template_name}` in `api/routers/refresh.py` (check credentials, acquire locks, resolve blocks, submit job)
- [X] T021 [US1] Register `refresh.py` router in `api/main.py` (depends on T020)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Full System Refresh (Priority: P2)

**Goal**: Trigger a full refresh of all templates and related content so that the entire database is synchronized with the source system.

**Independent Test**: Trigger a full refresh and verify that all templates, content blocks, rules, tone scores, and embeddings are updated.

### Tests for User Story 2 ⚠️

- [X] T022 [P] [US2] Write integration test for `POST /refresh/full` in `tests/api/refresh/test_refresh_integration.py` (mock job runner)
- [X] T022a [P] [US2] Write integration test for 503 when `STRONGMAIL_PASSWORD` is unset for `POST /refresh/full` in `tests/api/refresh/test_refresh_integration.py`

### Implementation for User Story 2

- [X] T023 [P] [US2] Implement `api/refresh/full_refresh.py` with `run_full_refresh_job` sync function (import existing pipeline, `force_upsert=True`)
- [X] T024 [US2] Implement `POST /refresh/full` in `api/routers/refresh.py` (check credentials, acquire lock, submit job)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Real-time Progress Monitoring (Priority: P2)

**Goal**: Monitor the progress of a running refresh job in real-time.

**Independent Test**: Subscribe to the progress stream of a running job and verify that progress events are received in order.

### Tests for User Story 3 ⚠️

- [X] T025 [P] [US3] Write tests for `replay_events` and `tail_events` in `tests/api/refresh/test_progress.py`
- [X] T026 [P] [US3] Write integration test for `GET /refresh/stream/{job_id}` in `tests/api/refresh/test_refresh_integration.py`
- [X] T026a [P] [US3] Write integration test for SSE reconnect/replay in `tests/api/refresh/test_refresh_integration.py` verifying a client connecting after the job is done receives all buffered events followed by job_done without hanging

### Implementation for User Story 3

- [X] T027 [P] [US3] Implement `replay_events()` and `tail_events()` async generators in `api/refresh/progress.py` (with 250ms polling)
- [X] T028 [US3] Implement `GET /refresh/stream/{job_id}` in `api/routers/refresh.py` using `StreamingResponse`

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: User Story 4 - Active Jobs Overview & Status (Priority: P3)

**Goal**: View a list of all currently active refresh jobs and get individual job status.

**Independent Test**: Start jobs and verify the active jobs list and individual status endpoints return correct data.

### Tests for User Story 4 ⚠️

- [X] T029 [P] [US4] Write integration test for `GET /refresh/status/{job_id}` in `tests/api/refresh/test_refresh_integration.py`. Also test that `GET /refresh/status/{unknown_job_id}` returns 404.
- [X] T030 [P] [US4] Write integration test for `GET /refresh/active` in `tests/api/refresh/test_refresh_integration.py`. Also test that `GET /refresh/active` returns `{"jobs": []}` when no jobs are running.

### Implementation for User Story 4

- [X] T031 [P] [US4] Implement `GET /refresh/status/{job_id}` in `api/routers/refresh.py`
- [X] T032 [P] [US4] Implement `GET /refresh/active` in `api/routers/refresh.py`

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T033 Validate `quickstart.md` by running each step in order against a live FastAPI + Redis + PostgreSQL environment: (1) `playwright install chromium`, (2) set all required env vars, (3) `uvicorn api.main:app --workers 1 --reload`, (4) `curl -X POST http://localhost:8000/refresh/template/password_reset_en`, (5) `curl -N http://localhost:8000/refresh/stream/{job_id}`. Update `quickstart.md` if any step fails or is unclear.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Independent from US1
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Independent from US1/US2
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) - Independent from US1/US2/US3

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Write test for linked_blocks.py in tests/api/refresh/test_linked_blocks.py"
Task: "Write integration test for POST /refresh/template/{name} in tests/api/refresh/test_refresh_integration.py"
Task: "Write integration test for 409 conflict when lock is held in tests/api/refresh/test_refresh_integration.py"
Task: "Write integration test for 503 when STRONGMAIL_PASSWORD is unset in tests/api/refresh/test_refresh_integration.py"

# Launch implementation tasks for User Story 1 together:
Task: "Implement api/refresh/linked_blocks.py with resolve_linked_blocks using asyncpg and db_pool"
Task: "Implement api/refresh/template_refresh.py with run_template_refresh_job sync function"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
   - Developer D: User Story 4
3. Stories complete and integrate independently