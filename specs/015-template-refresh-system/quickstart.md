# Quickstart: Template Refresh System (Backend Only)

This guide explains how to set up and interact with the Template Refresh System endpoints.

## Setup & Requirements

### 1. Playwright Installation
The background extraction jobs rely on Playwright. Ensure the required browsers are installed (one-time setup):
```bash
playwright install chromium
```

### 2. Environment Variables
The following environment variables MUST be set when starting the FastAPI server. They are read dynamically when a refresh endpoint is called:
- `STRONGMAIL_PASSWORD`: Password for the StrongMail instance (Required).
- `DATABASE_URL`: PostgreSQL connection string (Required).
- `STRONGMAIL_ORG_ID`: Organization ID for the StrongMail instance (Optional, default: `Skrill`).
- `STRONGMAIL_USERNAME`: Username for the StrongMail instance (Optional, default: `io.teamprod`).

### 3. Server Start Command
Start the FastAPI server:
```bash
uvicorn api.main:app --workers 1 --reload
```

## Endpoints

### 1. Start a Template Refresh
Trigger a test refresh for a specific template against a real StrongMail instance.

```bash
curl -X POST http://localhost:8000/refresh/template/{template_name}
```
**Response (200 OK)**:
```json
{
  "job_id": "refresh-20260530143022-a3f7c912"
}
```

### 2. Stream Progress (SSE)
Subscribe to real-time progress events for a job. Tail the SSE stream:

```bash
curl -N http://localhost:8000/refresh/stream/{job_id}
```
**Output**:
```text
data: {"type": "step_start", "step": "resolve_linked_blocks", "message": "Resolving linked blocks...", "count": null, "total": null, "timestamp": "2026-05-30T09:00:00Z"}
```

### 4. Get Job Status
Retrieve the current status of a job without streaming.

```bash
curl http://localhost:8000/refresh/status/refresh-1a2b3c4d-1717150000000
```
**Response**:
```json
{
  "job_id": "refresh-1a2b3c4d-1717150000000",
  "type": "template",
  "target": "my-template-name",
  "status": "running",
  "started_at": "2026-05-30T09:00:00Z",
  "finished_at": null,
  "error": null
}
```

### 5. List Active Jobs
List all currently pending or running jobs.

```bash
curl http://localhost:8000/refresh/active
```
**Response**:
```json
[
  {
    "job_id": "refresh-1a2b3c4d-1717150000000",
    "type": "template",
    "target": "my-template-name",
    "status": "running",
    "started_at": "2026-05-30T09:00:00Z"
  }
]
```