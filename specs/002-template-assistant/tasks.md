---
description: "Task list template for feature implementation"
---

# Tasks: Template Assistant

**Input**: Design documents from `/specs/002-template-assistant/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are requested per the plan (pytest + pytest-asyncio, unit tests per subagent, one E2E test).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- **⚠️ agent.py**: Tasks that modify `agent.py` must run sequentially — never in parallel
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure. All tasks in this phase can run in parallel.

- [X] T001 [P] Create `template_assistant/` package structure with `__init__.py`
- [X] T002 [P] Create `template_assistant/tests/` package structure with `__init__.py`
- [X] T003 [P] Create `template_assistant/subagents/` package structure with `__init__.py`
- [X] T004 [P] Create `template_assistant/ml/` package structure with `__init__.py`
- [X] T005 [P] Create `template_assistant/utils/` package structure with `__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 Implement `SessionContext` dataclass, `validate_session_context()` function,
  and `SessionContextMissingError` exception class in `template_assistant/context.py`.
  All four fields are required: `template_name`, `lang_local`, `param_cust_brand`, `session_id`.
  Write unit tests in `template_assistant/tests/test_context.py` covering:
  - Valid context passes validation
  - Each of the four fields missing individually raises `SessionContextMissingError`
  - `lang_local` and `param_cust_brand` are coerced to uppercase on construction

- [X] T007 Implement proactive context announcement in root `TemplateAssistantAgent`
  skeleton in `template_assistant/agent.py`.
  On session start with valid context the agent emits:
  `"Hi! I'm ready to help you with the {template_name} template ({lang_local}, {param_cust_brand})."`
  On missing context the agent refuses with a clear message.
  Write unit test in `template_assistant/tests/test_agent.py` covering both branches.
  ⚠️ This is the first and only task that creates `agent.py` — subsequent tasks only add to `sub_agents=[]`.

- [X] T008 [P] Implement GoEmotions lazy-load singleton in `template_assistant/ml/goemotions.py`.
  Expose a single `get_classifier()` function that initialises the pipeline once at
  module level and returns the same instance on every subsequent call:
```python
  from transformers import pipeline
  _classifier = None
  def get_classifier():
      global _classifier
      if _classifier is None:
          _classifier = pipeline(
              "text-classification",
              model="SamLowe/roberta-base-go_emotions",
              top_k=None,
          )
      return _classifier
```
  Write unit test in `template_assistant/tests/test_ml_goemotions.py` verifying:
  - Two calls to `get_classifier()` return the same object (singleton guarantee)
  - Returned pipeline accepts a plain text string and returns 28 labelled scores

- [X] T009 [P] Implement static intent → emotion weight mapping in
  `template_assistant/tone_profiles.py`.
  The mapping is a `dict[str, dict[str, float]]` keyed by canonical intent phrase.
  Minimum required entries:
```python
  TONE_PROFILES = {
      "more reassuring":  {"relief": 0.8, "caring": 0.7, "fear": 0.1, "nervousness": 0.1},
      "more urgent":      {"desire": 0.8, "nervousness": 0.6},
      "warmer":           {"joy": 0.8, "love": 0.7, "gratitude": 0.7},
      "more professional":{"approval": 0.7, "amusement": 0.1, "excitement": 0.1},
      "more encouraging": {"admiration": 0.8, "optimism": 0.8, "joy": 0.6},
  }
```
  Write unit tests in `template_assistant/tests/test_tone_profiles.py` verifying:
  - Every key in `TONE_PROFILES` maps to a non-empty dict
  - Every emotion label in every value dict is a valid GoEmotions label
  - A lookup for an unknown intent returns `None` (not a `KeyError`)

- [X] T010 [P] Implement `extract_plain_text(html: str) -> str` utility in
  `template_assistant/utils/text.py` using `trafilatura`.
  Rules:
  - Returns clean plain text with boilerplate (headers, footers, nav) stripped
  - Returns empty string (not raises) for image-only or empty HTML input
  Write unit tests in `template_assistant/tests/test_utils_text.py` covering:
  - Normal HTML with body paragraphs → returns non-empty plain text
  - HTML containing only `<img>` tags → returns empty string without raising
  - Empty string input → returns empty string without raising
  - HTML with fewer than 50 characters of extractable text → returns the short string
    (caller is responsible for warning the user, not this function)

**Checkpoint**: Foundation complete — all user story phases can now begin.

---

## Phase 3: User Story 1 — Query Template Content (Priority: P1) 🎯 MVP

**Goal**: As a template author, I want to ask what a specific section of the template says
so that I can understand the current content without opening the editor.

**Independent Test**: Ask the agent about a specific paragraph and verify the response
matches the resolved content from the shared resolution library.

### Tests for User Story 1 ⚠️ Write and confirm FAILING before T013

- [X] T011 [P] [US1] Write unit tests for `get_template_structure` in
  `template_assistant/tests/test_resolution_subagent.py`:
  - Returns list of placeholder keys found in HTML and text bodies
  - Keys are grouped by body type (`html`, `text`)
  - Raises `SessionContextMissingError` when context fields are absent

- [X] T012 [P] [US1] Write unit tests for `resolve_key` in
  `template_assistant/tests/test_resolution_subagent.py`:
  - Returns resolved value for a known key
  - Returns working copy value when an override exists in Redis
  - Returns `UnresolvableKey` entry when key is missing from graph and parameters
  - Raises `SessionContextMissingError` when context fields are absent

### Implementation for User Story 1

- [X] T013 [US1] Implement `get_template_structure` and `resolve_key` tools in
  `template_assistant/subagents/resolution_subagent.py`.
  Both tools extract `SessionContext` from `session_state` as their first action
  and raise `SessionContextMissingError` if invalid.
  Both delegate entirely to `shared.resolution` — no resolution logic here.

- [X] T014 [US1] ⚠️ agent.py — Add `ResolutionSubagent` to `sub_agents=[]` in
  `template_assistant/agent.py`. Do not modify any other part of the file.

**Checkpoint**: User Story 1 fully functional and independently testable.

---

## Phase 4: User Story 2 — Full HTML Preview (Priority: P1)

**Goal**: As a template author, I want to see a full resolved HTML preview of the template
so that I can review it as it would appear to recipients.

**Independent Test**: Ask for a preview and verify the returned HTML is the fully resolved
template body.

### Tests for User Story 2 ⚠️ Write and confirm FAILING before T016

- [X] T015 [P] [US2] Write unit tests for `resolve_full_template` in
  `template_assistant/tests/test_resolution_subagent.py`:
  - Returns complete resolved HTML string
  - Unresolvable keys are listed in the result alongside the resolved text
  - Raises `SessionContextMissingError` when context fields are absent

### Implementation for User Story 2

- [X] T016 [US2] Implement `resolve_full_template` tool in
  `template_assistant/subagents/resolution_subagent.py`.
  Returns the full resolved HTML as a code block string.
  Delegates to `shared.resolution.resolver.resolve_template`.
  Does not modify `agent.py` — `ResolutionSubagent` is already registered.

**Checkpoint**: User Stories 1 and 2 both functional independently.

---

## Phase 5: User Story 4 — Evaluate Emotional Tone (Priority: P1)

**Goal**: As a template author, I want to ask the agent to evaluate the emotional tone
of the template so that I can understand how recipients are likely to feel reading it.

**Independent Test**: Ask for a tone evaluation and verify the agent returns all 28
GoEmotions label scores reflecting the current working copy state.

### Tests for User Story 4 ⚠️ Write and confirm FAILING before T019

- [X] T017 [P] [US4] Write unit tests for `evaluate_tone` in
  `template_assistant/tests/test_tone_evaluation_subagent.py`:
  - Returns a `ToneEvaluationResult` with 28 labelled scores
  - Uses working copy values when Redis overrides are present
  - When extractable plain text is fewer than 50 characters, result includes
    a `low_coverage_warning: True` flag
  - When HTML yields empty plain text, scores are still returned (not raises)
  - Raises `SessionContextMissingError` when context fields are absent

- [X] T018 [P] [US4] Write unit tests for `get_stored_tone_scores` in
  `template_assistant/tests/test_tone_evaluation_subagent.py`:
  - Returns stored scores from `template_tone_evaluations` for matching
    `(template_id, lang_local, param_cust_brand)`
  - Returns `None` when no stored scores exist (not raises)

### Implementation for User Story 4

- [X] T019 [US4] Implement `evaluate_tone` and `get_stored_tone_scores` tools in
  `template_assistant/subagents/tone_evaluation_subagent.py`.
  `evaluate_tone` flow:
  1. Validate `SessionContext`
  2. Call `shared.resolution.resolver.resolve_template` to get resolved HTML
  3. Call `extract_plain_text` from `template_assistant/utils/text.py`
  4. If plain text length < 50 characters, set `low_coverage_warning=True`
  5. Call `get_classifier()` from `template_assistant/ml/goemotions.py`
  6. Return `ToneEvaluationResult`
  `get_stored_tone_scores` queries `template_tone_evaluations` via `shared.db`.
  Note: `compare_tone` is NOT implemented here — it has no covering user story.

- [X] T020 [US4] ⚠️ agent.py — Add `ToneEvaluationSubagent` to `sub_agents=[]` in
  `template_assistant/agent.py`. Do not modify any other part of the file.

**Checkpoint**: Tone evaluation functional. Must not run T020 in parallel with T014.

---

## Phase 6: User Story 5 — Suggest and Apply Tone Rewrites (Priority: P1)

**Goal**: As a template author, I want to tell the agent to make the template feel more
reassuring, have it suggest rewrites for specific placeholders, and apply them immediately.

**Independent Test**: Request a tone change, verify suggestions are shown with current vs
suggested values, confirm changes are reflected in Redis working copy after the call.

### Tests for User Story 5 ⚠️ Write and confirm FAILING before T025–T028

- [X] T021 [P] [US5] Write unit tests for key eligibility heuristics in
  `template_assistant/tests/test_tone_suggestion_subagent.py`:
  - Keys ending in `_URL`, `_COLOR`, `_ID` are not eligible
  - Values starting with `http` are not eligible
  - Values shorter than 20 characters are not eligible
  - Keys with long natural language values are eligible

- [X] T022 [P] [US5] Write unit tests for working copy snapshot in
  `template_assistant/tests/test_tone_suggestion_subagent.py`:
  - Snapshot captures pre-suggestion working copy value when key is already in Redis
  - Snapshot captures graph value when key is not yet in Redis (value is `None`)
  - A second snapshot call overwrites the previous snapshot entirely
  - Snapshot is written to `working-copy-snapshot:{template_name}:{session_id}`

- [X] T023 [P] [US5] Write unit tests for `suggest_tone_rewrites` in
  `template_assistant/tests/test_tone_suggestion_subagent.py`:
  - Returns list of `ToneSuggestion` objects with `key`, `current_value`,
    `suggested_value`, `predicted_delta`
  - Only eligible keys appear in suggestions
  - When no eligible keys exist, returns empty list (not raises)
  - Natural language intent resolves via `TONE_PROFILES` anchors

- [X] T024 [P] [US5] Write unit tests for `apply_tone_suggestions` in
  `template_assistant/tests/test_tone_suggestion_subagent.py`:
  - Snapshot is written to Redis BEFORE any working copy values are written
  - Each suggested value is written to `working-copy:{template_name}:{session_id}`
  - After apply, working copy contains all suggested values

- [X] T025 [P] [US5] Write unit tests for `set_working_copy_value` in
  `template_assistant/tests/test_working_copy_subagent.py`:
  - Writes a single canonical key override to the Redis hash
  - Raises `SessionContextMissingError` when context fields are absent

### Implementation for User Story 5

- [X] T026 [US5] Implement key eligibility heuristics as a pure function
  `is_eligible_for_rewrite(key: str, value: str) -> bool` in
  `template_assistant/subagents/tone_suggestion_subagent.py`.
  Ineligible when: key ends with `_URL`, `_COLOR`, or `_ID`; value starts
  with `http`; value length < 20 characters.

- [X] T027 [US5] Implement working copy snapshot logic as
  `capture_snapshot(keys, session_context, redis, graph) -> None` in
  `template_assistant/subagents/tone_suggestion_subagent.py`.
  For each key: read current Redis working copy value if present, else read
  graph value. Write all to `working-copy-snapshot:{template_name}:{session_id}`.
  Overwrites any previous snapshot without merging.

- [X] T028 [US5] Implement `suggest_tone_rewrites` tool in
  `template_assistant/subagents/tone_suggestion_subagent.py`.
  Flow:
  1. Validate `SessionContext`
  2. Map natural language intent to target emotion weights via `TONE_PROFILES`;
     fall back to LLM mapping for unknown intents
  3. Call `resolve_full_template` to get current resolved HTML (respects working copy)
  4. Run GoEmotions via `get_classifier()` to get baseline scores
  5. Filter placeholder keys through `is_eligible_for_rewrite`
  6. If no eligible keys, return empty list and inform caller
  7. Call underlying LLM with: target emotion profile, each eligible key's
     current value, and surrounding resolved template context for coherence
  8. LLM returns only rewritten values — not key names, not explanations
  9. Return list of `ToneSuggestion` objects

- [X] T029 [US5] Implement `apply_tone_suggestions` tool in
  `template_assistant/subagents/tone_suggestion_subagent.py`.
  Flow:
  1. Validate `SessionContext`
  2. Call `capture_snapshot` for all affected keys (MUST complete before step 3)
  3. Write each suggested value to Redis working copy via `set_working_copy_value`
  4. Return confirmation with count of applied changes

- [X] T030 [US5] Implement `set_working_copy_value` tool in
  `template_assistant/subagents/working_copy_subagent.py`.
  Writes one canonical key field to `working-copy:{template_name}:{session_id}` hash.

- [X] T031 [US5] ⚠️ agent.py — Add `WorkingCopySubagent` and `ToneSuggestionSubagent`
  to `sub_agents=[]` in `template_assistant/agent.py` in a single edit.
  Do not modify any other part of the file.
  ⚠️ Must not run in parallel with T014 or T020.

**Checkpoint**: Tone suggestion, apply, and working copy write all functional.

---

## Phase 7: User Story 3 — Identify Unresolvable Placeholders (Priority: P2)

**Goal**: As a template author, I want to know which placeholders cannot be resolved
under the current context so I can identify and fix data quality issues.

**Independent Test**: Ask for unresolvable placeholders and verify the agent lists the
correct ones with their reason codes.

### Tests for User Story 3 ⚠️ Write and confirm FAILING before T033

- [X] T032 [P] [US3] Write unit tests for `list_unresolvable_placeholders` in
  `template_assistant/tests/test_resolution_subagent.py`:
  - Returns list of `UnresolvableKey` objects with `key` and `reason`
  - Reason codes are one of `MISSING`, `CYCLE`, `BROKEN_RULE`
  - Returns empty list when all placeholders resolve cleanly
  - Raises `SessionContextMissingError` when context fields are absent

### Implementation for User Story 3

- [X] T033 [US3] Implement `list_unresolvable_placeholders` tool in
  `template_assistant/subagents/resolution_subagent.py`.
  Delegates to `shared.resolution.resolver.resolve_template` and returns
  the `unresolvable_keys` list from `ResolutionResult`.
  Does not modify `agent.py` — `ResolutionSubagent` is already registered.

---

## Phase 8: User Story 6 — Review Working Copy Changes (Priority: P2)

**Goal**: As a template author, I want to ask what changes I have made in this session
so I can review my working copy before committing.

**Independent Test**: Make changes, ask for a summary, verify the agent lists all
modified placeholder keys and their current overridden values.

### Tests for User Story 6 ⚠️ Write and confirm FAILING before T035

- [X] T034 [P] [US6] Write unit tests for `get_working_copy` in
  `template_assistant/tests/test_working_copy_subagent.py`:
  - Returns all fields from `working-copy:{template_name}:{session_id}` Redis hash
  - Returns empty dict when no overrides exist (not raises)
  - Raises `SessionContextMissingError` when context fields are absent

### Implementation for User Story 6

- [X] T035 [US6] Implement `get_working_copy` tool in
  `template_assistant/subagents/working_copy_subagent.py`.
  Reads all fields from `working-copy:{template_name}:{session_id}` hash.
  Returns `dict[str, str]` of canonical key → overridden value.

---

## Phase 9: User Story 7 — Undo Tone Suggestions (Priority: P2)

**Goal**: As a template author, I want to undo applied tone suggestions individually
or all at once so I can experiment safely.

**Independent Test**: Apply tone suggestions, request undo, verify placeholders revert
to their pre-suggestion values (preserving any prior manual edits).

### Tests for User Story 7 ⚠️ Write and confirm FAILING before T037

- [X] T036 [P] [US7] Write unit tests for `undo_tone_suggestions` in
  `template_assistant/tests/test_tone_suggestion_subagent.py`:
  - Restores specified keys from snapshot to working copy
  - When snapshot value is `None` for a key, that key is deleted from working copy
    (restores to graph value, not written as empty string)
  - Restoring all keys clears all suggestion-applied values from working copy
  - When no snapshot exists, agent informs user there is nothing to undo (not raises)
  - Raises `SessionContextMissingError` when context fields are absent

### Implementation for User Story 7

- [X] T037 [US7] Implement `undo_tone_suggestions(keys: list[str] | None)` tool in
  `template_assistant/subagents/tone_suggestion_subagent.py`.
  When `keys` is `None`, restore all keys from snapshot.
  When `keys` is a list, restore only those keys.
  For each key: if snapshot value is `None`, delete the key from working copy hash;
  otherwise write snapshot value back to working copy hash.
  If no snapshot exists in Redis, return informational message — do not raise.

---

## Phase 10: User Story 8 — Reset Working Copy (Priority: P3)

**Goal**: As a template author, I want to reset a specific placeholder or all my changes
back to the original database values so I can start over without ending the session.

**Independent Test**: Make changes, request reset, verify working copy is cleared in Redis.

### Tests for User Story 8 ⚠️ Write and confirm FAILING before T039

- [X] T038 [P] [US8] Write unit tests for `reset_working_copy_key` and
  `reset_full_working_copy` in `template_assistant/tests/test_working_copy_subagent.py`:
  - `reset_working_copy_key` deletes one field from the Redis hash
  - `reset_full_working_copy` deletes the entire Redis hash
  - Both return a confirmation message
  - Both raise `SessionContextMissingError` when context fields are absent
  - Calling reset on a key that does not exist in working copy does not raise

### Implementation for User Story 8

- [X] T039 [US8] Implement `reset_working_copy_key(key: str)` and
  `reset_full_working_copy()` tools in
  `template_assistant/subagents/working_copy_subagent.py`.
  `reset_working_copy_key` calls `HDEL working-copy:{template_name}:{session_id} {key}`.
  `reset_full_working_copy` calls `DEL working-copy:{template_name}:{session_id}`.

---

## Phase 11: End-to-End Validation

**Purpose**: Full happy-path multi-turn conversation test and final integration check.

- [X] T040 Write end-to-end multi-turn conversation test in
  `template_assistant/tests/test_e2e_agent.py`.
  The test injects a valid `session_state` dict and drives the following conversation
  in order, asserting state after each mutating step:
  1. Session starts → agent announces template name, lang_local, param_cust_brand
  2. User asks what a section says → `ResolutionSubagent` resolves and returns value
  3. User asks to evaluate tone → `ToneEvaluationSubagent` returns 28 labelled scores
  4. User asks to make the template warmer → `ToneSuggestionSubagent` suggests rewrites,
     applies them, Redis working copy contains new values
  5. User asks to undo paragraph 1 change only → snapshot restore verified in Redis
  6. User asks what changes remain → `WorkingCopySubagent` returns remaining overrides
  7. User asks for full preview → `ResolutionSubagent` returns resolved HTML string
  8. User asks to reset all changes → working copy Redis hash is deleted
  9. User asks for preview again → original graph values are reflected

- [X] T041 Verify all `agent.py` `sub_agents=[]` registrations are correct and complete:
  `ResolutionSubagent`, `WorkingCopySubagent`, `ToneEvaluationSubagent`,
  `ToneSuggestionSubagent` all present. Run full test suite and confirm all pass.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — all tasks parallel
- **Phase 2 (Foundational)**: Depends on Phase 1 — blocks all user story phases
- **Phases 3–10 (User Stories)**: All depend on Phase 2 completion
- **Phase 11 (E2E)**: Depends on all desired user stories being complete

### agent.py modification order (strictly sequential)
```
T007 (create) → T014 (add ResolutionSubagent) → T020 (add ToneEvaluationSubagent)
→ T031 (add WorkingCopySubagent + ToneSuggestionSubagent)
```

These four tasks must never run in parallel with each other.

### User story parallelism (after Phase 2)

- US1, US2, US3 share `resolution_subagent.py` — sequential within that file
- US4 is fully independent of US1–US3 implementation
- US5 implementation depends on `set_working_copy_value` (T030) existing before T029
- US6, US7, US8 share `working_copy_subagent.py` — sequential within that file
- All test files are independent and fully parallel

### Within each user story

1. Write tests → confirm they FAIL
2. Implement → confirm tests PASS
3. Register in `agent.py` if required (sequential gate)
4. Checkpoint validation before next story

---

## Notes

- `[P]` means different files, no shared state — safe to parallelise
- `⚠️ agent.py` means this task modifies the shared root agent file — never parallel
- `compare_tone` is explicitly out of scope — do not implement without a covering user story
- Snapshot overwrites: a second `apply_tone_suggestions` call replaces the previous
  snapshot entirely — do not merge or append
- Undo with `None` snapshot in Redis returns an informational message, never raises
- GoEmotions model is always loaded via `get_classifier()` — never instantiate
  `pipeline(...)` directly inside a tool function