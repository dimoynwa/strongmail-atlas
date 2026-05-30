# Internal Architectural Contracts

This file defines the strict boundaries and responsibilities for the Tone Batch Operations feature.

## Database Write Contracts

- `tone_batch.py` is the **ONLY** module permitted to write to the `template_tone_evaluations` table within the context of the batch job. This must never be done directly from the routers.
- `api/routers/tone.py` writes to `template_tone_evaluations` **ONLY** for the single-template reevaluate endpoint, and it must do so via `run_in_executor` using a `psycopg3` sync connection.

## Redis Access Contracts

- `tone_batch/job_registry.py` is the **ONLY** module permitted to read or write the `tone-job:*` hash keys.
- `tone_batch/locks.py` is the **ONLY** module permitted to read or write the global lock key `tone-lock:batch`.
- `tone_batch/progress.py` is the **ONLY** module permitted to read or append to the `tone-job:*:progress` lists.

## Import & Concurrency Constraints

- **No** tone batch module (`api/tone_batch/*.py`) is permitted to import `asyncpg` or use the global async pool `state.db_pool`.
- All interactions with `asyncpg` for template graph resolution and export must remain isolated in the async endpoints (`api/routers/tone.py`, `api/routers/tone_batch.py`) before handing off the pure sync workload to `run_batch_tone_job`.