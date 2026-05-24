---
description: "Task list template for feature implementation"
---

# Tasks: Placeholder Resolution Engine

**Input**: Design documents from `specs/001-placeholder-resolution-engine/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Integration tests follow each module's implementation task (real PostgreSQL + Redis, no mocks).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Update pyproject.toml requires-python to >=3.11 in pyproject.toml
- [x] T002 [P] Create directory structure for shared/resolution and tests/integration
- [x] T003 [P] Initialize empty __init__.py files in shared/__init__.py and shared/resolution/__init__.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create database connection pool singleton in shared/db.py
- [x] T005 [P] Create redis connection client singleton in shared/redis_client.py
- [x] T006 [P] Create integration test fixtures in tests/integration/conftest.py
- [x] T007 Define ReasonCode, UnresolvableEntry, ResolutionResult dataclasses and exceptions in shared/resolution/resolver.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Build Resolution Graph (Priority: P1) 🎯 MVP

**Goal**: Load complete set of placeholder key→value pairs for a template from the database into an immutable in-memory structure.

**Independent Test**: Call the graph-building function with a known template name and verify the returned map contains the expected keys and raw values.

### Implementation for User Story 1

- [x] T008 [P] [US1] Implement build_resolution_graph in shared/resolution/graph_builder.py
- [x] T009 [US1] Add integration tests for graph building in tests/integration/test_graph_builder.py
- [x] T010 [US1] Export build_resolution_graph in shared/resolution/__init__.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Resolve Full Template Body (Priority: P2)

**Goal**: Evaluate template bodies, replacing ##PLACEHOLDER## tokens with final values and tracking unresolvables recursively.

**Independent Test**: Use a template body string with placeholders (including chained and missing ones). Verify output string and unresolvable list.

### Implementation for User Story 2 — namespace module

- [x] T011 [P] [US2] Implement normalize_key and expand_namespace_prefix in shared/resolution/namespace.py
- [x] T012 [US2] Add integration tests for namespace logic in tests/integration/test_namespace.py

### Implementation for User Story 2 — SM_RULE module

- [x] T013 [P] [US2] Implement SM_RULE evaluation logic in shared/resolution/sm_rule_evaluator.py
- [x] T014 [US2] Add integration tests for SM_RULE evaluation in tests/integration/test_sm_rule_evaluator.py

### Implementation for User Story 2 — resolver (resolve_body)

- [x] T015 [US2] Implement resolve_body in shared/resolution/resolver.py
- [x] T016 [US2] Add integration tests for full body resolution in tests/integration/test_resolver.py
- [x] T017 [US2] Export resolve_body in shared/resolution/__init__.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Resolve Single Placeholder Key (Priority: P3)

**Goal**: Resolve a single placeholder key to its final string value without evaluating an entire body.

**Independent Test**: Call single-key resolution with a key that chains through two intermediate placeholders. Verify the final resolved string.

### Implementation for User Story 3

- [x] T018 [US3] Implement resolve_key in shared/resolution/resolver.py
- [x] T019 [US3] Add integration tests for single key resolution in tests/integration/test_resolver.py
- [x] T020 [US3] Export resolve_key in shared/resolution/__init__.py

**Checkpoint**: User Story 3 should be fully functional and testable independently

---

## Phase 6: User Story 4 - Working Copy Priority in Resolution (Priority: P4)

**Goal**: Check the session working copy store in Redis before consulting the resolution graph for every lookup.

**Independent Test**: Write an override value to Redis for a session, then verify full-body resolution uses the override over the database.

### Implementation for User Story 4

- [x] T021 [US4] Update resolve_body and resolve_key to use working copy overrides in shared/resolution/resolver.py
- [x] T022 [US4] Add integration tests for working copy priority in tests/integration/test_resolver.py

---

## Phase 7: User Story 5 - Unresolvable Placeholder Scan (Priority: P5)

**Goal**: Report data quality issues by returning a structured report of all unresolvable keys and their reasons.

**Independent Test**: Supply a body with missing keys, cycles, and broken rule chains, then verify exactly the expected reason codes are returned.

### Implementation for User Story 5

- [x] T023 [US5] Implement scan_unresolvable in shared/resolution/resolver.py
- [x] T024 [US5] Add integration tests for unresolvable placeholder scan in tests/integration/test_resolver.py
- [x] T025 [US5] Export scan_unresolvable in shared/resolution/__init__.py

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T026 [P] Verify all docstrings, type hints, and code formatting across shared/resolution/*.py
- [x] T027 Run all integration tests and ensure performance goals (under 500ms) are met
- [x] T028 Add end-to-end integration test exercising full pipeline (graph build → resolve_body → scan_unresolvable) in tests/integration/test_e2e_pipeline.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories proceed sequentially in priority order (P1 → P2 → P3 → P4 → P5)
- **Polish (Final Phase)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2)
- **User Story 2 (P2)**: Depends on User Story 1 (requires `build_resolution_graph`) and T007 dataclasses
- **User Story 3 (P3)**: Depends on User Story 2 `resolve_body` core logic
- **User Story 4 (P4)**: Modifies resolver logic from User Stories 2 and 3
- **User Story 5 (P5)**: Depends on User Story 2 resolver components

### Module-Level Parallel Opportunities

- **T008** (`graph_builder.py`) and **T011** (`namespace.py`) have no dependency on each other — both marked `[P]` and can run in parallel once Phase 2 completes
- **T011** (`namespace.py`) and **T013** (`sm_rule_evaluator.py`) have no dependency on each other — both marked `[P]`
- Within each module: implementation task → integration test task (strict ordering)

### Within Each Module

- Implement module in `shared/resolution/`
- Add integration tests in `tests/integration/` (immediately after that module's implementation)
- Export public API from `shared/resolution/__init__.py` when applicable

---

## Parallel Example: Independent Modules

```bash
# After Phase 2 completes, launch independent module implementations together:
Task T008: "Implement build_resolution_graph in shared/resolution/graph_builder.py"
Task T011: "Implement normalize_key and expand_namespace_prefix in shared/resolution/namespace.py"

# Within User Story 2, launch SM_RULE alongside namespace (after T011 if desired):
Task T011: "Implement namespace.py"
Task T013: "Implement sm_rule_evaluator.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `tests/integration/test_graph_builder.py`

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently
3. Add User Story 2 (namespace → sm_rule → resolve_body, each with tests) → Test independently
4. Add User Story 3 → Test independently
5. Add User Story 4 → Test independently
6. Add User Story 5 → Test independently
7. Run T028 end-to-end pipeline test
