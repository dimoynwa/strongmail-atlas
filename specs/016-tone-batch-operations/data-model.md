# Data Model: Tone Batch Operations

## Entities

### `ToneJob` Dataclass

Represents a batch tone evaluation job.

- **Fields**:
  - `job_id`: `str` (Format: `tone-{YYYYMMDDHHMMSS}-{uuid4_hex[:8]}`)
  - `status`: `ToneJobStatus`
  - `started_at`: `str` (ISO 8601 UTC string. Conversion to datetime is the caller's responsibility)
  - `finished_at`: `Optional[str]` (ISO 8601 UTC string. Conversion to datetime is the caller's responsibility)
  - `error`: `Optional[str]`

### Types and Literals

- **`ToneJobStatus`**: `Literal["pending", "running", "done", "failed"]`
- **`ProgressEvent`**: Must be imported from `api.refresh.models`, **not redefined**. There is exactly one `ProgressEvent` definition in the codebase.

### `TemplateToneEvaluation` JSONB Schema (Stored in PostgreSQL)

The `tones` JSONB column stores emotion scores and an optional sentinel key.

- **Keys**: Emotion labels (e.g., `"joy"`, `"admiration"`) mapping to float scores.
- **Sentinel Key (`"_warning"`)**: An optional string key indicating an evaluation issue (e.g., `"no_meaningful_text"`).
  - The `_warning` value is **never** an emotion label.
  - It must **not** appear in `TONE_1`/`TONE_2`/`TONE_3` export columns.
  - The export query/logic **must** strip the `_warning` key before sorting the remaining emotions by score.
  - The `_warning` key is stripped from the emotions dict before it is returned in any API response (both `/tone/reevaluate` and `/tone/evaluate`). The warning value is exposed only via the dedicated top-level `warning` field in the response. The `_warning` key must never appear as a key inside the emotions object returned to API clients.

## Redis Key Formats

1. **Job State**
   - **Key**: `tone-job:{job_id}`
   - **Type**: Hash
   - **Fields**: `status`, `started_at`, `finished_at`, `error`
   - **TTL**: 24 hours (set at job completion)

2. **Job Progress**
   - **Key**: `tone-job:{job_id}:progress`
   - **Type**: List
   - **Content**: Append-only `ProgressEvent` JSON strings
   - **TTL**: 24 hours (matches Job State TTL)

3. **Batch Job Lock**
   - **Key**: `tone-lock:batch`
   - **Type**: String
   - **Content**: The `job_id` holding the lock
   - **TTL**: 2 hours (orphan safety)
