# StrongMail Agent Studio

FastAPI backend for the StrongMail Agent Studio. It sits between a React frontend and the Python agent stack:

- **Chat** → Google ADK runners (SSE streaming)
- **Working copy, preview, tone evaluate** → direct Redis / PostgreSQL / GoEmotions (no agent round-trip)
- **Session** → in-memory ADK sessions with a pre-built resolution graph

**Base URL:** `http://localhost:8000`  
**Interactive docs:** `http://localhost:8000/docs`

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- PostgreSQL and Redis (via Docker Compose or existing instances)
- AWS credentials in `.env` if using Bedrock models

---

## Setup

### 1. Clone and install

```bash
uv sync
cp .env.example .env   # edit with your DATABASE_URL, REDIS_URL, AWS keys
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis
```

Postgres listens on `localhost:15433`, Redis on `localhost:6379` (defaults in `.env.example`).

### 3. Run the API

**VS Code / Cursor** — launch config **FastAPI: Agent Studio API**

**Terminal:**

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
```

> Use a **single worker** — ADK sessions are in-memory.  
> First startup may take 30–60s while GoEmotions loads.

### 4. Verify

```bash
curl http://localhost:8000/health
```

---

## Usage

### Recommended call order

1. `GET /health` — check dependencies  
2. `GET /templates`, `/templates/locales`, `/templates/brands` — sidebar data  
3. `POST /session` — create session; save `session_id`  
4. `GET /working-copy/{session_id}`, `GET /preview/{session_id}` — initial state  
5. `GET /tone/stored/{session_id}`, `POST /tone/evaluate/{session_id}` — tone  
6. `POST /chat/stream` — agent chat (SSE)  
7. `POST /tone/apply/{session_id}` / `POST /tone/undo/{session_id}` — apply or undo suggestions  
8. `PATCH /working-copy/{session_id}` — manual edits  
9. `GET /working-copy/{session_id}/export` — download overrides  
10. `DELETE /working-copy/{session_id}` — clear working copy  

### Postman

Import [`api/postman/StrongMail Agent Studio.postman_collection.json`](api/postman/StrongMail%20Agent%20Studio.postman_collection.json).  
Collection variable `session_id` is set automatically by the **POST /session** test script.

### End-to-end test script

```bash
PYTHONPATH=. .venv/bin/python scripts/test_api_workflow.py
```

Runs all endpoints in workflow order and reports pass/fail.

### Docker

```bash
docker build -t strongmail-api .

# Baked defaults from .env.example
docker run --rm -p 8000:8000 strongmail-api

# Mount your local .env (recommended)
docker run --rm -p 8000:8000 -v "$(pwd)/.env:/app/.env:ro" strongmail-api

# Override specific variables (runtime wins over .env)
docker run --rm -p 8000:8000 \
  -v "$(pwd)/.env:/app/.env:ro" \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:15433/strongmail-tov \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  strongmail-api
```

**Env precedence:** runtime `-e` / `--env-file` → entrypoint loads `$ENV_FILE` (default `/app/.env`) without overriding already-set vars → `python-dotenv` in app code (same no-override rule).

Set a custom env file path:

```bash
docker run -e ENV_FILE=/config/.env -v "$(pwd)/.env:/config/.env:ro" ...
```

---

## Configuration

Copy `.env.example` to `.env`. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `TEMPLATE_ASSISTANT_MODEL` | LLM provider (`bedrock_nova_pro`, `gemini`, `ollama`, …) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | Bedrock credentials |

Session-scoped template context is passed in **`POST /session`**, not via these globals.

---

## API Reference

All JSON bodies use `Content-Type: application/json`. Timestamps are ISO 8601 UTC strings.

### Error format

```json
{
  "error": "SessionNotFound",
  "message": "No session found for session_id: abc-123",
  "detail": null
}
```

| Status | When |
|--------|------|
| 400 | Malformed request |
| 404 | Session, template, or graph key not found |
| 422 | Request validation failure |
| 500 | Unexpected server error |
| 503 | GoEmotions not loaded yet |

---

### Health

#### `GET /health`

Returns dependency status. Always **200** — read the JSON body for component health.

```json
{
  "status": "ok",
  "components": {
    "postgres": { "status": "ok", "latency_ms": 2 },
    "redis": { "status": "ok", "latency_ms": 1 },
    "go_emotions": { "status": "ok", "model": "SamLowe/roberta-base-go_emotions" },
    "adk": { "status": "ok", "active_sessions": 1 }
  }
}
```

---

### Templates

#### `GET /templates`

Lists approved templates with placeholder key counts.

```json
{
  "templates": [
    {
      "name": "NFY_SM_REGISTERED",
      "id": "12345",
      "key_count": 7079,
      "last_modified": "31-Oct-22 09:47 AM UTC",
      "summary": "…"
    }
  ],
  "total": 668
}
```

#### `GET /templates/locales`

```json
{ "locales": ["EN"] }
```

#### `GET /templates/brands`

```json
{ "brands": ["SKRILL"] }
```

---

### Session

#### `POST /session` → `201`

Creates an ADK session and pre-builds the resolution graph.

**Request:**

```json
{
  "template_name": "NFY_SM_REGISTERED",
  "lang_local": "EN",
  "param_cust_brand": "SKRILL"
}
```

**Response:**

```json
{
  "session_id": "uuid-…",
  "template_name": "NFY_SM_REGISTERED",
  "lang_local": "EN",
  "param_cust_brand": "SKRILL",
  "tone_key_count": 42,
  "working_copy_overrides": 0
}
```

Use `session_id` on all subsequent session-scoped calls.

---

### Working copy

Redis key format: `working-copy:{template_name}:{session_id}`

#### `GET /working-copy/{session_id}`

```json
{
  "session_id": "uuid-…",
  "overrides": [{ "key": "EN.PARAGRAPH_1", "value": "…", "set_at": null }],
  "total_overrides": 1,
  "session_has_changes": true
}
```

Empty overrides return `200` with `"overrides": []` (not 404).

#### `PATCH /working-copy/{session_id}`

**Request:**

```json
{ "key": "EN.PARAGRAPH_1", "value": "New text here" }
```

Key must exist in the session resolution graph.

#### `DELETE /working-copy/{session_id}`

Clears the entire working copy hash.

#### `GET /working-copy/{session_id}/export`

Returns a downloadable JSON patch file (`Content-Disposition: attachment`).

---

### Preview

#### `GET /preview/{session_id}?highlight_modified=true`

Resolves HTML and plain text using the current working copy.

```json
{
  "resolved_html": "<html>…</html>",
  "resolved_text": "Dear customer, …",
  "unresolvable_keys": [{ "key": "EN.MISSING", "reason": "MISSING" }],
  "total_placeholders": 7079,
  "resolved_count": 7078,
  "unresolvable_count": 1,
  "evaluated_from": "working_copy"
}
```

---

### Tone

#### `POST /tone/evaluate/{session_id}`

Runs GoEmotions on resolved plain text. Optional body: `{ "top_n": 5 }`.

```json
{
  "emotions": { "gratitude": 0.74, "neutral": 0.60 },
  "model": "go_emotions",
  "evaluated_from": "working_copy",
  "plain_text_length": 312,
  "warning": null
}
```

#### `GET /tone/stored/{session_id}`

Reads the latest row from `template_tone_evaluations`. Returns `200` with null emotions when none stored.

#### `POST /tone/apply/{session_id}`

Writes pending suggestions from ADK session state to Redis. Optional body: `{ "keys": ["EN.PARAGRAPH_1"] }` — omit to apply all.

#### `POST /tone/undo/{session_id}`

Restores from the tone suggestion snapshot in Redis. Optional body: `{ "keys": ["EN.PARAGRAPH_1"] }` — omit for full undo.

---

### Chat (SSE)

#### `POST /chat/stream`

Streams agent responses as Server-Sent Events.

**Request (template agent):**

```json
{
  "message": "Make this template feel more reassuring.",
  "session_id": "uuid-…",
  "agent": "template"
}
```

**Request (general agent):**

```json
{
  "message": "Find password-related templates.",
  "agent": "general"
}
```

`session_id` is required for `"template"`, optional for `"general"`.

**Response:** `Content-Type: text/event-stream`

```
data: {"type":"tool","name":"evaluate_tone"}\n\n
data: {"type":"token","text":"Top emotions: "}\n\n
data: {"type":"final","text":"…","diff":null}\n\n
data: {"type":"wc_updated"}\n\n
```

| Event | Meaning |
|-------|---------|
| `tool` | Agent invoked a tool |
| `token` | Partial response text |
| `final` | Complete response; `diff` set when tone suggestions are pending |
| `wc_updated` | Working copy changed — refresh preview |
| `error` | Stream failed |

---

## Project layout

```
api/
├── main.py              # FastAPI app, lifespan, CORS
├── state.py             # ADK runners, DB/Redis/GoEmotions singletons
├── routers/             # Route handlers
├── models/              # Pydantic request/response models
├── middleware/          # Session guard dependency
├── services/            # Shared preview logic
└── postman/             # Postman collection
shared/                  # DB, Redis, resolution engine
template_assistant/      # Template ADK agent + tools
general_agent/           # Catalog ADK agent
scripts/test_api_workflow.py
Dockerfile
docker-compose.yml
```

Full specification: [`specs/012-fast-api-wrapper/spec.md`](specs/012-fast-api-wrapper/spec.md)

---

## Development

```bash
# Integration tests
pytest tests/integration

# API workflow smoke test (server must be running)
PYTHONPATH=. python scripts/test_api_workflow.py
```

**CORS** is configured for `http://localhost:3000` (React dev server). Adjust in `api/main.py` for other origins.
