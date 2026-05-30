# Feature Specification: Tone Batch Operations

**Feature Branch**: `016-tone-batch-operations`

**Created**: 2026-05-30

**Status**: Draft

**Input**: User description: "Implement Spec 016 — Tone Batch Operations..."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evaluate single template tone (Priority: P1)

As an API client, I want to evaluate a single template's tone and store the results in the database, so that tone evaluations can be updated on-demand without running a full batch job.

**Why this priority**: Essential for immediate reevaluation of changed or new templates.

**Independent Test**: Can be fully tested by making a POST request to `/tone/reevaluate/{template_name}` and verifying the resulting scores in the PostgreSQL `template_tone_evaluations` table.

**Acceptance Scenarios**:

1. **Given** an existing template with a valid template details record, **When** a reevaluate request is made, **Then** the endpoint returns the top 3 emotions and they are saved to the database.
2. **Given** a template with no meaningful text or unresolvable keys, **When** a reevaluate request is made, **Then** the result is stored with the appropriate warning flag and returned in the API response warning field.
3. **Given** a non-existent template, **When** a reevaluate request is made, **Then** the API returns a 'Template Not Found' error.

---

### User Story 2 - Batch reevaluate all templates (Priority: P1)

As a system administrator, I want to trigger a batch job to reevaluate all templates for English/SKRILL and track its progress, so that I can keep all tone evaluations up to date across the system.

**Why this priority**: Needed for bulk updates across the entire template corpus.

**Independent Test**: Can be tested by calling the batch trigger endpoint and verifying that all applicable templates receive updated rows in the database, and progress events are emitted.

**Acceptance Scenarios**:

1. **Given** no active batch tone job, **When** a batch trigger request is made, **Then** a new job is created, locked, and executed asynchronously, processing all applicable templates.
2. **Given** an active batch tone job, **When** a batch trigger request is made again, **Then** the API returns a conflict error indicating a job is already running.
3. **Given** an active batch tone job, **When** the progress stream endpoint is connected, **Then** the client receives real-time progress updates including load, resolve/evaluate, and store steps.

---

### User Story 3 - Export tone evaluations (Priority: P2)

As a content manager, I want to export all template tone evaluations to CSV or Excel format, so that I can analyze the overall emotional tone of our templates in external tools.

**Why this priority**: Necessary for reporting and analysis by non-technical stakeholders.

**Independent Test**: Can be tested by hitting the export endpoint with a specific format requested and verifying the downloaded file contains the correct columns and data.

**Acceptance Scenarios**:

1. **Given** stored evaluations in the database, **When** the export endpoint is called with CSV format, **Then** a CSV file is returned containing NAME, SUBJECT, SUMMARY, top 3 TONE/SCORE pairs, and WARNING.
2. **Given** templates with unresolvable placeholders or missing text, **When** they are exported, **Then** the WARNING column correctly reflects the issue.
3. **Given** the export endpoint is called with Excel format, **Then** a valid Excel file is returned.

---

### User Story 4 - View plain text used for evaluation (Priority: P3)

As an API client using the existing single session evaluate endpoint, I want to see the plain text that was used for evaluation, so that I can debug and understand the input.

**Why this priority**: This is a minor enhancement to an existing endpoint to aid in debugging.

**Independent Test**: Can be tested by calling the existing endpoint and verifying the new plain text field is present and correct.

**Acceptance Scenarios**:

1. **Given** a valid session, **When** the session evaluate endpoint is called, **Then** the response includes the plain text and its length alongside existing data.

### Edge Cases

- What happens when the database connection fails during the batch save step?
- How does the system handle an orphaned job lock (e.g., if the server restarts mid-job)?
- What happens if the AI tone model is not loaded when an evaluation is requested?
- How are templates without a details record handled during the batch run and export?
- What happens if a template subject contains tokens that cannot be resolved?

## Technical Design

- **File Structure**:
  - New `api/tone_batch/` subdirectory mirroring refresh: `models.py`, `job_registry.py`, `locks.py`, `progress.py`, `job_runner.py`, `batch_tone.py`.
  - Modified `api/routers/tone.py` for new and extended endpoints.
  - New `api/routers/tone_batch.py` for batch-related endpoints.
  - Modified `api/main.py` lifespan to include the tone orphan check.
  - Modified `api/models/responses.py` for the `plain_text` field addition.

- **Redis Key Schema**:
  - `tone-job:{job_id}`: Hash (`status`, `started_at`, `finished_at`, `error`). TTL: 24 hours (set at job completion). Job ID format: `tone-{YYYYMMDDHHMMSS}-{uuid4_hex[:8]}`.
  - `tone-job:{job_id}:progress`: List (append-only `ProgressEvent` JSON strings).
  - `tone-lock:batch`: String (holds `job_id`, TTL 2 hours).

- **Batch Job Steps**:
  1. `load_templates`: `step_start`/`step_done` with `count=N`.
  2. `resolve_and_evaluate`: `item_done` per template (`count=i`, `total=N`). Emits `step_error` on per-template failure, but job continues.
  3. `store_results`: `step_start`/`step_done` with `count=upserted`. Final event is `job_done` or `job_failed`.

- **Export Implementation**:
  - Uses a single JOIN query (no N+1).
  - Subject resolution is batched post-query for rows containing `##...##` tokens.
  - Export format relies on `openpyxl` for xlsx and stdlib `csv` for CSV.
  - The response is buffered in memory before returning.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST return the plain text input in the response of the session evaluate endpoint.
- **FR-002**: System MUST provide a new endpoint that runs the tone evaluator for a specific template and saves the results into the database. The DB write (upsert) MUST use `psycopg3` via `run_in_executor`, while the graph read MUST use `asyncpg` (`db_pool`). It MUST return a 503 ModelNotReady response if the classifier is not loaded.
- **FR-003**: System MUST identify and flag templates with empty/insufficient text (< 20 chars) or unresolvable keys during evaluation by storing a `_warning` sentinel key inside the `tones` JSONB column (not a separate DB column). The `_warning` sentinel values MUST be exactly one of: `"no_meaningful_text"` (plain text < 20 chars after trafilatura), `"unresolvable_keys"` (non-empty unresolvable_keys from resolve_template), or `"no_meaningful_text,unresolvable_keys"` (if both conditions are met). The `_warning` key MUST be stripped before sorting emotions by score and MUST NEVER appear in `TONE_1`/`TONE_2`/`TONE_3` columns. The export WARNING column MUST read from `tones["_warning"]`.
- **FR-004**: System MUST provide a batch job system mirroring the existing refresh system. It MUST share the existing `ThreadPoolExecutor` (`refresh_executor` in `api/state.py`); a second executor MUST NOT be created. It uses Redis-backed state/locking. `api/tone_batch/models.py` MUST import `ProgressEvent` from `api.refresh.models` — it MUST NOT redefine it (there is exactly one definition in the codebase).
- **FR-005**: System MUST enforce a single global lock (`tone-lock:batch`) for the batch tone job. This lock MUST be fully isolated from refresh locks (`refresh-lock:*`) — one does not block the other.
- **FR-006**: System MUST recover from orphaned tone batch jobs on application startup by calling `mark_orphaned_tone_jobs_failed` in the `main.py` lifespan hook, alongside the existing refresh orphan check.
- **FR-007**: System MUST provide an export endpoint that returns a CSV or Excel file containing all templates with stored evaluations. The `openpyxl` dependency MUST be added to `pyproject.toml` to support Excel export.
- **FR-008**: System MUST resolve template subjects for the export using the following fallback chain: (a) if the subject has no `##...##` tokens, use it as-is; (b) if resolution succeeds, use the resolved value; (c) if resolution fails or the `template_details` row is absent, use the raw string or an empty string, respectively.
- **FR-009**: System MUST exclude templates from the export if they do not have a stored evaluation record. Additionally, the batch job `load_templates` step MUST only include templates WITH a `template_details` row (templates without raw bodies are skipped).
- **FR-010**: System MUST pass the classifier as a parameter from the async caller (which holds `state.classifier`) into `batch_tone.run_batch_tone_job()`. The sync function MUST NOT call `get_classifier()` itself.

### Key Entities

- **Tone Evaluation Job**: Represents a batch processing run (status, timing, progress).
- **Template Tone Evaluation**: Represents the top 3 emotions and warnings for a template, stored in the database.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of applicable templates are successfully processed and stored during a batch run without manual intervention.
- **SC-002**: Exported CSV/Excel files contain exactly the number of rows matching the stored evaluations records.
- **SC-003**: The batch job lock reliably prevents concurrent execution 100% of the time without blocking other unrelated batch jobs.
- **SC-004**: Orphaned jobs are successfully marked as failed upon server restart 100% of the time.

## Assumptions

- The database is highly available and can handle the bulk save from the batch job.
- The AI tone classifier is loaded into memory prior to these endpoints being hit.
- The existing system resources (e.g., thread pools) are sufficient for handling the additional batch tone jobs.
- Excel export formatting will be unstyled plain tabular data.
- The `_warning` sentinel key is excluded when sorting emotion scores for TONE_1/2/3 columns in the export. It surfaces only in the WARNING column.