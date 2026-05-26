---
description: "Task list for Refactor Tone Suggestion Subagent"
---

# Tasks: Refactor Tone Suggestion Subagent

**Input**: Design documents from `/specs/009-refactor-tone-suggestion-subagent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/internal-delegation.md

**Organization**: Tasks are grouped by user story. All unit tests can be run
independently once their phase's tools are implemented. E2e tests (marked [e2e])
require Phase 6 (instruction updates) to pass — write them early to establish the
failing baseline, but do not expect them to go green until Phase 6 is complete.

---

## Phase 1: Foundational (blocks all implementation)

**Purpose**: Audit, error classes, and correctness fixes that every later phase
depends on. No user story implementation begins until this phase is complete.

- [ ] T001 Perform FIX-10 audit on `template_assistant/services.py` to determine
  `resolve_template` return type. Record finding in `research.md` as either
  "Branch A — wraps shared ResolutionResult" or "Branch B — own type, add
  ServiceResolutionResult". This finding is a prerequisite for T002 and T003.

- [ ] T002 Apply FIX-10 field name corrections in
  `template_assistant/subagents/tone_suggestion_subagent.py` based on T001 finding:
  - Branch A: update all access sites from `resolved_body` → `resolved_text` and
    `resolved_keys` → `unresolvable_keys`.
  - Branch B: add `ServiceResolutionResult` dataclass to `template_assistant/models.py`
    and update the type annotation on `services.resolve_template`.
  Record the branch decision as a comment at the top of this task's commit.
  **Depends on**: T001.

- [ ] T003 Add `MissingClassificationError` and `SuggestionIdMismatchError` to
  `template_assistant/context.py` with `to_payload() -> dict[str, Any]` methods
  as specified in data-model.md. **Depends on**: T001 (must know final file list).

- [ ] T004 Remove module-level mutable `_classifier_llm_fn` variable, its type alias
  `ClassifierLlmFn`, and the `set_classifier_llm_fn()` function from
  `template_assistant/subagents/tone_suggestion_subagent.py`.

**Checkpoint**: All foundational prerequisites met. User story phases may now begin.

---

## Phase 2: User Story 1 — Suggestion generation via tool (Priority: P1) 🎯 MVP

**Goal**: Replace `after_agent_callback` event scraping with an explicit
`finalize_rewrites` tool call.

**Unit test scope**: T005–T008 can pass as soon as T009–T012 are complete.
E2e coverage comes in Phase 6 once instructions are updated.

### Tests (write first — must fail before implementation)

- [ ] T005 [P] Write `test_finalize_rewrites_accepts_valid_keys`
- [ ] T006 [P] Write `test_finalize_rewrites_discards_hallucinated_keys`
- [ ] T007 [P] Write `test_finalize_rewrites_filters_unchanged_values`
- [ ] T008 [P] Write `test_finalize_rewrites_malformed_json`

### Implementation

- [ ] T009 Implement `finalize_rewrites(rewrites: list[dict], tool_context: ToolContext)`
  in `tone_suggestion_subagent.py` per the tool specification in plan.md.

- [ ] T010 Register `finalize_rewrites` in `SuggestAgent`'s `tools=[]` list.

- [ ] T011 Remove the following from `tone_suggestion_subagent.py`:
  - `_process_suggest_agent_response` function
  - `_extract_agent_response_text` function
  - `_finalize_suggest_rewrites` function
  - `after_agent_callback=_process_suggest_agent_response` kwarg on `SuggestAgent`
  - All reads and writes of `pending_suggest_rewrite` from/to `session.state`
    (check `_suggest_tone_rewrites_tool` and any other call site)

**Checkpoint**: `test_finalize_rewrites_*` unit tests pass. `SuggestAgent` no longer
has `after_agent_callback`. E2e tests are written but not yet green (require Phase 6).

---

## Phase 3: User Story 2 — Resilient eligible keys loading (Priority: P1)

**Goal**: Replace `before_agent_callback` DB/Redis I/O with an explicit
`load_eligible_keys` tool.

### Tests (write first — must fail before implementation)

- [ ] T012 [P] Write `test_load_eligible_keys_success`
- [ ] T013 [P] Write `test_load_eligible_keys_cache_hit_skips_db`
- [ ] T014 [P] Write `test_load_eligible_keys_force_reload_bypasses_cache`
- [ ] T015 [P] Write `test_load_eligible_keys_db_failure_returns_error_dict`
  — assert return dict contains `error` (str) and `message` (str); assert no
  exception is raised.
- [ ] T016 [P] Write `test_manual_edit_then_suggest_excludes_edited_key` [e2e]
  — after `set_working_copy_value` sets a key to a URL, subsequent suggest flow
  with `force_reload=True` must not include that key in suggestions.
- [ ] T017 [P] Write `test_db_failure_during_load_eligible_keys_surfaces_message` [e2e]

### Implementation

- [ ] T018 Implement `load_eligible_keys(force_reload: bool, tool_context: ToolContext)`
  in `tone_suggestion_subagent.py` per the tool specification in plan.md.

- [ ] T019 Register `load_eligible_keys` in `ToneSuggestionSubagent`'s `tools=[]`
  list (the orchestrator, not any specialist subagent).

- [ ] T020 Remove `_populate_eligible_keys` function and
  `before_agent_callback=_populate_eligible_keys` kwarg from
  `ToneSuggestionSubagent` in `tone_suggestion_subagent.py`.

**Checkpoint**: `test_load_eligible_keys_*` unit tests pass. `ToneSuggestionSubagent`
no longer has `before_agent_callback`. E2e tests T016–T017 written but not yet green.

---

## Phase 4: User Story 3 — Correct snapshot lifecycle (Priority: P2)

**Goal**: Capture snapshots at suggestion time, return `snapshot_cleared` from undo,
and remove snapshot capture from apply.

### Tests (write first — must fail before implementation)

- [ ] T021 [P] Write `test_suggest_tone_rewrite_snapshot_saved_before_prompt`
  — assert Redis hash `tone-snapshot:...` exists after `_suggest_tone_rewrites_tool`
  returns and before `_apply_tone_suggestions_tool` is called.
- [ ] T022 [P] Write `test_suggest_tone_rewrite_snapshot_overwritten_flag`
- [ ] T023 [P] Write `test_apply_does_not_call_capture_snapshot`
- [ ] T024 [P] Write `test_undo_full_clears_snapshot_hash`
- [ ] T025 [P] Write `test_undo_partial_leaves_snapshot_hash`
- [ ] T026 [P] Write `test_undo_no_snapshot_returns_gracefully`
- [ ] T027 [P] Write `test_second_suggest_before_undo_shows_warning` [e2e]

### Implementation

- [ ] T028 Modify `_suggest_tone_rewrites_tool` to:
  - Call `capture_snapshot` before building the rewrite prompt.
  - Return `snapshot_saved: bool` and `snapshot_overwritten: bool`.
  - Write `suggestion_id` to `tool_context.state` before returning.
  Note: this is an intermediate form — T029 in Phase 5 rewrites this function to its
  final form. Do not add the `tone_bearing_keys` parameter yet; that is Phase 5's job.

- [ ] T029 Modify `_apply_tone_suggestions_tool` to remove the `capture_snapshot`
  call and remove `snapshot_overwritten` from its return dict.

- [ ] T030 Modify `_undo_tone_suggestions_tool` to return `snapshot_cleared: bool`
  in all cases, and delete the Redis snapshot hash when `keys=None` (full undo).

**Checkpoint**: Snapshot lifecycle unit tests T021–T026 pass. E2e test T027 written
but not yet green (requires Phase 6 instruction update).

---

## Phase 5: User Story 4 — Robust state and dependency management (Priority: P2)

**Goal**: Enforce explicit parameter passing for `tone_bearing_keys`, await pool and
Redis getters, validate `suggestion_id` cross-match, and clean up session state.

### Tests (write first — must fail before implementation)

- [ ] T031 [P] Write `test_suggest_tone_rewrite_raises_on_missing_tone_bearing_keys`
- [ ] T032 [P] Write `test_suggest_tone_rewrite_empty_tone_bearing_keys_returns_message`
- [ ] T033 [P] Write `test_classify_keys_tool_returns_classification_not_writes_state`
  — assert return value contains `tone_bearing` and `structural` keys; assert
  `session.state` does NOT contain `tone_bearing_keys` after the call.
- [ ] T034 [P] Write `test_apply_validates_suggestion_id_cross_match`
- [ ] T035 [P] Write `test_apply_awaits_pool_and_redis`
- [ ] T036 [P] Write `test_post_apply_state_keys_are_clean`
  — assert `session.state` does NOT contain `tone_bearing_keys`, `structural_keys`,
  or `pending_suggest_rewrite` after a full suggest→apply cycle.

### Implementation

- [ ] T037 Modify `_classify_keys_tool` to return `tone_bearing` and `structural`
  in its return dict instead of writing them to `tool_context.state`.
  It MUST NOT write `tone_bearing_keys` or `structural_keys` to state.

- [ ] T038 **Rewrite `_suggest_tone_rewrites_tool` to its final form from scratch**,
  incorporating T028's snapshot changes and adding `tone_bearing_keys: dict[str, str]`
  as an explicit parameter. Final signature per plan.md:
  ```python
  async def _suggest_tone_rewrites_tool(
      target_intent: str,
      tone_bearing_keys: dict[str, str],
      tool_context: ToolContext,
  ) -> dict[str, Any]
  ```
  Raise `MissingClassificationError` if `tone_bearing_keys` is absent or `None`.
  Return `{"message": "No eligible keys found..."}` if it is an empty dict `{}`.
  Do not patch T028's output — rewrite the function completely.

- [ ] T039 **Rewrite `_apply_tone_suggestions_tool` to its final form from scratch**,
  incorporating T029's removal of `capture_snapshot` and adding:
  - `await get_pool()` and `await get_redis()` (FIX-04).
  - `suggestion_id` cross-match validation before writing to Redis; raise
    `SuggestionIdMismatchError` on mismatch.
  Do not patch T029's output — rewrite the function completely.

**Checkpoint**: All unit tests in Phases 1–5 pass. E2e tests written but not yet
green. The file is in a fully correct state for tool behavior; only the agent
instructions remain to be updated.

---

## Phase 6: Instruction updates

**Purpose**: Write the complete final instruction for each agent. Both tasks must
come after all tool implementations are done. Do not patch existing instruction
strings — write each in full.

**Depends on**: All of Phases 1–5.

- [ ] T040 [P] Write the complete final `ToneSuggestionSubagent` (orchestrator)
  instruction in `tone_suggestion_subagent.py`. The instruction must include all of
  the following in order:
  - Step 0: call `load_eligible_keys(force_reload=True)`; on error, relay `message`
    and stop.
  - Step 1: delegate to `KeyClassifierAgent`.
  - Step 2: read `tone_bearing_keys` from `KeyClassifierAgent`'s tool return value;
    pass it explicitly to `SuggestAgent` via `_suggest_tone_rewrites_tool`'s
    `tone_bearing_keys` parameter. Do not read it from `session.state`.
  - Step 3: after `SuggestAgent` completes, read `suggestions` from `session.state`
    (written by `finalize_rewrites`) for diff presentation.
  - Step 4: if `_suggest_tone_rewrites_tool` returns `snapshot_overwritten: true`,
    prepend the defined warning before asking for confirmation.
  - Apply, undo, and existing rules: unchanged in substance.
  Replace the existing instruction string entirely.

- [ ] T041 [P] Write the complete final `SuggestAgent` instruction in
  `tone_suggestion_subagent.py`. The instruction must:
  - Add the explicit step: after generating JSON rewrites, call
    `finalize_rewrites(rewrites=[...])`. Do not emit JSON as response text. Do not
    proceed until `finalize_rewrites` has been called.
  - Remove any reference to `after_agent_callback`, `pending_suggest_rewrite`, or
    emitting JSON as raw response text.
  Replace the existing instruction string entirely.

**Checkpoint**: All unit tests and all e2e tests pass. Run the full smoke test from
spec.md to confirm end-to-end behavior.

---

## Phase 7: Verification

**Purpose**: Final correctness checks. All must pass before the branch is merged.

- [ ] T042 Run full test suite and confirm zero regressions:
  ```
  pytest template_assistant/tests/ -x
  ```

- [ ] T043 Run the combined deletion verification grep and confirm zero results:
  ```
  grep -n "callback\|classifier_llm_fn\|pending_suggest_rewrite\|_extract_agent_response_text\|_finalize_suggest_rewrites" \
    template_assistant/subagents/tone_suggestion_subagent.py
  ```

---

## Dependencies and execution order

```
Phase 1 (Foundational)
    └── Phase 2 (US1) ──┐
    └── Phase 3 (US2) ──┤ all independent, can run in parallel
    └── Phase 4 (US3) ──┤ after Phase 1
    └── Phase 5 (US4) ──┘
            │
        Phase 6 (Instructions) ← must follow all of Phases 1–5
            │
        Phase 7 (Verification)
```

Within each user story phase, the order is: write tests (all [P], can be parallel)
→ implement tools (sequential within phase).

User story phases 2–5 are independent of each other and can be worked by different
team members in parallel. Phase 6 requires all four to be complete.

### E2e test readiness

| Test | Written in phase | Passes after phase |
|---|---|---|
| `test_db_failure_during_load_eligible_keys_surfaces_message` | Phase 3 | Phase 6 |
| `test_manual_edit_then_suggest_excludes_edited_key` | Phase 3 | Phase 6 |
| `test_second_suggest_before_undo_shows_warning` | Phase 4 | Phase 6 |