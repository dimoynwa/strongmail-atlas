# Quickstart: Tone Batch Operations

## Triggering a Tone Batch Job

Start a new batch reevaluation job and read the `job_id` from the response.

```bash
curl -X POST http://localhost:8000/tone/batch-reevaluate
```

If successful, returns a `202 Accepted` with the `job_id`:
```json
{
  "job_id": "tone-20260530143022-a3f7c912",
  "status": "pending"
}
```

If a job is already running, returns a `409 Conflict`:
```json
{
  "job_id": null,
  "status": "blocked",
  "locked_by": "tone-20260530143000-b1e2f345"
}
```

## Monitoring Progress

Connect to the SSE stream to tail progress events for a running job. The `-N` flag is required to prevent `curl` from buffering the stream.

```bash
# Replace {job_id} with the ID returned from the trigger endpoint
curl -N http://localhost:8000/tone/batch-stream/{job_id}
```

## Reevaluating a Single Template

```bash
curl -X POST http://localhost:8000/tone/reevaluate/password_reset_en
```

## Exporting Results

Download all stored evaluations as CSV (default). The `-O -J` flags save the file to disk using the filename provided by the server.

```bash
curl -O -J http://localhost:8000/tone/export
```

Download as Excel, specifying the format query parameter:

```bash
curl -O -J 'http://localhost:8000/tone/export?format=xlsx'
```