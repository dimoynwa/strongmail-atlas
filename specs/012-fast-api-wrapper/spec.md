# StrongMail Agent Studio — API Specification

> **Backend**: FastAPI (Python 3.11+), `uvicorn`, async throughout
> **Base URL**: `http://localhost:8000`
> **All request/response bodies**: `application/json` unless noted
> **All timestamps**: ISO 8601 UTC strings

---

## 1. Architecture overview

The FastAPI layer sits between the React frontend and the Python backend. It is intentionally thin:

- **Chat endpoints** delegate to the Google ADK `Runner`, streaming events back as Server-Sent Events (SSE)
- **Working copy endpoints** call `shared/redis_client.py` directly — no agent round-trip
- **Preview endpoints** call `shared/resolution/resolver.py` directly — no agent round-trip
- **Tone evaluate endpoint** calls `template_assistant/ml/goemotions.py` directly — no agent round-trip
- **Session endpoint** creates an ADK session and returns the session ID to the client

This design keeps latency low for the most frequent operations (working copy reads/writes, preview refreshes) and reserves the ADK agent path for natural language chat only.

```
React
  │
  ├── POST /chat/stream         → ADK Runner (SSE)
  ├── POST /session             → ADK SessionService
  ├── GET  /templates           → PostgreSQL
  ├── GET  /templates/locales   → PostgreSQL
  ├── GET  /templates/brands    → PostgreSQL
  ├── GET  /working-copy/{sid}  → Redis
  ├── PATCH /working-copy/{sid} → Redis
  ├── DELETE /working-copy/{sid}→ Redis
  ├── GET  /preview/{sid}       → shared/resolution (PostgreSQL + Redis)
  ├── POST /tone/evaluate/{sid} → GoEmotions singleton (+ Redis for WC)
  ├── GET  /tone/stored/{sid}   → PostgreSQL (template_tone_evaluations)
  ├── POST /tone/apply/{sid}    → Redis (pending_suggestions → working copy)
  ├── POST /tone/undo/{sid}     → Redis (snapshot → working copy)
  └── GET  /health              → PostgreSQL + Redis + GoEmotions
```

### Startup singletons

The following are initialised once at FastAPI startup and held as module-level singletons in `api/state.py`:

```python
# api/state.py
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from template_assistant.agent import root_agent as template_agent
from general_agent.agent import root_agent as general_agent
from shared.db import get_pool
from shared.redis_client import get_redis
from template_assistant.ml.goemotions import get_classifier

session_service = InMemorySessionService()

template_runner = Runner(
    agent=template_agent,
    app_name="template_assistant",
    session_service=session_service,
)

general_runner = Runner(
    agent=general_agent,
    app_name="general_agent",
    session_service=session_service,
)

# db_pool and redis are initialised in the FastAPI lifespan handler
db_pool = None
redis_client = None
classifier = None  # GoEmotions, loaded once
```

All endpoints import from `api.state` — they never create their own connections or model instances.

---

## 2. CORS

For development, allow all origins. Lock down in production:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 3. Error response format

All errors return a standard shape:

```json
{
  "error": "SessionNotFound",
  "message": "No ADK session found for session_id: abc-123",
  "detail": null
}
```

| HTTP status | When used |
|---|---|
| 400 | Malformed request, validation failure |
| 404 | Session not found, template not found, key not in graph |
| 409 | Conflict — e.g. second suggestion batch before undo |
| 422 | FastAPI default for request body validation errors |
| 500 | Unexpected server error (ADK failure, DB unreachable) |
| 503 | GoEmotions model not yet loaded |

---

## 4. Session endpoints

### `POST /session`

Creates a new ADK session for a template + context combination. Returns the session ID that the React client must include in all subsequent calls for this template.

**Request body**:

```json
{
  "template_name": "password_reset_en",
  "lang_local": "EN",
  "param_cust_brand": "SKRILL"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `template_name` | string | yes | Must exist in `template` table |
| `lang_local` | string | yes | Uppercased before use |
| `param_cust_brand` | string | yes | Uppercased before use |

**Behaviour**:

1. Validates `template_name` exists in PostgreSQL — returns 404 if not found
2. Creates an ADK session via `session_service.create_session()` with `state` set to:
   ```python
   {
       "template_name": template_name,
       "lang_local": lang_local.upper(),
       "param_cust_brand": param_cust_brand.upper(),
       "session_id": adk_session.id,
   }
   ```
3. Pre-builds the resolution graph for the template (calls `build_graph(pool, template_name)`) and caches it in the session state under `"resolution_graph"` — avoids rebuilding on every tool call
4. Returns the session ID and initial working copy summary

**Response** `201 Created`:

```json
{
  "session_id": "adk-session-abc123",
  "template_name": "password_reset_en",
  "lang_local": "EN",
  "param_cust_brand": "SKRILL",
  "tone_key_count": 8,
  "working_copy_overrides": 0
}
```

`tone_key_count` is the count of placeholder keys eligible for tone rewriting (pre-computed using the same eligibility logic as `get_eligible_keys` in the ToneSuggestionSubagent).

**Errors**:
- `404` if `template_name` not found
- `400` if `lang_local` or `param_cust_brand` is blank

---

## 5. Template list endpoints

### `GET /templates`

Returns all templates for the sidebar list.

**Query parameters**: none

**Response** `200 OK`:

```json
{
  "templates": [
    {
      "name": "password_reset_en",
      "id": "tpl_001",
      "key_count": 34,
      "last_modified": "2026-05-25T14:30:00Z",
      "summary": "Transactional email sent when a user requests a password reset."
    }
  ],
  "total": 12
}
```

`key_count` is the count of entries in the resolution graph for this template (all placeholder keys, not just tone-affecting ones).

**SQL**:

```sql
SELECT t.name, t.id, t.last_modified_date,
       COUNT(cbkv.field_key) AS key_count,
       td.summary
FROM template t
JOIN template_content_block tcb ON tcb.template_id = t.id
JOIN content_block_details cbd ON cbd.content_block_id = tcb.content_block_id
JOIN content_block_kv cbkv ON cbkv.content_block_details_id = cbd.id
LEFT JOIN template_details td ON td.template_id = t.id
WHERE t.template_status = 'ACTIVE'
GROUP BY t.name, t.id, t.last_modified_date, td.summary
ORDER BY t.last_modified_date DESC
```

---

### `GET /templates/locales`

Returns distinct `lang_local` values for the sidebar lang selector.

**Response** `200 OK`:

```json
{ "locales": ["EN", "DE", "ES", "FR", "PT"] }
```

**SQL**: `SELECT DISTINCT lang_local FROM template_details ORDER BY lang_local`

---

### `GET /templates/brands`

Returns distinct `param_cust_brand` values for the sidebar brand selector.

**Response** `200 OK`:

```json
{ "brands": ["NETELLER", "PAYSAFE", "RAPID", "SKRILL"] }
```

**SQL**: `SELECT DISTINCT param_cust_brand FROM template_details ORDER BY param_cust_brand`

---

## 6. Chat endpoint

### `POST /chat/stream`

The primary agent interaction endpoint. Sends a user message to the appropriate ADK agent and streams the response as Server-Sent Events.

**Request body**:

```json
{
  "message": "Make this template feel more reassuring and less urgent.",
  "session_id": "adk-session-abc123",
  "agent": "template"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | yes | User's natural language input |
| `session_id` | string | yes for `template` agent, no for `general` | ADK session ID from `POST /session` |
| `agent` | string | yes | `"template"` or `"general"` |

**Behaviour**:

1. Looks up the ADK session (`template` agent) or creates a transient session (`general` agent)
2. Calls `runner.run_async(user_id, session_id, new_message=message)`
3. Iterates over ADK events and yields SSE events:

| ADK event type | SSE event emitted |
|---|---|
| `function_call` | `{ "type": "tool", "name": "<tool_name>" }` |
| Partial text content | `{ "type": "token", "text": "<partial>" }` |
| Final response | `{ "type": "final", "text": "<full_text>", "diff": <DiffPayload or null> }` |

4. After the final response, if the agent applied any working copy changes (detect via ADK session state delta), emits a `{ "type": "wc_updated" }` event so the React client knows to refresh the working copy and preview

**SSE format**: Each event is a line beginning with `data: ` followed by a JSON string, terminated by `\n\n`:

```
data: {"type":"tool","name":"evaluate_tone · GoEmotions"}\n\n
data: {"type":"token","text":"Top emotions: "}\n\n
data: {"type":"token","text":"urgency 0.81, "}\n\n
data: {"type":"final","text":"Top emotions: urgency 0.81, neutral 0.62, approval 0.54. The tone is functional but somewhat alarming.","diff":null}\n\n
```

**`diff` payload** (populated when `suggest_tone_rewrite` ran):

```json
{
  "suggestions": [
    {
      "key": "EN.SUBJECT",
      "old_value": "URGENT: Reset your Skrill password now",
      "new_value": "Your Skrill password reset — action needed"
    },
    {
      "key": "EN.PARAGRAPH_1",
      "old_value": "Your account will be SUSPENDED in 24 hours.",
      "new_value": "We noticed your account needs attention — you have 24 hours to act safely."
    }
  ],
  "snapshot_overwritten": false
}
```

**Response headers**:

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Errors**:
- `404` if `session_id` not found (for template agent)
- `400` if `agent` is not `"template"` or `"general"`
- `500` if the ADK runner raises an unhandled exception (emitted as a final SSE event with `"type": "error"` before closing the stream)

---

## 7. Working copy endpoints

All working copy endpoints interact with Redis directly. The Redis key format is:

```
working-copy:{template_name}:{session_id}
```

This is a Redis hash. Each field is a canonical placeholder key (`EN.PARAGRAPH_1`), each value is the overridden raw string.

---

### `GET /working-copy/{session_id}`

Returns all current overrides in the working copy for this session.

**Path parameters**: `session_id` (string)

**Response** `200 OK`:

```json
{
  "session_id": "adk-session-abc123",
  "overrides": [
    {
      "key": "EN.SUBJECT",
      "value": "Your Skrill password reset — action needed",
      "set_at": null
    },
    {
      "key": "EN.PARAGRAPH_1",
      "value": "We noticed your account needs attention…",
      "set_at": null
    }
  ],
  "total_overrides": 2,
  "session_has_changes": true
}
```

Returns `overrides: []` and `total_overrides: 0` if no working copy exists for this session — not a 404.

**Errors**:
- `404` if `session_id` not found in ADK session service

---

### `PATCH /working-copy/{session_id}`

Writes a single placeholder key override to Redis. The key must exist in the resolution graph.

**Path parameters**: `session_id` (string)

**Request body**:

```json
{
  "key": "EN.SUBJECT",
  "value": "Your Skrill password reset — action needed"
}
```

**Behaviour**:

1. Validates `session_id` exists
2. Loads the resolution graph from session state cache
3. Validates that `key` exists in the graph — returns 404 if not
4. Reads the previous value from Redis (if any) — stored as `previous_value` in the response
5. Writes the new value to Redis with `HSET`
6. Returns confirmation

**Response** `200 OK`:

```json
{
  "key": "EN.SUBJECT",
  "value": "Your Skrill password reset — action needed",
  "previous_value": "URGENT: Reset your Skrill password now",
  "success": true
}
```

`previous_value` is `null` if the key had no prior override.

**Errors**:
- `404` if `session_id` not found
- `404` if `key` not in resolution graph (body: `{ "error": "KeyNotInGraph", "message": "EN.NONEXISTENT_KEY is not in the resolution graph for password_reset_en" }`)
- `500` if Redis write fails (never falls back silently)

---

### `DELETE /working-copy/{session_id}`

Deletes the entire Redis working copy hash for this session. Irreversible.

**Path parameters**: `session_id` (string)

**Response** `200 OK`:

```json
{
  "keys_cleared": 3,
  "success": true
}
```

Returns `keys_cleared: 0` if no working copy exists — not an error.

**Errors**:
- `404` if `session_id` not found
- `500` if Redis unavailable

---

### `GET /working-copy/{session_id}/export`

Returns the working copy as a downloadable JSON patch file.

**Response** `200 OK`:

```
Content-Type: application/json
Content-Disposition: attachment; filename="password_reset_en_working_copy_20260527.json"
```

```json
{
  "template_name": "password_reset_en",
  "lang_local": "EN",
  "param_cust_brand": "SKRILL",
  "exported_at": "2026-05-27T10:30:00Z",
  "overrides": {
    "EN.SUBJECT": "Your Skrill password reset — action needed",
    "EN.PARAGRAPH_1": "We noticed your account needs attention…"
  }
}
```

---

## 8. Preview endpoint

### `GET /preview/{session_id}`

Resolves the full template HTML and text bodies using the current working copy and returns the rendered result.

**Path parameters**: `session_id` (string)

**Query parameters**:

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `highlight_modified` | boolean | `true` | If true, wraps modified placeholder values in a highlight span before returning |

**Behaviour**:

1. Loads context from ADK session state (`template_name`, `lang_local`, `param_cust_brand`, `session_id`)
2. Loads the resolution graph from session state cache (already built at session init)
3. Calls `resolve_template(template_name, lang_local, param_cust_brand, session_id, graph, pool, redis)` from `shared/resolution/resolver.py`
4. If `highlight_modified=true`, loads current Redis working copy keys and wraps their resolved values in:
   ```html
   <span style="border-left:2px solid #22c55e;padding-left:6px;color:#166534">{value}</span>
   ```
5. Returns HTML, plain text, and unresolvable key list

**Response** `200 OK`:

```json
{
  "resolved_html": "<html>…</html>",
  "resolved_text": "Dear John, your account password has been reset…",
  "unresolvable_keys": [
    {
      "key": "EN.MISSING_KEY",
      "reason": "MISSING"
    }
  ],
  "total_placeholders": 34,
  "resolved_count": 33,
  "unresolvable_count": 1,
  "evaluated_from": "working_copy"
}
```

`evaluated_from` is `"working_copy"` if any Redis overrides were applied, `"graph"` otherwise.

**Errors**:
- `404` if `session_id` not found
- `500` if resolution fails unexpectedly

---

## 9. Tone endpoints

### `POST /tone/evaluate/{session_id}`

Evaluates the emotional tone of the current template state using GoEmotions. Bypasses the ADK agent — calls the classifier directly for speed.

**Path parameters**: `session_id` (string)

**Request body** (optional):

```json
{
  "top_n": 5
}
```

`top_n` defaults to 5, max 28 (full GoEmotions label set).

**Behaviour**:

1. Calls `GET /preview/{session_id}` internally to get the resolved plain text (or re-uses cached preview if available)
2. Strips HTML to plain text using `trafilatura.extract()` if HTML body is used
3. Passes plain text to `get_classifier()(text)` — the GoEmotions singleton
4. Sorts results by score descending, returns top N

**Response** `200 OK`:

```json
{
  "emotions": {
    "admiration": 0.74,
    "approval": 0.68,
    "joy": 0.55,
    "neutral": 0.60,
    "urgency": 0.42
  },
  "model": "go_emotions",
  "evaluated_from": "working_copy",
  "plain_text_length": 312,
  "warning": null
}
```

`warning` is populated when `lang_local` is not `EN`:

```json
{ "warning": "GoEmotions is English-optimised; results for lang_local=DE may be less accurate." }
```

**Errors**:
- `404` if `session_id` not found
- `503` if GoEmotions classifier not yet loaded (`{ "error": "ModelNotReady", "message": "GoEmotions classifier is still loading. Retry in a few seconds." }`)

---

### `GET /tone/stored/{session_id}`

Returns the most recent tone evaluation stored in `template_tone_evaluations` for this template, lang, and brand. Written by the offline pipeline — read-only from the API.

**Path parameters**: `session_id` (string)

**Response** `200 OK`:

```json
{
  "emotions": {
    "joy": 0.78,
    "admiration": 0.55,
    "approval": 0.54,
    "neutral": 0.62,
    "urgency": 0.81
  },
  "evaluated_at": "2026-05-20T14:30:00Z",
  "model_id": "go_emotions_v1",
  "source": "template_tone_evaluations"
}
```

If no stored evaluation exists:

```json
{
  "emotions": null,
  "evaluated_at": null,
  "model_id": null,
  "source": "none"
}
```

This is a `200`, not a `404` — the absence of stored scores is a valid state.

---

### `POST /tone/apply/{session_id}`

Writes confirmed pending suggestions from the most recent `suggest_tone_rewrite` call to the Redis working copy. Pending suggestions are held in ADK session state under `"pending_suggestions"`.

**Path parameters**: `session_id` (string)

**Request body** (optional — omit to apply all):

```json
{
  "keys": ["EN.SUBJECT", "EN.PARAGRAPH_1"]
}
```

If `keys` is omitted or null, all pending suggestions are applied.

**Behaviour**:

1. Reads `pending_suggestions` from ADK session state
2. If `keys` is provided, filters to only those keys
3. Writes each `(key, new_value)` pair to Redis via `HSET`
4. Updates `wc_modified_keys` in session state
5. Clears `pending_suggestions` from session state
6. Returns count of applied changes

**Response** `200 OK`:

```json
{
  "applied": 2,
  "keys": ["EN.SUBJECT", "EN.PARAGRAPH_1"],
  "message": "Applied 2 tone rewrite(s)."
}
```

If no pending suggestions exist:

```json
{
  "applied": 0,
  "keys": [],
  "message": "No pending suggestions to apply."
}
```

**Errors**:
- `404` if `session_id` not found
- `500` if Redis write fails

---

### `POST /tone/undo/{session_id}`

Restores working copy values from the pre-suggestion snapshot saved by `suggest_tone_rewrite`. The snapshot is stored in Redis under key `tone-snapshot:{template_name}:{session_id}`.

**Path parameters**: `session_id` (string)

**Request body** (optional — omit to undo all):

```json
{
  "keys": ["EN.PARAGRAPH_1"]
}
```

**Behaviour**:

1. Reads snapshot from Redis key `tone-snapshot:{template_name}:{session_id}`
2. If `keys` is provided, restores only those keys; otherwise restores all keys in the snapshot
3. For keys whose snapshot value is `SNAPSHOT_NONE_SENTINEL` (meaning the key had no override before the suggestion): removes the key from the working copy hash via `HDEL`
4. For other keys: restores the previous value via `HSET`
5. If `keys` is null (full undo): deletes the snapshot key from Redis
6. Returns count of restored keys

**Response** `200 OK`:

```json
{
  "restored": 2,
  "message": "Restored 2 placeholder(s).",
  "snapshot_cleared": true
}
```

`snapshot_cleared` is `true` only when a full undo was performed (no `keys` filter).

If no snapshot exists:

```json
{
  "restored": 0,
  "message": "No tone suggestion snapshot found for this session.",
  "snapshot_cleared": false
}
```

**Errors**:
- `404` if `session_id` not found

---

## 10. Health endpoint

### `GET /health`

Returns the connection and load status of all backend dependencies. Polled by the React app every 30 seconds to update the status bar.

**Response** `200 OK`:

```json
{
  "status": "ok",
  "components": {
    "postgres": {
      "status": "ok",
      "latency_ms": 2
    },
    "redis": {
      "status": "ok",
      "latency_ms": 1
    },
    "go_emotions": {
      "status": "ok",
      "model": "monologg/bert-base-cased-goemotions-original"
    },
    "adk": {
      "status": "ok",
      "active_sessions": 3
    }
  }
}
```

Component status values: `"ok"` | `"degraded"` | `"unavailable"`

Top-level `status` is `"ok"` if all components are `"ok"`, `"degraded"` if any are `"degraded"`, `"unavailable"` if any critical component (postgres or redis) is `"unavailable"`.

This endpoint never returns a non-200 status code — the React app reads the JSON body to determine component health.

---

## 11. FastAPI project structure

```
api/
├── main.py                  ← FastAPI app, lifespan handler, CORS, router mounts
├── state.py                 ← singletons: session_service, runners, db_pool, redis, classifier
├── routers/
│   ├── session.py           ← POST /session
│   ├── templates.py         ← GET /templates, /locales, /brands
│   ├── chat.py              ← POST /chat/stream (SSE)
│   ├── working_copy.py      ← GET/PATCH/DELETE /working-copy/{sid}, GET /export
│   ├── preview.py           ← GET /preview/{sid}
│   ├── tone.py              ← POST /evaluate, GET /stored, POST /apply, POST /undo
│   └── health.py            ← GET /health
├── models/
│   ├── requests.py          ← Pydantic request models
│   └── responses.py         ← Pydantic response models
└── middleware/
    └── session_guard.py     ← dependency that validates session_id on relevant endpoints
```

### `main.py` lifespan handler

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api import state
from shared.db import get_pool
from shared.redis_client import get_redis
from template_assistant.ml.goemotions import get_classifier

@asynccontextmanager
async def lifespan(app: FastAPI):
    state.db_pool = await get_pool()
    state.redis_client = await get_redis()
    state.classifier = get_classifier()   # blocks until model is loaded (~10s first run)
    yield
    await state.db_pool.close()
    await state.redis_client.aclose()

app = FastAPI(lifespan=lifespan)
```

### Session guard dependency

Used on all endpoints that require a valid session:

```python
# api/middleware/session_guard.py
from fastapi import Depends, HTTPException
from api.state import session_service

async def require_session(session_id: str) -> dict:
    session = await session_service.get_session(
        app_name="template_assistant",
        user_id="default",
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail={
            "error": "SessionNotFound",
            "message": f"No session found for session_id: {session_id}"
        })
    return session.state
```

Usage in a router:

```python
@router.get("/working-copy/{session_id}")
async def get_working_copy(
    session_id: str,
    session_state: dict = Depends(require_session),
):
    ...
```

---

## 12. SSE implementation detail

```python
# api/routers/chat.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from api.state import template_runner, general_runner
import json

router = APIRouter()

@router.post("/chat/stream")
async def chat_stream(body: ChatStreamRequest):
    runner = template_runner if body.agent == "template" else general_runner

    async def generate():
        try:
            async for event in runner.run_async(
                user_id="default",
                session_id=body.session_id,
                new_message=body.message,
            ):
                # Tool call started
                if event.get_function_calls():
                    tool_name = event.get_function_calls()[0].name
                    yield f"data: {json.dumps({'type': 'tool', 'name': tool_name})}\n\n"

                # Partial text token
                elif event.content and not event.is_final_response():
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            yield f"data: {json.dumps({'type': 'token', 'text': part.text})}\n\n"

                # Final response
                elif event.is_final_response():
                    text = event.content.parts[0].text if event.content else ""

                    # Check if a diff is pending in session state
                    session = await session_service.get_session(
                        app_name="template_assistant",
                        user_id="default",
                        session_id=body.session_id,
                    )
                    diff = None
                    if session and session.state.get("pending_suggestions"):
                        pending = session.state["pending_suggestions"]
                        diff = {
                            "suggestions": pending,
                            "snapshot_overwritten": session.state.get("snapshot_overwritten", False),
                        }

                    yield f"data: {json.dumps({'type': 'final', 'text': text, 'diff': diff})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

---

## 13. React API client

All API calls from React go through a thin client wrapper in `src/api/client.ts`:

```typescript
const BASE_URL = process.env.REACT_APP_API_URL ?? 'http://localhost:8000';

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.error ?? 'UnknownError', body.message ?? '');
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
```

SSE streaming uses the native `fetch` + `ReadableStream` API, not `EventSource`, because `EventSource` does not support `POST` requests:

```typescript
// src/api/chat.ts
export async function streamChat(
  payload: ChatStreamRequest,
  onToken: (text: string) => void,
  onTool: (name: string) => void,
  onFinal: (text: string, diff: DiffPayload | null) => void,
  onError: (message: string) => void,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      if (!part.startsWith('data: ')) continue;
      const event = JSON.parse(part.slice(6));

      if (event.type === 'tool')   onTool(event.name);
      if (event.type === 'token')  onToken(event.text);
      if (event.type === 'final')  onFinal(event.text, event.diff ?? null);
      if (event.type === 'error')  onError(event.message);
    }
  }
}
```

---

## 14. Running the backend

```bash
# Install dependencies
pip install fastapi uvicorn google-adk asyncpg redis trafilatura transformers torch

# Start API server (single worker — required for in-memory ADK sessions)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload

# Start React dev server
cd frontend && npm start   # proxies /api/* to localhost:8000
```

Add to `frontend/package.json` to avoid CORS during development:

```json
{
  "proxy": "http://localhost:8000"
}
```

With the proxy in place, React calls `/session` and FastAPI receives it at `http://localhost:8000/session` — no CORS headers needed in development.