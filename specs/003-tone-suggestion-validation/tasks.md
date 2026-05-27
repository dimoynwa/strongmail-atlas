---

description: "Task list for Tone Suggestion Validation feature implementation"
---

# Tasks: Tone Suggestion Validation

**Input**: Design documents from `/specs/003-tone-suggestion-validation/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Test tasks are included as requested in the specification (TDD approach).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create `EligibilityResult` and `DiscardedSuggestion` dataclasses in `template_assistant/subagents/tone_suggestion_subagent.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 Implement `is_eligible_for_rewrite` helper function with full type hints in `template_assistant/subagents/tone_suggestion_subagent.py`
- [X] T003 [P] Write tests for `is_eligible_for_rewrite` covering all five filter rules in `template_assistant/tests/test_tone_suggestion_key_validation.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Prevent LLM Hallucinations in Tone Suggestions (Priority: P1) 🎯 MVP

**Goal**: The system only suggests tone rewrites for valid placeholder keys, silently discarding hallucinated keys and returning them in the `discarded_keys` field.

**Independent Test**: Can be fully tested by mocking an LLM response that includes hallucinated keys and verifying that only eligible keys are returned as suggestions.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation.**
> **The `[P]` marker indicates T004 and T005 can run in parallel with each other. They MUST be completed before T006-T009 begin.**

- [X] T004 [P] [US1] Write test: `suggest_tone_rewrite` with mocked LLM response containing a hallucinated key in `template_assistant/tests/test_tone_suggestion_key_validation.py`
- [X] T005 [P] [US1] Write test: `suggest_tone_rewrite` returns empty suggestions when LLM returns only hallucinated keys in `template_assistant/tests/test_tone_suggestion_key_validation.py`

### Implementation for User Story 1

- [X] T006 [US1] Update `suggest_tone_rewrite` in `template_assistant/subagents/tone_suggestion_subagent.py` to derive eligible set using graph + working copy
- [X] T007 [US1] Update `suggest_tone_rewrite` LLM prompt to include explicit constraints and request structured JSON
- [X] T008 [US1] Update `suggest_tone_rewrite` response validation to filter against eligible set and populate `discarded_keys`
- [X] T009 [US1] Update `suggest_tone_rewrite` return schema to include `discarded_keys` in `template_assistant/subagents/tone_suggestion_subagent.py`

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Strict Graph Validation Before Writing to Redis (Priority: P1)

**Goal**: The system strictly validates all keys against the resolution graph before writing them to the Redis working copy, preventing partial writes.

**Independent Test**: Can be fully tested by attempting to apply a tone suggestion for a key that does not exist in the graph, verifying that a `KeyNotInGraphError` is raised and no partial writes occur.

### Tests for User Story 2 ⚠️

- [X] T010 [P] [US2] Write test: `apply_tone_suggestions` raises `KeyNotInGraphError` for invalid key in `template_assistant/tests/test_tone_suggestion_key_validation.py`
- [X] T011 [P] [US2] Write test: `apply_tone_suggestions` prevents partial writes (one invalid key → no keys written) in `template_assistant/tests/test_tone_suggestion_key_validation.py`
- [X] T012 [P] [US2] Write test: `apply_tone_suggestions` succeeds end-to-end when all keys are valid in `template_assistant/tests/test_tone_suggestion_key_validation.py`

### Implementation for User Story 2

- [X] T013 [US2] Update `apply_tone_suggestions` in `template_assistant/subagents/tone_suggestion_subagent.py` to implement atomic all-or-nothing graph validation gate, raising `KeyNotInGraphError` with `invalid_keys` and `valid_keys_not_written` payload if any key fails

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T014 Run full test suite and confirm all pass: `pytest template_assistant/tests/test_tone_suggestion_key_validation.py -v` and `pytest template_assistant/tests/ -v`. Confirm the bug regression: send "Make this template feel more approval and exciting." → apply all → verify no BODY or SUBJECT keys in Redis working copy.

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
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Write test: suggest_tone_rewrite with mocked LLM response containing a hallucinated key"
Task: "Write test: suggest_tone_rewrite returns empty suggestions when LLM returns only hallucinated keys"
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
4. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
3. Stories complete and integrate independently