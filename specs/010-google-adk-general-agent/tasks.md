# Tasks: Google ADK General Agent

**Input**: Design documents from `/specs/010-google-adk-general-agent/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create `general_agent` package structure per implementation plan
- [X] T002 Add `sentence-transformers` and `pgvector` to project dependencies
- [X] T003 [P] Define `TemplateSearchResult` dataclass in `general_agent/models.py`
- [X] T004 [P] Define `ToneDiscoveryResult` dataclass in `general_agent/models.py`
- [X] T005 [P] Define `StructuralSummary` dataclass in `general_agent/models.py`
- [X] T006 [P] Define `ResolutionHealthResult` dataclass in `general_agent/models.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement pgvector query helper in `shared/embeddings.py`
- [X] T007b [P] Create `general_agent/ml/__init__.py` as an empty package init file
- [X] T008 Implement encoder singleton and `encode_query` in `general_agent/ml/embeddings.py` (lazy-load `get_encoder()` singleton)
- [X] T008a Pre-download `sentence-transformers/all-mpnet-base-v2` model and verify 768-dimension output shape
- [X] T008b Verify the column name `summary_embeded` exists in the live database
- [X] T009 Create base `GeneralAgent` root agent class in `general_agent/agent.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Find Templates by Natural Language Intent (Priority: P1) 🎯 MVP

**Goal**: Find templates using natural language descriptions of their intent.

**Independent Test**: Can be fully tested by asking the agent to find templates for a specific purpose (e.g., "Find a template for changing the password") and verifying that relevant templates are returned based on semantic similarity.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Integration test for `semantic_search_templates` in `tests/general_agent/integration/test_semantic_search.py`

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement `SemanticSearchSubagent` and `semantic_search_templates` tool in `general_agent/subagents/semantic_search_subagent.py`
- [X] T012 [US1] Register `SemanticSearchSubagent` as a subagent in `GeneralAgent` (`general_agent/agent.py`)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Find Templates by Keyword Match (Priority: P1)

**Goal**: Find templates by searching for exact terms in the template name, subject, or summary.

**Independent Test**: Can be fully tested by asking the agent to find templates containing a specific word (e.g., "Find templates with 'reset' in the subject") and verifying that only templates matching the keyword are returned.

### Tests for User Story 2

- [X] T013 [P] [US2] Integration test for `keyword_search_templates` in `tests/general_agent/integration/test_keyword_search.py`

### Implementation for User Story 2

- [X] T014 [P] [US2] Implement `KeywordSearchSubagent` and `keyword_search_templates` tool in `general_agent/subagents/keyword_search_subagent.py`
- [X] T015 [US2] Register `KeywordSearchSubagent` as a subagent in `GeneralAgent` (`general_agent/agent.py`)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Audit Template Structure and Health (Priority: P2)

**Goal**: Query the structural composition and resolution health of templates.

**Independent Test**: Can be fully tested by asking the agent about template dependencies (e.g., "Which templates include content block 123?") and verifying that the correct templates are identified based on pre-computed structural data.

### Tests for User Story 3

- [X] T016 [P] [US3] Integration test for structural queries in `tests/general_agent/integration/test_structural_query.py`
- [X] T016a [P] [US3] Integration test verifying `get_template_resolution_health` returns `health_score = 1.0` for a template with no unresolvable keys

### Implementation for User Story 3

- [X] T017 [P] [US3] Implement `StructuralQuerySubagent` and its tools in `general_agent/subagents/structural_query_subagent.py`
- [X] T018 [US3] Register `StructuralQuerySubagent` as a subagent in `GeneralAgent` (`general_agent/agent.py`)

**Checkpoint**: All user stories up to US3 should be independently functional

---

## Phase 6: User Story 4 - Discover Templates by Emotional Tone (Priority: P2)

**Goal**: Find and rank templates based on their emotional character.

**Independent Test**: Can be fully tested by asking the agent to find templates with a specific tone (e.g., "Find templates where urgency is above 0.7") and verifying that the returned templates match the criteria based on pre-computed tone evaluations.

### Tests for User Story 4

- [X] T019 [P] [US4] Integration test for tone discovery queries in `tests/general_agent/integration/test_tone_discovery.py`
- [X] T019a [P] [US4] Integration test verifying `find_templates_by_tone` returns an empty list when no templates meet the `min_score` threshold

### Implementation for User Story 4

- [X] T020 [P] [US4] Implement `ToneDiscoverySubagent` and its tools in `general_agent/subagents/tone_discovery_subagent.py`
- [X] T021 [US4] Register `ToneDiscoverySubagent` as a subagent in `GeneralAgent` (`general_agent/agent.py`)

**Checkpoint**: All user stories up to US4 should be independently functional

---

## Phase 7: User Story 5 - Combine Multiple Search Strategies (Priority: P3)

**Goal**: Find templates using a combination of intent, keywords, structure, and tone.

**Independent Test**: Can be fully tested by asking a complex query (e.g., "find password-related templates that feel reassuring") and verifying that the agent delegates to multiple specialized search capabilities to produce a combined result.

### Tests for User Story 5

- [X] T022 [P] [US5] End-to-end fan-out test covering a multi-subagent query (e.g. "find reassuring password templates" -> SemanticSearch + ToneDiscovery) in `tests/general_agent/e2e/test_fan_out.py`

### Implementation for User Story 5

- [X] T023 [US5] Update `GeneralAgent` prompt/configuration in `general_agent/agent.py` to ensure correct fan-out and result merging behavior.

**Checkpoint**: All user stories should now be independently functional

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T024 Verify all subagents strictly adhere to read-only constraints.
- [X] T025 Verify all tool signatures enforce the result limit (default 10, max 50).
- [X] T026 Update documentation and run quickstart.md validation.

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
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 5 (P3)**: Depends on US1, US2, US3, and US4 being complete.

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, US1, US2, US3, and US4 can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1 & 2

```bash
# Launch tests for User Story 1 and 2 together:
Task: "Integration test for semantic_search_templates in tests/general_agent/integration/test_semantic_search.py"
Task: "Integration test for keyword_search_templates in tests/general_agent/integration/test_keyword_search.py"

# Launch implementation for User Story 1 and 2 together:
Task: "Implement SemanticSearchSubagent and semantic_search_templates tool in general_agent/subagents/semantic_search_subagent.py"
Task: "Implement KeywordSearchSubagent and keyword_search_templates tool in general_agent/subagents/keyword_search_subagent.py"
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
5. Add User Story 4 → Test independently → Deploy/Demo
6. Add User Story 5 → Test independently → Deploy/Demo
7. Each story adds value without breaking previous stories
