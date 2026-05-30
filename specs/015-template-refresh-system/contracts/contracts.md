# Contracts: Template Refresh System (Backend Only)

## Internal Module Contracts

### `api/routers/refresh.py` -> `api/refresh/job_registry.py`
- Only `job_registry.py` is permitted to read or write job hash keys in Redis. The router must use the functions provided by `job_registry.py` to interact with job state.

### `api/routers/refresh.py` -> `api/refresh/locks.py`
- Only `locks.py` is permitted to read or write lock keys in Redis. The router must use the functions provided by `locks.py` to acquire, check, and release locks.

### `api/refresh/template_refresh.py` & `api/refresh/full_refresh.py`
- These modules contain the synchronous job functions that run in the thread pool.
- They MUST NEVER use `asyncpg` or any asynchronous code.
- All database access within these modules MUST be synchronous, utilizing the extraction pipeline's own connection handling.

### `api/refresh/linked_blocks.py`
- This is the ONLY module in the refresh subsystem permitted to use `asyncpg` (via the shared `db_pool` from `api.state`).
- It performs read-only async queries to resolve linked blocks before a job is submitted to the thread pool.