---
description: "Task list for Tone Batch Operations implementation"
---

# Tasks: Tone Batch Operations

**Input**: Design documents from `/specs/016-tone-batch-operations/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/internal-boundaries.md, quickstart.md

**Tests**: Tests are explicitly requested in the plan and specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Project initialization and basic structure

- [X] T001 Add `openpyxl` dependency to `pyproject.toml` (blocking prerequisite for export implementation)
- [X] T002 Create `api/tone_batch/__init__.py`

---

## Phase 2: Foundational

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Write tests for tone_batch locks in `tests/api/tone_batch/test_locks.py` (MUST verify isolation from `refresh-lock:*`)
- [X] T004 [P] Implement Redis locks in `api/tone_batch/locks.py`
- [X] T005 [P] Create `ToneJob` dataclass, `ToneJobStatus` Literal, and explicitly import `ProgressEvent` from `api.refresh.models` (MUST NOT redefine it) in `api/tone_batch/models.py`. (Ensure `ToneJobType` is NOT defined here as there is only one job type).
- [X] T006 [P] Write tests for job registry in `tests/api/tone_batch/test_job_registry.py`
- [X] T007 [P] Implement job registry in `api/tone_batch/job_registry.py` (depends on models)
- [X] T008 [P] Write tests for progress tracking in `tests/api/tone_batch/test_progress.py`
- [X] T009 Implement progress tracking in `api/tone_batch/progress.py`
- [X] T010 Add orphan check (`mark_orphaned_tone_jobs_failed`) to lifespan handler in `api/main.py` (MUST be called after the existing refresh orphan check)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Evaluate single template tone (Priority: P1) 🎯 MVP

**Goal**: As an API client, I want to evaluate a single template's tone and store the results in the database, so that tone evaluations can be updated on-demand without running a full batch job.

**Independent Test**: Can be fully tested by making a POST request to `/tone/reevaluate/{template_name}` and verifying the resulting scores in the PostgreSQL `template_tone_evaluations` table.

### Tests for User Story 1

- [X] T011 [P] [US1] Write test for `/tone/reevaluate` endpoint covering normal, 404, and warning scenarios in `tests/api/tone_batch/test_tone_reevaluate.py`

### Implementation for User Story 1

- [X] T012 [US1] Add `/tone/reevaluate/{template_name}` endpoint to `api/routers/tone.py`, using `run_in_executor` and `psycopg3` for DB upsert. (MUST strip `_warning` from the emotions dict before constructing the response, exposing it only via the top-level warning field).

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Batch reevaluate all templates (Priority: P1)

**Goal**: As a system administrator, I want to trigger a batch job to reevaluate all templates for English/SKRILL and track its progress, so that I can keep all tone evaluations up to date across the system.

**Independent Test**: Can be tested by calling the batch trigger endpoint and verifying that all applicable templates receive updated rows in the database, and progress events are emitted.

### Tests for User Story 2

- [X] T013 [P] [US2] Write tests for job runner submission in `tests/api/tone_batch/test_job_runner.py`
- [X] T014 [P] [US2] Write integration tests for the full batch job in `tests/api/tone_batch/test_batch_tone_integration.py` (MUST verify: POST `/tone/batch-reevaluate` → GET `/tone/batch-stream` until `job_done` → GET `/tone/export` → verify at least one row has `TONE_1` populated)
- [X] T014A [P] [US2] Write test in `tests/api/tone_batch/test_batch_tone_integration.py` verifying `/tone/batch-reevaluate` returns 409 while a job is running, AND that the lock is released after job completion

### Implementation for User Story 2

- [X] T015 [US2] Implement `submit_tone_job` using `refresh_executor` in `api/tone_batch/job_runner.py` (MUST explicitly pass `state.classifier` as an argument to `run_batch_tone_job` when calling `run_in_executor`).
- [X] T016 [US2] Implement sync logic for `run_batch_tone_job` using `psycopg3` in `api/tone_batch/batch_tone.py` (MUST accept the GoEmotions classifier as an explicit parameter from the async caller, and MUST NOT call `get_classifier()` internally).
- [X] T017 [US2] Add the four batch endpoints (batch-reevaluate, batch-stream, batch-status, batch-active) in `api/routers/tone_batch.py`
- [X] T017A [US2] Mount the `tone_batch` router in `api/main.py` via `app.include_router(tone_batch_router, prefix="/tone")` (depends on T017).

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Export tone evaluations (Priority: P2)

**Goal**: As a content manager, I want to export all template tone evaluations to CSV or Excel format, so that I can analyze the overall emotional tone of our templates in external tools.

**Independent Test**: Can be tested by hitting the export endpoint with a specific format requested and verifying the downloaded file contains the correct columns and data.

### Tests for User Story 3

- [X] T018 [P] [US3] Write test for export endpoint formatting and logic in `tests/api/tone_batch/test_tone_export.py`

### Implementation for User Story 3

- [X] T019 [US3] Implement `GET /tone/export` endpoint with `asyncpg` graph resolution batched post-query in `api/routers/tone.py` (MUST filter out the `_warning` key from the tones JSONB before sorting by score descending; `_warning` must appear only in WARNING column).

**Checkpoint**: All user stories 1-3 should now be independently functional

---

## Phase 6: User Story 4 - View plain text used for evaluation (Priority: P3)

**Goal**: As an API client using the existing single session evaluate endpoint, I want to see the plain text that was used for evaluation, so that I can debug and understand the input.

**Independent Test**: Can be tested by calling the existing endpoint and verifying the new plain text field is present and correct.

### Tests for User Story 4

- [X] T020 [P] [US4] Write test for plain_text in evaluate response in `tests/api/tone_batch/test_tone_evaluate_plain_text.py`

### Implementation for User Story 4

- [X] T021 [P] [US4] Add `plain_text` field to `POST /tone/evaluate/{session_id}` response model in `api/models/responses.py`
- [X] T022 [US4] Update `POST /tone/evaluate/{session_id}` endpoint in `api/routers/tone.py` to return the `plain_text` field

**Checkpoint**: All user stories should now be independently functional

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T023 [P] Verify no `asyncpg` or `state.db_pool` imports leak into `api/tone_batch/` modules (enforcing the architectural contract)
- [X] T023A [P] Implement and verify `_warning` sentinel convention: writing it in `api/tone_batch/batch_tone.py` and `api/routers/tone.py` (/tone/reevaluate), AND reading it correctly in `api/routers/tone.py` export (stripping it before emotion sort, surfacing it in WARNING column)
- [X] T024 [P] Run curl examples from `specs/016-tone-batch-operations/quickstart.md` to validate live system behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel
  - Or sequentially in priority order (US1 → US2 → US3 → US4)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2)
- **User Story 2 (P1)**: Can start after Foundational (Phase 2)
- **User Story 3 (P2)**: Can start after Foundational (Phase 2)
- **User Story 4 (P3)**: Can start after Foundational (Phase 2)

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tests and independent modules (e.g., locks, models) marked [P] can run in parallel
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)

---

## Parallel Example: User Story 4

```bash
# Launch tests for User Story 4:
Task: "Write test for plain_text in evaluate response in tests/api/tone_batch/test_tone_evaluate_plain_text.py"

# Concurrently update the response model:
Task: "Add plain_text field to evaluation response model in api/models/responses.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently via `/tone/reevaluate/{template_name}`.

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently
3. Add User Story 2 → Test batch execution endpoints
4. Add User Story 3 → Verify export output correctly formats
5. Add User Story 4 → Validate minor payload updates on session eval

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 & User Story 4 (API extensions)
   - Developer B: User Story 2 (Batch logic and endpoints)
   - Developer C: User Story 3 (Export generation)
3. Stories complete and integrate independently