---
description: "Task list template for feature implementation"
---

# Tasks: Refactor Tone Suggestion Orchestrator

**Input**: Design documents from `/specs/006-refactor-tone-suggestion-orchestrator/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: The examples below include test tasks. Tests are OPTIONAL - only include them if explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create `template_assistant/tests/test_key_classifier.py` file with basic imports and structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Implement `_apply_structural_heuristics(key: str) -> bool` in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T003 [P] Implement `_llm_classify_keys(keys: dict[str, str]) -> dict[str, str]` in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T004 [P] Implement `set_classifier_llm_fn(fn: Callable | None) -> None` in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T005 Implement `classify_keys(eligible_keys: dict[str, str], session_state: dict) -> dict` in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T006 Implement `_classify_keys_tool(tool_context: ToolContext) -> dict` in `template_assistant/subagents/tone_suggestion_subagent.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Tone Improvement Request (Priority: P1) 🎯 MVP

**Goal**: Filter out structural elements and only rewrite actual tone-bearing prose.

**Independent Test**: Can be fully tested by requesting a tone rewrite on a template containing both prose and structural elements, and verifying that only prose is rewritten.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US1] Implement `test_stage1_structural_suffix` in `template_assistant/tests/test_key_classifier.py`
- [X] T008 [P] [US1] Implement `test_stage1_structural_substring` in `template_assistant/tests/test_key_classifier.py`
- [X] T009 [P] [US1] Implement `test_stage1_tone_bearing` in `template_assistant/tests/test_key_classifier.py`
- [X] T010 [P] [US1] Implement `test_stage2_llm_classification` in `template_assistant/tests/test_key_classifier.py`
- [X] T011 [P] [US1] Implement `test_stage2_hallucinated_key_discarded` in `template_assistant/tests/test_key_classifier.py`
- [X] T012 [P] [US1] Implement `test_stage2_fallback_on_failure` in `template_assistant/tests/test_key_classifier.py`
- [X] T013 [P] [US1] Implement `test_classify_keys_empty_input` in `template_assistant/tests/test_key_classifier.py`
- [X] T014 [P] [US1] Implement `test_classify_keys_all_structural` in `template_assistant/tests/test_key_classifier.py`
- [X] T015 [P] [US1] Implement `test_state_keys_written` in `template_assistant/tests/test_key_classifier.py`
- [X] T016 [P] [US1] Implement `test_suggest_reads_tone_bearing_keys` in `template_assistant/tests/test_tone_suggestion_subagent.py`
- [X] T017 [P] [US1] Implement `test_e2e_structural_keys_excluded` in `template_assistant/tests/test_tone_suggestion_subagent.py`

### Implementation for User Story 1

- [X] T018 [US1] Update `_suggest_tone_rewrites_tool` to read `tone_bearing_keys` from `session.state` in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T019 [US1] Define `KeyClassifierAgent` using `LlmAgent` in `template_assistant/subagents/tone_suggestion_subagent.py` (depends on T006)
- [X] T020 [US1] Define `SuggestAgent` using `LlmAgent` in `template_assistant/subagents/tone_suggestion_subagent.py` (depends on T018)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Confirm and Apply Suggestions (Priority: P1)

**Goal**: Capture snapshot, validate changes, and apply them to the working copy after user confirmation.

**Independent Test**: Can be fully tested by confirming a set of generated suggestions and verifying they are saved and a snapshot is created.

### Tests for User Story 2

- [X] T021 [P] [US2] Implement `test_apply_refuses_without_suggestion_id` in `template_assistant/tests/test_tone_suggestion_subagent.py`

### Implementation for User Story 2

- [X] T022 [US2] Update `_apply_tone_suggestions_tool` to: require `suggestion_id` from `session.state` (return error dict if absent), capture snapshot before any working copy write (hard ordering), enforce all-or-nothing graph validation via `KeyNotInGraphError`, include `snapshot_overwritten: bool` in return payload in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T023 [US2] Define `ApplyAgent` using `LlmAgent` in `template_assistant/subagents/tone_suggestion_subagent.py`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Undo Tone Suggestions (Priority: P2)

**Goal**: Restore previous state from snapshot.

**Independent Test**: Can be fully tested by applying suggestions, requesting an undo, and verifying the template is restored to its pre-apply state.

### Tests for User Story 3

<!-- E2E test moved to Phase N -->

### Implementation for User Story 3

- [X] T024 [US3] Update `_undo_tone_suggestions_tool` to return a message dict instead of raising `NoSnapshotError` in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T025 [US3] Define `UndoAgent` using `LlmAgent` in `template_assistant/subagents/tone_suggestion_subagent.py`

**Checkpoint**: All user stories should now be independently functional

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T026 Update `ToneSuggestionSubagent` to set `sub_agents=[KeyClassifierAgent, SuggestAgent, ApplyAgent, UndoAgent]` and `tools=[]` in one operation in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T027 Implement `test_e2e_full_flow` covering classify → suggest → apply → undo with real PostgreSQL and Redis in `template_assistant/tests/test_tone_suggestion_subagent.py`
- [X] T028 Run `pytest template_assistant/tests/ -k 'not test_key_classifier and not test_e2e'` to confirm all pre-existing tests pass unchanged. This validates the boundary constraint — no regressions introduced by the refactor.
- [X] T029 Run quickstart.md validation (run `pytest template_assistant/tests/`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Integrates with US1 flow
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Integrates with US1/US2 flow

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Models within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Implement test_stage1_structural_suffix in template_assistant/tests/test_key_classifier.py"
Task: "Implement test_stage1_structural_substring in template_assistant/tests/test_key_classifier.py"
# ... and so on for all T007-T017 tasks
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories
