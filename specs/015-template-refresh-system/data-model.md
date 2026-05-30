# Data Model: Template Refresh System (Backend Only)

## Types

```python
from typing import Literal

JobType = Literal["template", "full"]
JobStatus = Literal["pending", "running", "done", "failed"]
EventType = Literal["step_start", "step_done", "step_error", "item_done", "job_done", "job_failed"]
```

## Dataclasses

### RefreshJob

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class RefreshJob:
    job_id: str
    type: JobType
    target: Optional[str]
    status: JobStatus
    started_at: str  # ISO 8601 UTC string
    finished_at: Optional[str]  # ISO 8601 UTC string. Null/absent while pending or running.
    error: Optional[str]
```

### ProgressEvent

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProgressEvent:
    type: EventType
    step: Optional[str]
    message: str
    count: Optional[int]
    total: Optional[int]
    timestamp: str
```

### LinkedBlocksResult

```python
from dataclasses import dataclass

@dataclass
class LinkedBlocksResult:
    block_ids: list[str]
    rule_ids: list[str]
```

## Redis Key Formats

- `refresh-job:{job_id}`: Hash containing job state (`status`, `type`, `target`, `started_at`, `finished_at`, `error`). Note: Absent optional fields (`target`, `finished_at`, `error`) are stored as empty string `""` in the Redis hash and read back as `None` in Python when an empty string is detected.
- `refresh-job:{job_id}:progress`: List of JSON-encoded progress event strings.
- `refresh-lock:template:{name}`: String containing the `job_id` holding the lock.
- `refresh-lock:full`: String containing the `job_id` holding the lock.

## Job ID Format

`"refresh-{YYYYMMDDHHMMSS}-{uuid4_hex[:8]}"`
Example: `refresh-20260530143022-a3f7c912`