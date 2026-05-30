# Research: Template Refresh System (Backend Only)

## Unknowns Resolved

All technical details were explicitly provided in the user's instructions and the specification. There are no pending `NEEDS CLARIFICATION` items.

### Thread Pool Executor
**Decision**: Use `ThreadPoolExecutor(max_workers=2)` as a module-level singleton in `api/state.py`.
**Rationale**: Allows one slot for a full refresh and one for a concurrent template refresh without blocking the FastAPI event loop.

### Job ID Generation
**Decision**: Use format `"refresh-{uuid4_hex[:8]}-{unix_timestamp_ms}"`.
**Rationale**: Ensures job IDs are unique and sortable.

### Redis Polling for SSE
**Decision**: Poll every 250ms when the list has not grown.
**Rationale**: Balances responsiveness with Redis load.

### Lock TTLs
**Decision**: Template locks have a 30-minute TTL; full refresh locks have a 3-hour TTL.
**Rationale**: Safety values to prevent orphaned locks if the server crashes mid-job.

### Server Restart Mid-Job
**Decision**: In `api/main.py` lifespan startup, call `api.refresh.job_registry.mark_orphaned_jobs_failed(redis_client)`.
**Rationale**: Scans for any `refresh-job:*` hash keys with status="running" and sets them to failed with error="Server restarted mid-job", then releases their locks.

### Linked Block Resolution
**Decision**: Query `template_content_block`, `content_block_kv`, and `dynamic_content_details` using the shared asyncpg `db_pool` from `api.state`.
**Rationale**: Read-only async query before job submission to find reachable dynamic rule IDs from content block keys.

### Pipeline Integration
**Decision**: `template_refresh.py` and `full_refresh.py` import from the existing extraction pipeline modules and accept an `env` dict.
**Rationale**: Reuses existing extraction logic with `force_upsert=True` and ensures credentials are read at the moment the endpoint is called.

### SPIKE: Force Upsert Support
**SPIKE**: Does the existing extraction pipeline support a `force_upsert` parameter on each step function, or does it use skip logic that must be bypassed another way? Answer this before writing tasks. If `force_upsert` does not exist, the plan must describe how `template_refresh.py` and `full_refresh.py` will override the skip guard.

### SSE Implementation
**Decision**: Use `StreamingResponse` with `media_type="text/event-stream"` and headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
**Rationale**: Standard SSE implementation. Replays buffered events then polls for new ones. Closes on `job_done` or `job_failed`.