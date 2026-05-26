# Feature Specification: Refactor Tone Suggestion Subagent

**Feature Branch**: `009-refactor-tone-suggestion-subagent`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Refactor the ToneSuggestionSubagent implementation in
`template_assistant/subagents/tone_suggestion_subagent.py` to fix a set of identified
ADK anti-patterns and correctness bugs."

## Permitted file changes

The following files and only these files may be modified or created by this spec:

| File | Change type |
|---|---|
| `template_assistant/subagents/tone_suggestion_subagent.py` | Full rewrite |
| `template_assistant/context.py` | Targeted additions only (new error classes) |
| `template_assistant/models.py` | Conditional addition only (see FIX-10 audit) |

No other files change. All existing tests for `ResolutionSubagent`,
`WorkingCopySubagent`, `ToneEvaluationSubagent`, and `TemplateAssistantAgent` must
pass without modification.

## Fix index

This spec resolves the following identified issues. Each FR below is tagged with the
fix it implements.

| Fix | Description |
|---|---|
| FIX-01 | Replace `after_agent_callback` event scraping with `finalize_rewrites` tool |
| FIX-02 | Replace `before_agent_callback` DB/Redis I/O with `load_eligible_keys` tool |
| FIX-03 | Move snapshot capture into `suggest_tone_rewrite`, remove from `apply_tone_suggestions` |
| FIX-04 | Await `get_pool()` and `get_redis()` in `apply_tone_suggestions` |
| FIX-05 | Remove module-level mutable `_classifier_llm_fn` |
| FIX-06 | Stop using session state as cross-agent message bus for turn-scoped keys |
| FIX-07 | Invalidate `eligible_keys` cache on force reload |
| FIX-08 | Surface `snapshot_overwritten` warning to user |
| FIX-09 | Cross-validate `suggestion_id` at apply time |
| FIX-10 | Fix `resolved_body`/`resolved_keys` field name mismatch |
| FIX-11 | Return `snapshot_cleared` from `undo_tone_suggestions` and delete snapshot on full undo |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Suggestion generation via tool (Priority: P1)

The system generates tone suggestions reliably without relying on event scraping or
fragile callbacks.

**Why this priority**: Core functionality of the agent; fixing the event scraping
anti-pattern ensures stability across ADK versions and prevents silent failures on
malformed JSON.

**Independent test**: Can be tested by invoking the suggest flow and verifying that
`SuggestAgent` uses the `finalize_rewrites` tool to emit its suggestions, and that
the suggestions are correctly stored in the tool context state.

**Acceptance scenarios**:

1. **Given** a valid template with tone-bearing keys, **When** the suggest flow is
   triggered, **Then** `SuggestAgent` calls `finalize_rewrites` with its JSON output
   as a tool call, not via a callback.
2. **Given** `SuggestAgent` emits malformed JSON as the `rewrites` parameter,
   **When** `finalize_rewrites` processes the input, **Then** the tool returns a
   structured error dict with `error` and `message` fields; no exception propagates
   to the user.
3. **Given** `SuggestAgent` includes hallucinated keys or unchanged values in its
   output, **When** `finalize_rewrites` processes the input, **Then** hallucinated
   keys and unchanged values are discarded and only valid, changed suggestions are
   written to state.

---

### User Story 2 — Resilient eligible keys loading (Priority: P1)

The system loads eligible keys explicitly via a tool, handling database or cache
unavailability gracefully.

**Why this priority**: Prevents silent callback failures and provides clear error
messages to the user when backend services are unreachable.

**Independent test**: Can be tested by simulating a database or Redis outage during
the suggest flow and verifying the user receives a structured error message instead
of a callback exception.

**Acceptance scenarios**:

1. **Given** healthy DB and Redis connections, **When** the orchestrator starts the
   suggest flow, **Then** it calls `load_eligible_keys` and successfully retrieves
   and caches the eligible keys in `session.state`.
2. **Given** an unreachable DB or Redis, **When** the orchestrator calls
   `load_eligible_keys`, **Then** the tool returns `{"error": ..., "message": ...}`
   and the orchestrator relays a plain message to the user without raising an
   unhandled exception.
3. **Given** a new suggest flow within the same session, **When** the orchestrator
   calls `load_eligible_keys` with `force_reload=True`, **Then** the stale
   `eligible_keys` cache is cleared and rebuilt from the current working copy and
   resolution graph.

---

### User Story 3 — Correct snapshot lifecycle (Priority: P2)

The system captures undo snapshots at the correct time (during suggestion generation)
and properly clears them upon full undo.

**Why this priority**: Ensures users can safely undo suggestions without snapshots
being overwritten prematurely or lingering in Redis indefinitely.

**Independent test**: Can be tested by generating multiple batches of suggestions and
verifying the snapshot is captured during generation, and by performing a full undo
and verifying the snapshot Redis hash is deleted.

**Acceptance scenarios**:

1. **Given** no existing snapshot, **When** `suggest_tone_rewrite` is called,
   **Then** a snapshot is captured in Redis before the rewrite prompt is built and
   the payload includes `snapshot_saved: true`.
2. **Given** an existing snapshot from a prior suggestion batch, **When** a second
   `suggest_tone_rewrite` call runs in the same session, **Then** the payload
   includes `snapshot_overwritten: true` and the orchestrator prepends the defined
   warning to the diff presentation before asking the user to confirm.
3. **Given** a full undo request (`keys=None`), **When** `undo_tone_suggestions`
   completes, **Then** the Redis hash at `tone-snapshot:{template_name}:{session_id}`
   is deleted and the tool returns `snapshot_cleared: true`.
4. **Given** a partial undo request (`keys=["EN.PARAGRAPH_1"]`), **When**
   `undo_tone_suggestions` completes, **Then** the snapshot Redis hash remains and
   the tool returns `snapshot_cleared: false`.

---

### User Story 4 — Robust state and dependency management (Priority: P2)

The system enforces proper initialization of singletons, avoids shared mutable state
across sessions, and explicitly passes turn-scoped dependencies between subagents.

**Why this priority**: Prevents cold-start failures, cross-session test bleeding, and
non-deterministic ordering between specialist subagents.

**Independent test**: Can be tested by running the apply flow from a cold start,
running concurrent tests with a monkeypatched classifier, and verifying `SuggestAgent`
raises `MissingClassificationError` when invoked without `tone_bearing_keys`.

**Acceptance scenarios**:

1. **Given** a cold start where `get_pool()` and `get_redis()` have not yet been
   initialized, **When** `apply_tone_suggestions` is called, **Then** both getters
   are properly awaited and no coroutine-object errors occur.
2. **Given** concurrent test sessions where `_default_classifier_llm` is
   monkeypatched in one test, **When** a second test runs concurrently, **Then** the
   monkeypatch does not bleed into the second session.
3. **Given** the orchestrator delegates to `SuggestAgent` without first running
   `KeyClassifierAgent`, **When** `_suggest_tone_rewrites_tool` is called without a
   `tone_bearing_keys` parameter, **Then** a `MissingClassificationError` is raised
   and its `to_payload()` dict is returned to the orchestrator.

---

### Edge cases

- **Malformed JSON to `finalize_rewrites`**: `finalize_rewrites` catches
  `json.JSONDecodeError` and `ValueError` from `_parse_llm_rewrites` and returns
  `{"error": "parse_error", "message": "SuggestAgent returned invalid JSON."}`.
  No exception propagates.
- **DB/Redis failure during `load_eligible_keys`**: Returns structured error dict;
  orchestrator presents the `message` field as a plain user-facing message and stops
  the suggest flow.
- **`suggestion_id` mismatch at apply time**: `apply_tone_suggestions` raises
  `SuggestionIdMismatchError`; its `to_payload()` dict is returned and the
  orchestrator informs the user that the suggestion batch has expired.
- **`undo_tone_suggestions` with no snapshot**: Returns
  `{"restored": 0, "snapshot_cleared": false, "message": "No tone suggestion
  snapshot found for this session."}` — no exception raised.
- **All keys classified as structural (empty `tone_bearing_keys`)**: This is a valid
  state, not an error. `_suggest_tone_rewrites_tool` returns
  `{"message": "No eligible keys found for tone rewriting."}`. `MissingClassificationError`
  is only raised when `tone_bearing_keys` is absent from the tool call entirely.

---

## Requirements *(mandatory)*

### Functional requirements

**FR-001** *(FIX-01)*: `SuggestAgent` MUST emit rewrites by calling `finalize_rewrites`
as a registered ADK tool call, passing its JSON output as the `rewrites: list[dict]`
parameter. `finalize_rewrites` MUST appear in `SuggestAgent`'s `tools=[]` list. It
MUST NOT be invoked from a callback or as a plain Python function call. `after_agent_callback`
on `SuggestAgent` and the `pending_suggest_rewrite` session state key are removed entirely.

**FR-002** *(FIX-01)*: `finalize_rewrites(rewrites: list[dict], tool_context: ToolContext)`
MUST:
- Validate each key in `rewrites` against `tool_context.state["eligible_keys"]`,
  discarding hallucinated keys.
- Filter out rewrites where `new_value` equals the current value.
- Catch `json.JSONDecodeError` and `ValueError` from parsing and return a structured
  error dict instead of raising.
- On success, write to `tool_context.state`:
  - `suggestions`: list of dicts, each with `key`, `old_value`, `new_value`,
    `suggestion_id`.
  - `suggestion_id`: str (carried through from state, not regenerated).
  - `discarded_keys` (optional): list of dicts describing discarded items.
- MUST NOT write `tone_bearing_keys` or `structural_keys` to state — those are
  turn-scoped only.
- Return `{"accepted": int, "discarded": int, "suggestions": list}` on success, or
  `{"error": str, "message": str}` on parse failure.

**FR-003** *(FIX-02)*: `load_eligible_keys(force_reload: bool, tool_context: ToolContext)`
MUST:
- Appear in `ToneSuggestionSubagent`'s `tools=[]` list (the orchestrator's own tools),
  not on any specialist subagent.
- Be called by the orchestrator as its first action at the start of every suggest flow.
- If `force_reload=False` and `eligible_keys` is already present in state, return the
  cached value immediately without any DB or Redis calls.
- If `force_reload=True`, clear `session.state["eligible_keys"]` before rebuilding.
- On DB or Redis failure, return `{"error": str, "message": str}` — MUST NOT raise an
  exception.
- On success, write `eligible_keys` to `tool_context.state` and return
  `{"eligible_keys": dict, "total": int}`.
- The orchestrator instruction MUST include: "If `load_eligible_keys` returns a dict
  containing an `error` key, relay the `message` value to the user as a plain sentence
  and stop the suggest flow."
- `before_agent_callback` on `ToneSuggestionSubagent` is removed entirely.

**FR-004** *(FIX-03)*: `capture_snapshot` MUST be called inside `suggest_tone_rewrite`
immediately after eligible keys are resolved and before the rewrite prompt is built,
so the snapshot reflects the exact values shown to the user in the diff.
`apply_tone_suggestions` MUST NOT call `capture_snapshot`.

**FR-005** *(FIX-03)*: `suggest_tone_rewrite` MUST return a payload with exactly these
fields: `rewrite_prompt` (str), `eligible_keys` (list), `target_emotions` (dict),
`baseline_emotions` (dict), `suggestion_id` (str), `snapshot_saved` (bool),
`snapshot_overwritten` (bool).

**FR-006** *(FIX-03, FIX-08)*: The orchestrator instruction MUST include: "If
`suggest_tone_rewrite` returns `snapshot_overwritten: true`, prepend the following
warning to the diff presentation before asking the user to confirm: 'Note: applying
these suggestions will replace the undo snapshot from your previous suggestion batch.
You will not be able to undo that earlier batch individually after confirming.'"

**FR-007** *(FIX-04)*: `apply_tone_suggestions` MUST `await` calls to `get_pool()`
and `get_redis()`. It MUST NOT call `capture_snapshot`. It MUST NOT include
`snapshot_overwritten` in its return shape.

**FR-008** *(FIX-05)*: The module-level mutable `_classifier_llm_fn` and the function
`set_classifier_llm_fn()` MUST be removed. Tests that need to override the LLM
classification call MUST use `monkeypatch` on `_default_classifier_llm` at the module
level via the standard pytest fixture pattern.

**FR-009** *(FIX-06)*: `KeyClassifierAgent`'s tool MUST return its classification
result directly in its tool return value. The orchestrator MUST read `tone_bearing_keys`
from that return value and pass it explicitly as a parameter to
`_suggest_tone_rewrites_tool`. `_suggest_tone_rewrites_tool` MUST accept
`tone_bearing_keys: dict` as an explicit parameter and MUST raise
`MissingClassificationError` if this parameter is absent. `tone_bearing_keys` and
`structural_keys` MUST NOT be written to or read from `session.state`.

**FR-010** *(FIX-07)*: `load_eligible_keys` MUST clear `session.state["eligible_keys"]`
before rebuilding when called with `force_reload=True`. The orchestrator MUST always
call `load_eligible_keys(force_reload=True)` at the start of each new suggest flow
to ensure working copy changes since the last turn are reflected.

**FR-011** *(FIX-09)*: `apply_tone_suggestions` MUST verify that every suggestion in
the confirmed list carries a `suggestion_id` matching `session.state["suggestion_id"]`
before writing to Redis. On mismatch, it MUST raise `SuggestionIdMismatchError`.

**FR-012** *(FIX-10)*: Before any code is written for this fix, `services.py` MUST be
audited to determine the return type of `resolve_template`. The audit finding MUST be
recorded as a comment at the top of the implementation task for FIX-10. Two branches:
- If `services.resolve_template` wraps `shared/resolution/resolver.ResolutionResult`,
  all field access sites in `tone_suggestion_subagent.py` MUST be updated to use
  `resolved_text` (not `resolved_body`) and `unresolvable_keys` (not `resolved_keys`).
- If `services.resolve_template` returns its own type, a `ServiceResolutionResult`
  dataclass with fields `resolved_body` (str), `resolved_keys` (set[str]), and
  `unresolvable_keys` (list) MUST be added to `models.py` and the type annotation on
  `services.resolve_template` updated accordingly.

**FR-013** *(FIX-11)*: `undo_tone_suggestions` MUST always include `snapshot_cleared: bool`
in its return dict. On full undo (`keys=None`), it MUST delete the Redis hash at
`tone-snapshot:{template_name}:{session_id}` and return `snapshot_cleared: true`. On
partial undo (`keys` is a non-empty list), it MUST leave the snapshot hash intact and
return `snapshot_cleared: false`.

**FR-014** *(FIX-01, FIX-02)*: `MissingClassificationError` and
`SuggestionIdMismatchError` MUST be added to `template_assistant/context.py`, alongside
the existing `SessionContextMissingError`. Both MUST implement a `to_payload() -> dict[str, Any]`
method returning a dict the orchestrator can relay directly to the user.

**FR-015** *(FIX-06)*: After a full suggest→confirm→apply cycle, the only
tone-suggestion-related keys present in `session.state` MUST be: `eligible_keys`,
`suggestions`, `suggestion_id`. The keys `tone_bearing_keys`, `structural_keys`, and
`pending_suggest_rewrite` MUST NOT be present in state at any point after this refactor
is deployed.

---

### Key entities

- **Suggestion**: A proposed rewrite for a specific template key, including the
  original value, suggested value, and a `suggestion_id` field linking it to the
  batch it belongs to.
- **Snapshot**: A Redis hash capturing the template's working copy values for the keys
  involved in a suggestion batch, written before the rewrite prompt is generated.
  Used for undo. Key format: `tone-snapshot:{template_name}:{session_id}`.
- **Eligible keys**: The set of template keys that pass reachability and content
  eligibility filters for a given turn. Cached in `session.state["eligible_keys"]`.
  Turn-scoped rebuilding is forced via `load_eligible_keys(force_reload=True)`.

---

## Success criteria *(mandatory)*

### Measurable outcomes

**SC-001**: No callbacks remain in `tone_suggestion_subagent.py`. Verified by:
```
grep -n "callback" template_assistant/subagents/tone_suggestion_subagent.py
# must return zero results
```

**SC-002**: No module-level mutable classifier function remains. Verified by:
```
grep -n "classifier_llm_fn" template_assistant/subagents/tone_suggestion_subagent.py
# must return zero results
```

**SC-003**: Snapshot is captured at suggest time, not apply time. Verified by
`test_suggest_tone_rewrite_snapshot_saved_before_prompt`: asserts the Redis hash
`tone-snapshot:{template_name}:{session_id}` exists after `suggest_tone_rewrite`
returns and before any call to `apply_tone_suggestions`.

**SC-004**: Snapshot overwrite warning is visible in the agent's response. Verified by
`test_second_suggest_before_undo_shows_warning` (e2e): a second suggest call within
the same session produces an agent response containing the exact phrase "undo snapshot
from your previous suggestion batch".

**SC-005**: Full undo clears the snapshot Redis hash. Verified by
`test_undo_full_clears_snapshot_hash`: after `undo_tone_suggestions(keys=None)`,
the key `tone-snapshot:{template_name}:{session_id}` does not exist in Redis.

**SC-006**: DB failure during `load_eligible_keys` surfaces as a user-facing message,
not an unhandled exception. Verified by `test_load_eligible_keys_db_failure_returns_error_dict`:
asserts the return value contains `error` (str) and `message` (str) and that no
exception is raised.

**SC-007**: `tone_bearing_keys` and `structural_keys` are absent from `session.state`
after a full suggest→apply cycle. Verified by
`test_post_apply_state_keys_are_clean`: asserts the two keys are not present in state
after `apply_tone_suggestions` completes.

**SC-008**: Zero regression. Running `pytest template_assistant/tests/ -x` produces
zero failures across all 9 test files.

---

## Assumptions

- The existing `shared/db.py` and `shared/redis_client.py` interfaces already support
  `await` on their getter functions.
- The `KeyClassifierAgent`, `SuggestAgent`, `ApplyAgent`, and `UndoAgent` names,
  descriptions, and position in the `sub_agents=[]` hierarchy are unchanged.
- Redis key formats are unchanged:
  - Working copy: `working-copy:{template_name}:{session_id}`
  - Tone snapshot: `tone-snapshot:{template_name}:{session_id}`
- The internal utility functions `_build_reachable_eligible`, `classify_keys`,
  `capture_snapshot`, `evaluate_eligibility`, `_apply_structural_heuristics`,
  `_llm_classify_keys`, `_build_llm_prompt`, `_parse_llm_rewrites`, and
  `_validate_llm_rewrites` are not modified by this spec. Only their invocation sites
  within the tool functions change.
- The `pending_suggest_rewrite` state key, if present in any live session at deploy
  time, is silently ignored by the new code. It is never read; no error is raised on
  its presence.
- `finalize_rewrites` can be seamlessly integrated into `SuggestAgent`'s `tools=[]`
  list without requiring changes to the ADK agent configuration outside of
  `tone_suggestion_subagent.py`.
- The `services.py` audit (FR-012) is a prerequisite task — no FIX-10 code is written
  until the audit finding is recorded.