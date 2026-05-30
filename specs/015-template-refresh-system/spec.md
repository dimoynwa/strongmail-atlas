# Feature Specification: Template Refresh System (Backend Only)

**Feature Branch**: `015-template-refresh-system`

**Created**: 2026-05-30

**Status**: Draft

**Input**: User description: "Build a background refresh system for the StrongMail Agent Studio FastAPI backend..."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single Template Refresh (Priority: P1)

As an administrator, I want to trigger a refresh for a specific template so that its content, linked blocks, rules, tone scores, and embeddings are updated immediately without affecting the rest of the system.

**Why this priority**: This is the most common use case. Content for individual templates frequently becomes stale, and administrators need a targeted way to update it quickly without running a full, time-consuming extraction.

**Independent Test**: Can be fully tested by triggering a refresh for a single template and verifying that its content and related entities are updated in the database, while other templates remain untouched.

**Acceptance Scenarios**:

1. **Given** a template with stale content, **When** the administrator triggers a template refresh, **Then** a background job starts, and a unique job identifier is returned immediately.
2. **Given** a running template refresh job, **When** the administrator attempts to start another refresh for the same template, **Then** the system rejects the request with a conflict error (HTTP 409) containing the `locked_by` job ID.
3. **Given** a running full refresh job, **When** the administrator attempts to start a template refresh, **Then** the system rejects the request with a conflict error (HTTP 409) containing the `locked_by` job ID.
4. **Given** a completed template refresh job, **When** the administrator views the template, **Then** the template's content, linked blocks, dynamic rules, tone scores, and embeddings reflect the latest state from the source system.

---

### User Story 2 - Full System Refresh (Priority: P2)

As an administrator, I want to trigger a full refresh of all templates and related content so that the entire database is synchronized with the source system.

**Why this priority**: While less frequent than single template updates, a full synchronization is necessary periodically to ensure global data consistency and to catch any changes missed by targeted updates.

**Independent Test**: Can be fully tested by triggering a full refresh and verifying that all templates, content blocks, rules, tone scores, and embeddings are updated across the entire system.

**Acceptance Scenarios**:

1. **Given** a system with potentially stale data, **When** the administrator triggers a full refresh, **Then** a background job starts, and a unique job identifier is returned immediately.
2. **Given** any running refresh job (template or full), **When** the administrator attempts to start a full refresh, **Then** the system rejects the request with a conflict error (HTTP 409) containing the `locked_by` job ID.
3. **Given** a completed full refresh job, **When** the administrator views the system data, **Then** all templates, content blocks, dynamic rules, tone scores, and embeddings reflect the latest state from the source system.

---

### User Story 3 - Real-time Progress Monitoring (Priority: P2)

As an administrator, I want to monitor the progress of a running refresh job in real-time so that I know what step is currently executing and when the job completes.

**Why this priority**: Refresh jobs (especially full refreshes) can take a significant amount of time. Real-time feedback is crucial for user experience, preventing users from assuming the system has hung.

**Independent Test**: Can be fully tested by subscribing to the progress stream of a running job and verifying that progress events are received in order, culminating in a completion or failure event.

**Acceptance Scenarios**:

1. **Given** a running refresh job, **When** the administrator subscribes to its progress stream, **Then** they receive real-time updates for each step (start, completion, error, progress counts).
2. **Given** a running refresh job, **When** the administrator disconnects and reconnects to the progress stream, **Then** they receive all previous events they missed, followed by new real-time events.
3. **Given** a completed or failed refresh job, **When** the administrator subscribes to its progress stream, **Then** they receive the full history of events, ending with the final status, and the stream closes automatically.

---

### User Story 4 - Active Jobs Overview (Priority: P3)

As an administrator, I want to view a list of all currently active refresh jobs so that I can understand system activity and know which templates are currently locked.

**Why this priority**: Provides visibility into system state, allowing the UI to accurately reflect which operations are currently permitted and which are blocked.

**Independent Test**: Can be fully tested by starting several non-conflicting jobs and verifying that the active jobs list correctly reports their status.

**Acceptance Scenarios**:

1. **Given** multiple running template refresh jobs, **When** the administrator requests the active jobs list, **Then** the system returns a list of all currently running jobs and their targets.
2. **Given** no running jobs, **When** the administrator requests the active jobs list, **Then** the system returns an empty list.

### Edge Cases

- What happens when the source system credentials are not configured? (The system must reject the job start request immediately with HTTP 503).
- What happens if the background job encounters an error during extraction? (The job must be marked as failed, the error recorded in the job state, a failure event emitted to the progress stream, and all locks released).
- What happens if the server crashes while a job is running? (The system should handle orphaned locks gracefully via timeouts, and mark running jobs as failed on startup).
- What happens if the job is already in done or failed state when the SSE connection is opened? (The endpoint replays all buffered events from the progress list from index 0 to end, then closes the stream immediately without polling. It does not hang.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an interface to start a targeted refresh for a single, specified template.
- **FR-002**: System MUST provide an interface to start a full refresh of all templates and related data.
- **FR-003**: System MUST execute refresh jobs in the background without blocking other system operations. The thread pool MUST have `max_workers=2` (one slot for a full refresh, one for a concurrent template refresh).
- **FR-004**: System MUST prevent concurrent refresh jobs for the same template using Redis locks with a 30-minute TTL (to prevent orphaned locks if the server crashes). Note: Triggering a refresh for a template whose previous refresh has already completed and whose lock has been released is always permitted. No cooldown period applies.
- **FR-005**: System MUST prevent a full refresh if any other refresh job is currently running, using a Redis lock with a 3-hour TTL (to prevent orphaned locks if the server crashes).
- **FR-006**: System MUST prevent a template refresh if a full refresh is currently running.
- **FR-007**: System MUST provide a real-time, event-driven stream of progress updates for any specific job. The SSE endpoint MUST poll Redis for new events every 250ms when the list has not grown.
- **FR-008**: System MUST retain the full history of progress events for a job so that reconnecting clients receive missed events.
- **FR-009**: System MUST provide an interface to retrieve the current status of a specific job without subscribing to the event stream.
- **FR-010**: System MUST provide an interface to list all currently active or pending jobs. The response MUST be an array of job summary objects, each with `job_id`, `type`, `target`, `status`, and `started_at`. It MUST return only jobs with status "pending" or "running". Jobs in done or failed state are not included.
- **FR-011**: System MUST force-update existing data during a refresh, bypassing any "skip if exists" optimizations.
- **FR-012**: System MUST verify the presence of required source system credentials (`STRONGMAIL_PASSWORD`) before starting a job and reject the request with HTTP 503 if they are missing.
- **FR-013**: System MUST automatically release any locks held by a job when the job completes successfully or fails.
- **FR-014**: System MUST retain job state and history for 24 hours. The 24-hour TTL MUST be set (or reset) on both `refresh-job:{job_id}` and `refresh-job:{job_id}:progress` keys *when the job reaches a done or failed state*, not when they are first created.
- **FR-015**: System MUST generate unique and sortable `job_id`s using a combination of a timestamp and a UUID4 hex prefix (e.g., `YYYYMMDDHHMMSS-uuid4hex`).
- **FR-016**: System MUST handle server restarts mid-job. A startup check MUST run to find any jobs marked as "running" in Redis and mark them as "failed" with the error "Server restarted mid-job".
- **FR-017**: System MUST correctly resolve linked blocks for a template refresh. This requires querying `template_content_block` to get linked `content_block` IDs, then querying `content_block_kv` and `dynamic_content_details` to find reachable dynamic rule IDs from those content block keys.
- **FR-018**: System MUST return a specific HTTP 409 response shape when a job start is blocked by a lock. The response body MUST include `job_id` (null), `status` ("blocked"), and `locked_by` (the `job_id` holding the lock).
- **FR-019**: `STRONGMAIL_PASSWORD`, `STRONGMAIL_ORG_ID`, `STRONGMAIL_USERNAME`, and `DATABASE_URL` MUST be read from `os.environ` at the moment the POST endpoints are called. They are passed as an env dict to the sync job function. They MUST NEVER be cached at startup or read at module import time.
- **FR-020**: Progress events MUST use the following canonical step name values:
  - For template refresh: `resolve_linked_blocks`, `fetch_template_body`, `fetch_content_blocks`, `fetch_dynamic_rules`, `evaluate_tone`, `embed_summary`.
  - For full refresh: `fetch_templates_list`, `fetch_content_blocks_list`, `fetch_dynamic_rules_list`, `fetch_dynamic_rule_previews`, `fetch_templates_raw`, `fetch_content_blocks_raw`, `evaluate_all_tones`, `embed_all_summaries`, `backfill_placeholder_keys`.

### Key Behaviors

- **ASYNC/SYNC BOUNDARY**:
  - `resolve_linked_blocks` runs in the FastAPI async context using the shared asyncpg `db_pool` from `api.state` (read-only async query before job submission).
  - `template_refresh` and `full_refresh` sync job functions run inside the thread pool and MUST use synchronous DB connections from the pipeline's own connection handling. They MUST NEVER import `asyncpg` or call any coroutine.

### Integration Constraints

- `template_refresh` and `full_refresh` import and call existing extraction pipeline step functions with `force_upsert=True`. They do NOT reimplement Playwright login, grid fetching, jsonedit interception, edit.do parsing, or rule DSL parsing.
- Reimplementing any extraction logic is explicitly forbidden.

### Key Entities

- **Refresh Job**: Represents a background extraction task. Attributes include unique identifier, job type (template or full), target (if template), current status, start time, end time, and error details (if any).
- **Job Progress Event**: Represents a discrete update during a job's execution. Field optionality:
  - `type`: always required (e.g., step_start, step_done, step_error, item_done, job_done, job_failed)
  - `step`: required on step_start/step_done/step_error/item_done; null on job_done/job_failed
  - `message`: always required
  - `count`: present on item_done/step_done; null on step_start/job_done/job_failed
  - `total`: present on item_done/step_done; null on step_start/job_done/job_failed
  - `timestamp`: always required (ISO 8601 UTC)
- **Refresh Lock**: Represents an exclusive right to perform a refresh operation on a specific target (a template or the full system).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can successfully trigger and complete a single template refresh without restarting the application server.
- **SC-002**: Administrators can successfully trigger and complete a full system refresh without restarting the application server.
- **SC-003**: The system correctly rejects conflicting concurrent refresh requests 100% of the time, returning the required HTTP 409 response shape.
- **SC-004**: Clients reconnecting to a progress stream receive 100% of the events emitted since the job started, with zero gaps.
- **SC-005**: Background refresh jobs do not degrade the response time of other concurrent API requests.

## Assumptions

- The existing extraction pipeline logic can be safely executed in a background thread context.
- The underlying state store (cache) is highly available and suitable for managing distributed locks and short-lived event streams.
- The source system (StrongMail) can handle the load generated by targeted and full refreshes.
- Administrators are authenticated and authorized to perform refresh operations (authorization is handled by existing system mechanisms).
