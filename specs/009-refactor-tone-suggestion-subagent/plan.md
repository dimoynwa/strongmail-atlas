# Implementation Plan: Refactor Tone Suggestion Subagent

**Branch**: `009-refactor-tone-suggestion-subagent`
**Date**: 2026-05-26
**Spec**: [spec.md](./spec.md)

## Summary

Refactor `template_assistant/subagents/tone_suggestion_subagent.py` to fix eleven
identified ADK anti-patterns and correctness bugs. The changes replace fragile
`after_agent_callback` event scraping with an explicit `finalize_rewrites` tool call,
replace `before_agent_callback` DB/Redis I/O with an explicit `load_eligible_keys`
tool, correct the snapshot lifecycle so snapshots are captured at suggestion time
rather than apply time, remove the module-level mutable classifier function, stop
using `session.state` as a turn-scoped message bus between specialist subagents, and
fix two correctness bugs (`get_pool`/`get_redis` not awaited, field name mismatch on
resolution results). Targeted additions are made to `context.py` (two new error
classes) and conditionally to `models.py` (see FIX-10 audit). No other files change.

## Technical context

- **Language/version**: Python 3.11+
- **Primary dependencies**: google-adk, asyncpg, redis-py, transformers (GoEmotions),
  trafilatura, litellm
- **Storage**: PostgreSQL (via asyncpg), Redis
- **Testing**: pytest + pytest-asyncio, real PostgreSQL and Redis — no mocks
- **Target platform**: Linux server
- **Constraints**: All existing tests outside `test_tone_suggestion_subagent.py` and
  `test_e2e_agent.py` must pass without modification

## Constitution check

- **Test-first**: Every new or modified tool has named integration tests with explicit
  acceptance criteria listed in the Testing strategy section below.
- **Simplicity**: Removing callbacks and implicit state passing reduces the number of
  execution paths. The new flow is: explicit tool call → explicit return value →
  explicit parameter passing. Nothing is inferred from event history.

---

## Phase 0 — Audit (prerequisite, blocks all implementation)

Before any code is written, complete the following audit and record findings in
`research.md`.

### FIX-10 audit: `services.py` resolve_template return type

Inspect `template_assistant/services.py`. Determine which branch applies:

**Branch A** — `services.resolve_template` wraps `shared/resolution/resolver.ResolutionResult`:
- Record finding: "Branch A — wraps shared ResolutionResult"
- Action: Update all field access sites in `tone_suggestion_subagent.py` from
  `resolved_body` → `resolved_text` and from `resolved_keys` → `unresolvable_keys`
  (for the unresolvable set). No new dataclass needed.

**Branch B** — `services.resolve_template` returns its own type:
- Record finding: "Branch B — own type, add ServiceResolutionResult"
- Action: Add `ServiceResolutionResult` to `models.py` (see data-model.md) and update
  the type annotation on `services.resolve_template`.

The finding must appear as a comment at the top of the FIX-10 implementation task.
No FIX-10 code is written until this audit is complete.

---

## New tools

### `load_eligible_keys`

**File**: `tone_suggestion_subagent.py`
**Registered on**: `ToneSuggestionSubagent`'s `tools=[]` (the orchestrator, not any
specialist subagent)

**Signature**:
```python
async def load_eligible_keys(
    force_reload: bool,
    tool_context: ToolContext,
) -> dict[str, Any]
```

**Behaviour**:
- Reads session context from `tool_context.state` via `validate_session_context`.
- If `force_reload=False` and `tool_context.state["eligible_keys"]` is already
  populated, returns the cached value immediately with no DB or Redis calls.
- If `force_reload=True`, clears `tool_context.state["eligible_keys"]` before
  rebuilding.
- Calls `build_resolution_graph` and `resolve_template`, then
  `_build_reachable_eligible` to apply reachability and content eligibility filters.
- On success: writes `eligible_keys: dict[str, str]` to `tool_context.state` and
  returns `{"eligible_keys": dict, "total": int}`.
- On any DB or Redis exception: catches the exception, does NOT re-raise, returns
  `{"error": "<exception type>", "message": "<human-readable explanation>"}`.

**Does not raise.** All failure modes return a structured dict.

---

### `finalize_rewrites`

**File**: `tone_suggestion_subagent.py`
**Registered on**: `SuggestAgent`'s `tools=[]`

**Signature**:
```python
async def finalize_rewrites(
    rewrites: list[dict],
    tool_context: ToolContext,
) -> dict[str, Any]
```

**Behaviour**:
- `rewrites` is a list of `{"key": str, "new_value": str}` dicts produced by the
  LLM.
- Validates each key against `tool_context.state["eligible_keys"]`; discards any key
  not present (hallucinated keys).
- Filters out items where `new_value` equals the current value in `eligible_keys`.
- Catches `json.JSONDecodeError` and `ValueError` from `_parse_llm_rewrites`; on
  parse failure returns `{"error": "parse_error", "message": "SuggestAgent returned
  invalid JSON."}` without raising.
- Reads `suggestion_id` from `tool_context.state["suggestion_id"]` (set earlier by
  `_suggest_tone_rewrites_tool`).
- On success: writes to `tool_context.state`:
  - `suggestions`: `list[dict]` — each dict has `key` (str), `old_value` (str),
    `new_value` (str), `suggestion_id` (str).
  - `discarded_keys` (optional): `list[dict]` describing discarded items.
- Returns `{"accepted": int, "discarded": int, "suggestions": list}` on success.
- MUST NOT write `tone_bearing_keys` or `structural_keys` to state.

---

## Modified tools

### `_classify_keys_tool`

**Change**: The tool currently writes `tone_bearing_keys` and `structural_keys` to
`tool_context.state`. After this refactor it MUST return both values in its return
dict instead, so the orchestrator can read them from the return value and pass them
explicitly. It MUST NOT write `tone_bearing_keys` or `structural_keys` to state.

**Updated return shape**:
```python
{
    "tone_bearing": dict[str, str],
    "structural": dict[str, str],
    "stage1_structural_count": int,
    "stage2_structural_count": int,
    "tone_bearing_count": int,
}
```

---

### `_suggest_tone_rewrites_tool`

**Change**: Accepts `tone_bearing_keys: dict[str, str]` as an explicit parameter
instead of reading it from `tool_context.state`. Calls `capture_snapshot` before
building the rewrite prompt. Returns `snapshot_saved` and `snapshot_overwritten`.

**Updated signature**:
```python
async def _suggest_tone_rewrites_tool(
    target_intent: str,
    tone_bearing_keys: dict[str, str],
    tool_context: ToolContext,
) -> dict[str, Any]
```

**Updated return shape**:
```python
{
    "rewrite_prompt": str,
    "eligible_keys": list[str],
    "target_emotions": dict[str, float],
    "baseline_emotions": dict[str, float],
    "suggestion_id": str,
    "snapshot_saved": bool,
    "snapshot_overwritten": bool,
}
```

- Raises `MissingClassificationError` if `tone_bearing_keys` is absent or `None`.
  An empty dict `{}` is valid (no eligible keys, returns early with a message).
- Writes `suggestion_id` to `tool_context.state` before returning (needed by
  `finalize_rewrites`).
- MUST NOT write `suggestions` to state — `finalize_rewrites` does that.

---

### `_apply_tone_suggestions_tool`

**Changes**:
- `await get_pool()` and `await get_redis()` (FIX-04).
- Validates `suggestion_id` cross-match before writing: every suggestion in the
  confirmed list must carry `suggestion_id == tool_context.state["suggestion_id"]`.
  On mismatch, raises `SuggestionIdMismatchError`.
- MUST NOT call `capture_snapshot` (FIX-03).
- MUST NOT return `snapshot_overwritten` in its return dict.

**Return shape** (unchanged except removal of `snapshot_overwritten`):
```python
{
    "applied": int,
    "message": str,
}
```

---

### `_undo_tone_suggestions_tool`

**Change**: Returns `snapshot_cleared: bool` in all cases. Deletes the snapshot Redis
hash when `keys=None` (full undo); leaves it when `keys` is a non-empty list.

**Updated return shape**:
```python
{
    "restored": int,
    "message": str,
    "snapshot_cleared": bool,
}
```

---

## Deletions

The following must be removed entirely. Each is a checklist item for the deletion task:

- [ ] `_populate_eligible_keys` function (was `before_agent_callback`)
- [ ] `_process_suggest_agent_response` function (was `after_agent_callback`)
- [ ] `set_classifier_llm_fn()` function
- [ ] `_classifier_llm_fn` module-level variable and its type alias `ClassifierLlmFn`
- [ ] `before_agent_callback=_populate_eligible_keys` kwarg on `ToneSuggestionSubagent`
- [ ] `after_agent_callback=_process_suggest_agent_response` kwarg on `SuggestAgent`
- [ ] All reads and writes of `pending_suggest_rewrite` from/to `session.state`
- [ ] `_extract_agent_response_text` function (used only by the removed callback)
- [ ] `_finalize_suggest_rewrites` function (logic moves into `finalize_rewrites` tool)

After deletion, verify:
```
grep -n "callback\|classifier_llm_fn\|pending_suggest_rewrite\|_extract_agent_response_text\|_finalize_suggest_rewrites" \
  template_assistant/subagents/tone_suggestion_subagent.py
# must return zero results
```

---

## Instruction changes

### ToneSuggestionSubagent (orchestrator) instruction

The following changes are required. Present the full updated instruction in the
implementation — do not patch in-place.

**Add as step 0** (before any delegation):
```
Step 0: Call load_eligible_keys(force_reload=True). If the result contains an "error"
key, relay the "message" value to the user as a plain sentence and stop. Do not
proceed to KeyClassifierAgent.
```

**Update step 2** (passing keys to SuggestAgent):
```
Step 2: Read tone_bearing_keys from KeyClassifierAgent's tool return value.
Pass it explicitly to SuggestAgent via _suggest_tone_rewrites_tool's
tone_bearing_keys parameter. Do not read tone_bearing_keys from session.state.
```

**Add snapshot overwrite warning rule**:
```
Step 4 (new): If _suggest_tone_rewrites_tool returns snapshot_overwritten: true,
prepend the following warning to the diff presentation before asking the user to
confirm: "Note: applying these suggestions will replace the undo snapshot from
your previous suggestion batch. You will not be able to undo that earlier batch
individually after confirming."
```

**Add explicit step for finalize_rewrites**:
```
Step 3 (new): After SuggestAgent completes, session.state["suggestions"] and
session.state["suggestion_id"] will have been written by finalize_rewrites.
Read suggestions from state before presenting the diff to the user.
```

### SuggestAgent instruction

**Add** after the step that calls `_suggest_tone_rewrites_tool`:
```
After generating JSON rewrites, call finalize_rewrites(rewrites=[...]) with the
full list as the parameter. Do not emit the JSON as response text. Do not proceed
until finalize_rewrites has been called.
```

**Remove** any instruction referencing `after_agent_callback`, `pending_suggest_rewrite`,
or emitting JSON as raw response text.

---

## Contracts (`contracts/internal-delegation.md`)

The contracts file must document the following rules. These are the authoritative
source for what each agent may and may not do.

### Delegation rules

| From | To | Condition |
|---|---|---|
| `ToneSuggestionSubagent` | `KeyClassifierAgent` | Always, as step 1 of suggest flow |
| `ToneSuggestionSubagent` | `SuggestAgent` | Only after `KeyClassifierAgent` completes |
| `ToneSuggestionSubagent` | `ApplyAgent` | Only after user explicitly confirms |
| `ToneSuggestionSubagent` | `UndoAgent` | Any time user requests undo |

### Shared module access

| Agent | May read from | May write to |
|---|---|---|
| `ToneSuggestionSubagent` | `shared/resolution/`, `shared/db.py`, `shared/redis_client.py` | Redis only |
| `KeyClassifierAgent` | `tone_profiles.py`, `ml/goemotions.py` | Nothing |
| `SuggestAgent` | `tone_profiles.py`, `ml/goemotions.py` | `tool_context.state` via `finalize_rewrites` only |
| `ApplyAgent` | `shared/resolution/`, `shared/db.py`, `shared/redis_client.py` | Redis only |
| `UndoAgent` | `shared/redis_client.py` | Redis only |

### State ownership

| Key | Owner | Scope |
|---|---|---|
| `eligible_keys` | `ToneSuggestionSubagent` via `load_eligible_keys` | Session (cached, invalidated by `force_reload=True`) |
| `suggestions` | `SuggestAgent` via `finalize_rewrites` | Session (suggest turn → apply turn) |
| `suggestion_id` | `_suggest_tone_rewrites_tool` | Session (suggest turn → apply turn) |
| `tone_bearing_keys` | Not stored in state | Turn-scoped only, passed as parameter |
| `structural_keys` | Not stored in state | Turn-scoped only, not passed forward |

No agent may write to PostgreSQL. No agent may read session context fields
(`template_name`, `lang_local`, `param_cust_brand`, `session_id`) from anywhere other
than `validate_session_context(tool_context.state)`.

---

## Testing strategy

**Framework**: pytest + pytest-asyncio, real PostgreSQL and Redis, no mocks.
Session context injected via `tool_context.state` in unit tests and via
`InMemorySessionService` in e2e tests.

### `test_tone_suggestion_subagent.py` — full rewrite

| Test name | What it verifies |
|---|---|
| `test_load_eligible_keys_success` | Returns `eligible_keys` dict and writes to state on healthy connections |
| `test_load_eligible_keys_cache_hit_skips_db` | With `force_reload=False` and populated state, makes no DB calls |
| `test_load_eligible_keys_force_reload_bypasses_cache` | With `force_reload=True`, clears and rebuilds even when state is populated |
| `test_load_eligible_keys_db_failure_returns_error_dict` | On DB failure, returns dict with `error` (str) and `message` (str); no exception raised |
| `test_finalize_rewrites_accepts_valid_keys` | Accepted keys written to state with correct `old_value`, `new_value`, `suggestion_id` |
| `test_finalize_rewrites_discards_hallucinated_keys` | Keys not in `eligible_keys` are excluded; included in `discarded_keys` |
| `test_finalize_rewrites_filters_unchanged_values` | Rewrites where `new_value == current_value` are not written to state |
| `test_finalize_rewrites_malformed_json` | Returns `{"error": "parse_error", "message": ...}` without raising |
| `test_suggest_tone_rewrite_snapshot_saved_before_prompt` | Redis hash `tone-snapshot:...` exists after `_suggest_tone_rewrites_tool` returns, before `_apply_tone_suggestions_tool` is called |
| `test_suggest_tone_rewrite_snapshot_overwritten_flag` | Second call in same session returns `snapshot_overwritten: true` |
| `test_suggest_tone_rewrite_raises_on_missing_tone_bearing_keys` | `MissingClassificationError` raised when `tone_bearing_keys` parameter is absent |
| `test_suggest_tone_rewrite_empty_tone_bearing_keys_returns_message` | Empty `tone_bearing_keys` dict returns `{"message": "No eligible keys found..."}` without raising |
| `test_classify_keys_tool_returns_classification_not_writes_state` | `_classify_keys_tool` return value contains `tone_bearing` and `structural`; state does NOT contain `tone_bearing_keys` after the call |
| `test_apply_validates_suggestion_id_cross_match` | `SuggestionIdMismatchError` raised when confirmed suggestion carries wrong `suggestion_id` |
| `test_apply_does_not_call_capture_snapshot` | No snapshot Redis hash written during `_apply_tone_suggestions_tool` call |
| `test_apply_awaits_pool_and_redis` | No coroutine-object errors on cold-start apply call |
| `test_undo_full_clears_snapshot_hash` | After `_undo_tone_suggestions_tool(keys=None)`, Redis hash `tone-snapshot:...` does not exist; return includes `snapshot_cleared: true` |
| `test_undo_partial_leaves_snapshot_hash` | After `_undo_tone_suggestions_tool(keys=["EN.PARAGRAPH_1"])`, Redis hash still exists; return includes `snapshot_cleared: false` |
| `test_undo_no_snapshot_returns_gracefully` | With no snapshot in Redis, returns `{"restored": 0, "snapshot_cleared": false, "message": ...}` without raising |
| `test_post_apply_state_keys_are_clean` | After full suggest→apply cycle, `session.state` does NOT contain `tone_bearing_keys`, `structural_keys`, or `pending_suggest_rewrite` |

### `test_e2e_agent.py` — new cases added (existing cases unchanged)

| Test name | What it verifies |
|---|---|
| `test_second_suggest_before_undo_shows_warning` | Second suggest call produces response containing "undo snapshot from your previous suggestion batch" |
| `test_manual_edit_then_suggest_excludes_edited_key` | After `set_working_copy_value` sets a key to a URL, subsequent suggest flow does not include that key in suggestions |
| `test_db_failure_during_load_eligible_keys_surfaces_message` | With DB unreachable, agent responds with a plain error message rather than raising |

---

## Project structure

```text
specs/009-refactor-tone-suggestion-subagent/
├── spec.md
├── plan.md                          # This file
├── research.md                      # Phase 0 audit findings (FIX-10 branch decision)
├── data-model.md
├── quickstart.md
├── contracts/
│   └── internal-delegation.md      # Delegation rules, state ownership, module access
└── tasks.md                        # Generated by /speckit.tasks
```

```text
template_assistant/
├── context.py                       # + MissingClassificationError, SuggestionIdMismatchError
├── models.py                        # + ServiceResolutionResult (Branch B only)
├── subagents/
│   └── tone_suggestion_subagent.py  # Full rewrite
└── tests/
    ├── test_tone_suggestion_subagent.py  # Full rewrite (20 tests)
    └── test_e2e_agent.py                 # 3 new cases added
```

---

## Complexity tracking

No constitution violations. The net change reduces complexity: two callback functions
and one module-level mutable are removed, and implicit state-bus usage drops from five
turn-scoped keys to zero. The explicit parameter passing introduced by FIX-06 adds
lines but removes execution paths, making the flow testable in isolation.