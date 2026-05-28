# Feature Specification: Initialize Working Copy Endpoint

**Feature Branch**: `014-init-working-copy-endpoint`

**Created**: 2026-05-28

**Status**: Draft

**Input**: Add a FastAPI endpoint that initializes the session working copy the same way
tone placeholder discovery works: inspect the template body (plain text first, HTML if no
text), keep only tone-relevant placeholder keys, seed each key with its current resolved
value or `''`, and return the existing working copy unchanged when Redis already has
entries. Extend the template preview API so unresolvable placeholder scanning uses the same
resolution pipeline as `scripts/scan_all_template_unresolvables.py` (per-template, session
context, HTML + text bodies).

**Related specs**: `003-tone-suggestion-validation`, `004-tone-suggestion-reachability-pre-filter`,
`012-fast-api-wrapper`, `011-agent-studio-ui/contracts/working_copy_init.md`

**Reference implementation**: `scripts/scan_all_template_unresolvables.py`

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — First open populates editable keys (Priority: P1)

A template author opens a template in Agent Studio after `POST /session`. The UI calls
initialize working copy instead of driving ADK tools. The API discovers which placeholders
affect tone in the rendered email, writes their current values into Redis, and returns the
full override list for the working-copy table.

**Why this priority**: Without initialization, the UI shows an empty editor until the user
manually patches keys or runs tone suggestion. This is the primary onboarding path.

**Independent Test**: Create a session for a template with known `EN.*` prose keys, call
`POST /working-copy/{session_id}/init` on an empty Redis hash, assert `200` with
`initialized: true`, non-empty `overrides`, and Redis contains the same key/value pairs.

**Acceptance Scenarios**:

1. **Given** no Redis hash for `working-copy:{template}:{session}`, **When** init is called,
   **Then** the response lists every tone-eligible reachable key with its resolved value or
   `''` when resolution fails.
2. **Given** a template whose `template_details.text` is non-empty, **When** init runs,
   **Then** reachability is computed from the **text** body only (HTML is not scanned for
   token discovery).
3. **Given** a template whose `text` is empty or whitespace-only and `html` is non-empty,
   **When** init runs, **Then** reachability is computed from the **HTML** body.
4. **Given** both `text` and `html` are empty, **When** init runs, **Then** the response
   returns `initialized: true`, `overrides: []`, and no Redis write occurs.

---

### User Story 2 — Idempotent return when already initialized (Priority: P1)

If the author refreshes the page or the UI retries init, an existing working copy must not
be overwritten.

**Why this priority**: Prevents accidental loss of in-progress edits.

**Independent Test**: Seed Redis with one override, call init again, assert Redis unchanged
and `initialized: false`, `source: "existing"`.

**Acceptance Scenarios**:

1. **Given** Redis hash `working-copy:{template}:{session}` has at least one field,
   **When** init is called, **Then** no keys are added, removed, or updated in Redis.
2. **Given** an existing working copy, **When** init is called, **Then** the response body
   matches `GET /working-copy/{session_id}` for the same overrides (same keys and values).

---

### User Story 3 — Same key set as tone placeholder discovery (Priority: P2)

Operators expect the working copy table to list the same keys the tone subsystem would
offer for rewrite (reachable + content eligibility), not every graph key.

**Why this priority**: Consistency between UI, tone suggestion, and resolution preview.

**Independent Test**: For one template/session, compare key sets from init response and from
`load_eligible_keys(force_reload=True)` (or shared service extractor); they must be identical.

**Acceptance Scenarios**:

1. **Given** session context `lang_local=EN`, `param_cust_brand=SKRILL`, **When** init
   builds keys, **Then** each key passes `evaluate_eligibility` from
   `tone_suggestion_subagent.py` using working-copy-first value resolution order.
2. **Given** a graph key that is not visited when resolving the selected body, **When** init
   runs, **Then** that key is excluded even if present in the resolution graph.
3. **Given** a reachable key whose resolved value is a bare `##TOKEN##` chain or URL,
   **When** init runs, **Then** that key is excluded (same rules as tone eligibility).

---

### Edge Cases

- Session missing or unknown `session_id` → `404 SessionNotFound` (same as other
  session-scoped routes).
- Redis unavailable → `503 RedisUnavailable`; no partial hash writes.
- Key resolves to `ReasonCode` failure → stored value `''` in working copy (key still
  included if tone-eligible and reachable).
- Synthetic preprocessor keys (`__SM_RULE_BRAND_COLOR__`, etc.) are never written; only
  canonical graph keys that appear in the eligible set.
- Namespace-expanded tokens in the body (e.g. `##LANG_LOCAL.PARAGRAPH_1##`) contribute
  canonical keys (`EN.PARAGRAPH_1`) to reachability per existing resolver behaviour.
- Init does not create or overwrite tone snapshots (`working-copy-snapshot:…`).

---

### User Story 4 — Preview surfaces full unresolvable scan (Priority: P2)

After opening a template, the author loads the preview panel and sees which placeholders
still fail resolution under the active `lang_local` / `param_cust_brand`, with reasons and
detail text — the same information the offline scan script produces for one template.

**Why this priority**: Data-quality visibility in the UI removes the need to run a separate
CLI scan when debugging a single template session.

**Independent Test**: For a fixture template with a known missing key in HTML and another in
text only, `GET /preview/{session_id}` returns both keys in `unresolvable_keys` with `detail`
populated and correct `reason` codes.

**Acceptance Scenarios**:

1. **Given** a session with working copy overrides, **When** preview is requested, **Then**
   resolution uses the working copy hash and unresolvables reflect override-aware resolution.
2. **Given** a template with both `html` and `text` bodies, **When** preview scans
   unresolvables, **Then** results are the deduplicated union of HTML and text scans (same
   merge rule as `scan_all_template_unresolvables.py`).
3. **Given** a key fails in HTML with reason `MISSING_KEY`, **When** preview returns the
   entry, **Then** `detail` includes human-readable context from `UnresolvableEntry.detail`
   (e.g. cycle path), not only the reason code.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The API MUST expose `POST /working-copy/{session_id}/init` on the FastAPI
  service (prefix and session guard consistent with `012-fast-api-wrapper`).
- **FR-002**: The endpoint MUST require a valid ADK session with `template_name`,
  `lang_local`, `param_cust_brand`, and `session_id` in session state (same as
  `PATCH /working-copy/{session_id}`).
- **FR-003**: Before any write, the endpoint MUST read Redis hash
  `working-copy:{template_name}:{session_id}`. If the hash contains **one or more** fields,
  the endpoint MUST return the current overrides and MUST NOT modify Redis.
- **FR-004**: When the hash is empty, the endpoint MUST build the tone placeholder key set
  using the **same rules** as `_build_reachable_eligible` in
  `template_assistant/subagents/tone_suggestion_subagent.py`:
  - Load resolution graph for `template_name`
  - Determine reachability via `resolve_body` on a **single** template body (see FR-005)
  - For each graph key in `resolved_keys`, evaluate eligibility with
    `evaluate_eligibility(key, value, lang_local, param_cust_brand)` where `value` is the
    working-copy value if present (always empty on first init) else the raw graph value
- **FR-005**: Body selection for reachability MUST differ from `resolve_template()` today:
  1. Load `template_details.text` and `template_details.html` for the template
  2. If `text` trimmed is non-empty → run `resolve_body` **only** on `text` (still uses full
     graph + session context + Redis for transitive resolution)
  3. Else if `html` trimmed is non-empty → run `resolve_body` **only** on `html`
  4. Else → eligible set is empty; return without Redis writes
- **FR-006**: For each key in the eligible set, the endpoint MUST compute the value to store:
  - Call shared single-key resolution (`resolve_key`) with session context
  - If resolution returns a string → use that string
  - If resolution returns `None` or only unresolvable entries → use `''`
- **FR-007**: The endpoint MUST write all eligible keys to Redis in one logical operation
  (`HSET` per key or pipelined batch). Either all writes succeed or none are persisted.
- **FR-008**: Response schema MUST extend `WorkingCopyResponse` (or equivalent) with:
  - `initialized: bool` — `true` when Redis was populated this call; `false` when returning
    existing data
  - `source: "created" | "existing"` — how the payload was produced
  - `tone_key_count: int` — number of keys in the eligible set (even when `source` is
    `existing`, report count of keys that *would* be eligible on fresh init for UI hints)
- **FR-009**: Shared logic for tone key discovery MUST be extracted to a reusable service
  function (e.g. `template_assistant/services.py`:
  `build_tone_eligible_keys(session_context) -> dict[str, str]`) used by both this endpoint
  and `load_eligible_keys` to prevent drift.
- **FR-010**: `POST /session` behaviour is unchanged; clients that want a pre-populated table
  MUST call `POST /working-copy/{session_id}/init` after session creation (UI migration).
- **FR-011**: Init MUST NOT invoke ADK runners, LLM calls, or KeyClassifierAgent — only
  deterministic graph + resolution + eligibility filters.

### API Contract

#### `POST /working-copy/{session_id}/init`

**Purpose**: Idempotently ensure the working copy hash contains all tone-editable placeholder
keys for the active template and session context.

**Steps**:

```
1. require_session → session_state
2. wc = HGETALL working-copy:{template}:{session}
3. if wc non-empty:
     return { overrides: wc, initialized: false, source: "existing", ... }
4. graph = build_resolution_graph(template_name)
5. body = text if text.strip() else html if html.strip() else ""
6. if body empty → return { overrides: [], initialized: true, source: "created", tone_key_count: 0 }
7. resolved = resolve_body(body) → resolved_keys
8. eligible = { k: resolve_value(k) for k in graph if k in resolved_keys and evaluate_eligibility(...) }
9. HSET all eligible keys to Redis
10. return { overrides: eligible, initialized: true, source: "created", tone_key_count: len(eligible) }
```

**Response** `200 OK` (same override shape as GET):

```json
{
  "session_id": "uuid-…",
  "overrides": [
    { "key": "EN.PARAGRAPH_1", "value": "Dear customer, …", "set_at": null }
  ],
  "total_overrides": 12,
  "session_has_changes": true,
  "initialized": true,
  "source": "created",
  "tone_key_count": 12
}
```

When returning existing working copy:

```json
{
  "session_id": "uuid-…",
  "overrides": [ … ],
  "total_overrides": 3,
  "session_has_changes": true,
  "initialized": false,
  "source": "existing",
  "tone_key_count": 12
}
```

**Errors**: Same codes as `012-fast-api-wrapper` working-copy routes (`404` session/template,
`503` Redis, `500` on unexpected resolution failures).

---

## Template preview: unresolvable scanning

Extend `GET /preview/{session_id}` (and shared preview service logic) so unresolvable
placeholder discovery matches the per-template scan in
`scripts/scan_all_template_unresolvables.py`. The batch script remains the operator tool for
catalog-wide reports; the API exposes the same **single-template** behaviour for an active
session.

### Problem

Today `api/services/preview.py` already merges HTML and text unresolvables, but:

- `UnresolvableKey` omits `detail` from `UnresolvableEntry` (cycle paths, missing branch
  targets, etc.).
- `total_placeholders` / `resolved_count` use `len(graph)` (all content-block keys), which
  misrepresents tokens actually present in the template bodies — unlike the script, which
  reports only keys that failed during body resolution.
- Scan logic is duplicated inline rather than shared with the script, risking drift as
  preprocessors and SM_RULE parsing evolve.

### Scan semantics (aligned with script)

For one template and resolution context:

```
1. graph = build_resolution_graph(template_name)  [or session cache]
2. context = { LANG_LOCAL, PARAM_CUST_BRAND } from session
3. html_body, text_body = fetch_template_bodies(template_name)
4. accumulated_keys = ∅
5. by_key = {}   # canonical key → UnresolvableEntry
6. if html_body.strip():
     result_html = resolve_body(html, context, session_id, working_copy)
     merge into by_key (first wins per key)
7. if text_body.strip():
     result_text = resolve_body(text, context, session_id, working_copy)
     merge into by_key (append keys not already present)
8. unresolvable_keys = sorted(by_key.values(), key=key)
```

**Differences from working-copy init (FR-005)**:

| Aspect | Init (`POST …/init`) | Preview / scan |
|--------|----------------------|----------------|
| Bodies used | **One**: text, else html | **Both**: html and text when non-empty |
| Purpose | Seed tone-editable keys | Report resolution failures in rendered output |
| Working copy | Writes eligible keys | Reads existing overrides only |

### Functional requirements (preview)

- **FR-012**: Extract shared service
  `scan_template_unresolvables(session_context, *, graph, include_html=True, include_text=True) -> list[UnresolvableEntry]`
  in `template_assistant/services.py` (or `api/services/resolution_scan.py`) implementing
  steps 1–8 above. `scripts/scan_all_template_unresolvables.py` MUST call this helper for
  `_scan_template` instead of inlining `resolve_body` merges.
- **FR-013**: `build_preview` MUST use `scan_template_unresolvables` for `unresolvable_keys`
  rather than ad-hoc merge in `api/services/preview.py`.
- **FR-014**: `UnresolvableKey` response model MUST add optional field `detail: str` (default
  `""`). Map `reason` from `ReasonCode.value` (`MISSING_KEY`, `CYCLE`, `BROKEN_RULE_CHAIN`,
  `INVALID_RULE`); keep `map_unresolvable_reason` only where the UI contract requires
  shortened labels (`MISSING`, `CYCLE`, …) — document both in OpenAPI.
- **FR-015**: Preview metrics MUST be body-accurate:
  - `unresolvable_count` = `len(unresolvable_keys)`
  - `tokens_scanned` = count of distinct `##PLACEHOLDER##` tokens found in scanned bodies
    (html and/or text) before resolution, using `extract_placeholder_keys`
  - `resolved_token_count` = `tokens_scanned - unresolvable_count` (keys appearing in bodies
    that did not surface as unresolvable)
  - Deprecate or repurpose `total_placeholders` / `resolved_count` if they currently mean
    `len(graph)`; prefer new fields or redefine them to match token scan (breaking change
    documented in API changelog).
- **FR-016**: `GET /preview/{session_id}` response MUST include `scan_sources: list[str]` with
  values `"html"` and/or `"text"` indicating which bodies contributed to the scan (empty
  list when both bodies blank).
- **FR-017**: Preview resolution for displayed HTML/text (`resolved_html`, `resolved_text`)
  remains full dual-body resolution as today; only the **unresolvable scan** section follows
  the shared helper (same inputs: session context + working copy).
- **FR-018**: Optional query flag `include_unresolvable_scan=true` (default `true`) on
  `GET /preview/{session_id}` allows clients to skip the scan pass when they only need
  rendered bodies (performance escape hatch).

### API contract: extended `GET /preview/{session_id}`

**Query parameters** (additions):

| Param | Default | Description |
|-------|---------|-------------|
| `highlight_modified` | `true` | Unchanged — green border on WC values |
| `include_unresolvable_scan` | `true` | When `false`, omit scan pass; return empty `unresolvable_keys` |

**Response** `200 OK` (additions / changes):

```json
{
  "resolved_html": "<html>…</html>",
  "resolved_text": "Dear customer, …",
  "unresolvable_keys": [
    {
      "key": "CAMPAIGN_NAME",
      "reason": "MISSING_KEY",
      "detail": ""
    },
    {
      "key": "EN.MISSING_BLOCK",
      "reason": "CYCLE",
      "detail": "A → B → A"
    }
  ],
  "unresolvable_count": 2,
  "tokens_scanned": 47,
  "resolved_token_count": 45,
  "scan_sources": ["html", "text"],
  "evaluated_from": "working_copy",
  "total_placeholders": 47,
  "resolved_count": 45
}
```

`total_placeholders` and `resolved_count` MUST equal `tokens_scanned` and
`resolved_token_count` respectively after this feature (redefined semantics). Clients that
relied on graph-size counts must migrate to explicit graph endpoints if needed later.

### Optional: stateless single-template scan

**Out of scope for v1** unless time permits: `GET /templates/{template_name}/unresolvables`
with required query `lang_local` and `param_cust_brand`, no session — runs the same helper
with a synthetic `session_id` and empty working copy (mirrors script defaults). Catalog-wide
`GET /templates/unresolvables` (all templates) stays CLI-only in v1 due to latency (726+
templates ≈ 40s locally).

### Testing

- Integration test: fixture template, session with `EN`/`SKRILL`, assert preview
  `unresolvable_keys` match direct call to `scan_template_unresolvables`.
- Regression: port one case from `scripts/scan_all_template_unresolvables.py --limit 1`
  into pytest (same keys and reasons).
- Contract test: `detail` present for a seeded `CYCLE` fixture.

---

### Key Entities

- **Working copy**: Redis hash `working-copy:{template_name}:{session_id}`; field = canonical
  uppercase key, value = user-facing resolved string.
- **Tone-eligible key**: Reachable during body resolution AND passes `evaluate_eligibility`.
- **Body source**: Either `text` or `html` from `template_details`, never both for
  reachability in this feature.
- **Session context**: `template_name`, `lang_local`, `param_cust_brand`, `session_id` from
  ADK session state.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: UI can replace ADK `get_eligible_keys` + `get_working_copy` init sequence with
  one HTTP call per template open.
- **SC-002**: 100% of integration tests show identical key sets between init-created working
  copy and `build_tone_eligible_keys` for three fixture templates.
- **SC-003**: Repeat init on a non-empty hash never changes Redis key count (idempotency).
- **SC-004**: Templates with non-empty `text` use text-only reachability in tests (HTML token
  not in `resolved_keys` when token appears only in HTML).
- **SC-005**: Init completes in under 3 seconds for a template with ≤50 tone-eligible keys
  under normal local DB/Redis load.
- **SC-006**: Preview `unresolvable_keys` for a session match the shared scan helper output
  with zero diff in key, reason, and detail.
- **SC-007**: Preview scan completes in under 2 seconds for a template with ≤100 body tokens
  under normal local DB/Redis load (with `include_unresolvable_scan=true`).

---

## Assumptions

- `template_details` continues to store one row per template (no locale/brand row filter in
  SQL); session `lang_local` / `param_cust_brand` affect resolution via namespace expansion
  only.
- “Tone placeholders” means the `_build_reachable_eligible` set, not post-classifier
  `tone_bearing_keys` (classifier is out of scope for init).
- Empty string is an acceptable stored value for keys that appear in the body but fail full
  resolution (author can fill manually).
- `set_at` remains `null` until a future metadata feature adds timestamps.

---

## Clarifications

### Session 2026-05-28

- Q: Text vs HTML for reachability? → A: Prefer `template_details.text`; if absent/blank, use
  `html`; do not union both for this endpoint (differs from `resolve_template()` which
  resolves both when text exists).
- Q: Existing working copy behaviour? → A: If Redis hash has any fields, return as-is; do not
  merge missing tone keys.
- Q: Value when unresolved? → A: Store `''` for eligible reachable keys that fail
  `resolve_key`.
- Q: ADK vs REST? → A: New REST endpoint on FastAPI; optional later refactor of
  `load_eligible_keys` to call shared service.
- Q: Preview scan vs init body selection? → A: Init uses text-or-html (one body); preview scan
  uses html **and** text when both exist, same as `scan_all_template_unresolvables.py`.
- Q: Catalog-wide scan in API? → A: v1 shares per-template logic only; full-catalog scan
  remains the CLI script (optional stateless single-template endpoint deferred).

---

## Out of Scope

- Re-initializing or merging into a partial working copy
- KeyClassifier / `tone_bearing` subset
- Writing to PostgreSQL
- Automatic init inside `POST /session` (explicit client call only in v1)
- Populating `eligible_keys` in ADK session state (UI may continue to use HTTP only)
- Synchronous HTTP endpoint that scans all templates in one request (use CLI script or future
  async job)
