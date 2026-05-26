# Feature Specification: Refactor Tone Suggestion Orchestrator

**Feature Branch**: `006-refactor-tone-suggestion-orchestrator`

**Created**: 2026-05-25

**Status**: Draft

**Input**: User description: "Refactor the ToneSuggestionSubagent in the Template Assistant agent..."

## Clarifications

### Session 2026-05-25

- Q: GAP-001: Is the two-stage classify_keys design fully specified? → A: Yes, updated to include exact heuristics, JSON output requirement, and read-only constraint.
- Q: GAP-002: Is the session.state data flow specified as a contract? → A: Yes, added explicit state keys, writers, and readers contract.
- Q: GAP-003: Is the human-in-the-loop confirmation gate specified as a hard rule? → A: Yes, updated to explicitly require `suggestion_id` before `ApplyAgent` runs.
- Q: GAP-004: Is the snapshot ordering rule in ApplyAgent specified as non-negotiable? → A: Yes, snapshot must fully complete before any working copy writes.
- Q: GAP-005: Is the all-or-nothing graph validation in ApplyAgent specified? → A: Yes, all keys must be validated first, raising `KeyNotInGraphError` on failure.
- Q: GAP-006: Is the UndoAgent prerequisite correctly specified as none? → A: Yes, UndoAgent can be triggered at any time without exceptions.
- Q: GAP-007: Is the SNAPSHOT_NONE_SENTINEL restore rule in UndoAgent specified? → A: Yes, keys with the sentinel must be deleted via `hdel`.
- Q: GAP-008: Is the boundary constraint stated explicitly? → A: Yes, added explicit boundaries preventing changes to shared/resolution and other agents.
- Q: GAP-009: Is the file location constraint stated? → A: Yes, all subagents must be in `tone_suggestion_subagent.py`.
- Q: GAP-010: Is the TemplateAssistantAgent transparency rule stated? → A: Yes, the external interface remains exactly the same.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tone Improvement Request (Priority: P1)

A template author asks the assistant to "improve the tone" or "make it sound more professional". The system identifies eligible content but filters out structural elements (like footer copyrights, navigation links, and system buttons) and only rewrites actual tone-bearing prose. The user receives meaningful suggestions without noisy changes to structural elements.

**Why this priority**: Filtering out structural elements is the core problem being solved to improve suggestion quality and reduce system confusion.

**Independent Test**: Can be fully tested by requesting a tone rewrite on a template containing both prose and structural elements, and verifying that only prose is rewritten.

**Acceptance Scenarios**:

1. **Given** a template with both tone-bearing text and structural elements, **When** the user asks to improve the tone, **Then** the system classifies the elements correctly, only rewrites the tone-bearing text, and presents the suggestions to the user.

---

### User Story 2 - Confirm and Apply Suggestions (Priority: P1)

After receiving tone suggestions, the template author reviews the proposed changes and confirms they want to apply them. The system captures a snapshot of the current state, validates the changes, and applies them to the working copy.

**Why this priority**: Applying the suggestions is critical to completing the tone improvement workflow. The human-in-the-loop confirmation gate is a strict requirement.

**Independent Test**: Can be fully tested by confirming a set of generated suggestions and verifying they are saved and a snapshot is created.

**Acceptance Scenarios**:

1. **Given** pending tone suggestions, **When** the user explicitly confirms them, **Then** the system captures a pre-apply snapshot, validates the changes, and saves the confirmed changes.
2. **Given** pending tone suggestions, **When** the user tries to apply them but the suggestion reference is missing or invalid, **Then** the system refuses to run and returns a clear error message.

---

### User Story 3 - Undo Tone Suggestions (Priority: P2)

A template author decides they don't like the applied tone suggestions and asks to undo them. The system restores the previous state from the snapshot.

**Why this priority**: Providing a reliable undo mechanism builds user trust and allows safe experimentation with tone rewrites.

**Independent Test**: Can be fully tested by applying suggestions, requesting an undo, and verifying the template is restored to its pre-apply state.

**Acceptance Scenarios**:

1. **Given** a previously applied tone suggestion with a saved snapshot, **When** the user asks to undo the changes, **Then** the system restores the snapshot values.
2. **Given** a request to undo but no snapshot exists, **When** the undo process runs, **Then** it returns a clear message indicating no snapshot was found, without raising an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST route tone suggestion requests through an orchestrator that delegates to four specialized agents: `KeyClassifierAgent`, `SuggestAgent`, `ApplyAgent`, and `UndoAgent`.
- **FR-002**: The `KeyClassifierAgent` MUST categorize template elements into "tone" and "structural" using a two-stage process:
  - **Stage 1 (Deterministic)**: No LLM call. Keys are classified structural if their canonical name contains suffixes (`_URL`, `_LINK`, `_HREF`, `_SRC`, `_IMG`, `_IMAGE`, `_LOGO`, `_ICON`, `_COLOR`, `_COLOUR`, `_BG`, `_BACKGROUND`, `_ID`, `_CODE`, `_TAG`, `_TRACK`) or substrings (`FOOTER`, `HEADER`, `COPYRIGHT`, `NAV`, `PRIVACY`, `LEGAL`, `COOKIE`, `UNSUBSCRIBE`, `TRACKING`, `PIXEL`, `BEACON`, `VIEWINBROWSER`, `VIEW_IN_BROWSER`) case-insensitively.
  - **Stage 2 (LLM)**: A single LLM call classifies remaining ambiguous keys. The prompt MUST request JSON output only: `[{"key": "...", "role": "tone" | "structural"}]`.
- **FR-003**: The `KeyClassifierAgent` is a read-only call. It MUST NOT write to Redis or PostgreSQL.
- **FR-004**: The `SuggestAgent` MUST process only the "tone" elements, evaluate the baseline emotion, look up the target profile, generate rewrites, and validate the response to discard hallucinations or identical values. `SuggestAgent` MUST read its candidate key set exclusively from `session.state["tone_bearing_keys"]`. It MUST NOT call `_build_reachable_eligible()` or read `eligible_keys` directly. It MUST NOT write to Redis.
- **FR-005**: The `ApplyAgent` MUST require a valid `suggestion_id` in `session.state`. It MUST capture a pre-apply snapshot to Redis, and this snapshot MUST fully complete before any call to `set_working_copy_value()`. If the snapshot write fails, it MUST abort entirely (no partial writes). If a tone snapshot already exists for this session when `ApplyAgent` runs, it MUST be overwritten entirely by the new pre-apply snapshot. `apply_tone_suggestions` MUST include `snapshot_overwritten: bool` in its return payload. When true, the orchestrator MUST inform the user that the previous undo snapshot has been replaced.
- **FR-006**: The `ApplyAgent` MUST perform all-or-nothing graph validation. It MUST validate ALL confirmed keys against the resolution graph first, then write ALL keys or write NONE. Raising `KeyNotInGraphError` MUST prevent any Redis write.
- **FR-007**: The `UndoAgent` MUST be triggerable at any session point (no prerequisite of prior suggestion or apply). If no snapshot exists, it MUST return a clear message and MUST NOT raise an exception. `UndoAgent` supersedes the `NoSnapshotError` contract in the original tool definition. The underlying `undo_tone_suggestions` function MUST be updated to return `{"restored": 0, "message": "No tone suggestion snapshot found for this session."}` rather than raising `NoSnapshotError`.
- **FR-008**: The `UndoAgent` MUST read the snapshot and restore the previous state. If a snapshot value equals `SNAPSHOT_NONE_SENTINEL`, the key MUST be deleted from the working copy using `hdel`, not overwritten with the sentinel string.
- **FR-009**: The orchestrator MUST enforce a human-in-the-loop confirmation gate by presenting the suggestions to the user and waiting for explicit confirmation before delegating to the `ApplyAgent`. `ApplyAgent` MUST NEVER be called without a `suggestion_id` in `session.state`.

### Data Model

The return schema of the `classify_keys` tool MUST be:
```json
{
    "tone_bearing": "dict[str, str]",
    "structural": "dict[str, str]",
    "stage1_structural_count": "int",
    "stage2_structural_count": "int",
    "tone_bearing_count": "int"
}
```
*Note: The distinction between `tone_bearing` (return value field) and `tone_bearing_keys` (`session.state` key name) MUST be explicit to ensure the ADK tool wrapper is written correctly. `stage1_structural_count` represents keys classified structural by name heuristics, `stage2_structural_count` represents keys classified structural by LLM, and `tone_bearing_count` represents `len(tone_bearing)`.*

### Session State Data Flow Contract

The following keys in `session.state` MUST be strictly managed:
- `eligible_keys` (dict[str, str]): Written by orchestrator (`_build_reachable_eligible()`), read by `KeyClassifierAgent`.
- `tone_bearing_keys` (dict[str, str]): Written by `KeyClassifierAgent`, read by `SuggestAgent`.
- `structural_keys` (dict[str, str]): Written by `KeyClassifierAgent`, used by orchestrator for reporting.
- `suggestions` (list[dict]): Written by `SuggestAgent`, read by `ApplyAgent`.
- `suggestion_id` (str): Written by `SuggestAgent`, read by `ApplyAgent`.
*Rule: A reader MUST NEVER be implemented before its writer.*

### Constraints & Boundaries

- **Boundary Constraint**: There MUST BE NO changes to `shared/resolution/`, `ResolutionSubagent`, `WorkingCopySubagent`, `ToneEvaluationSubagent`, `TemplateAssistantAgent`, or any existing tests.
- **File Location Constraint**: All four specialist subagents MUST be defined in `template_assistant/subagents/tone_suggestion_subagent.py`, not in separate files.
- **Transparency Rule**: The external interface of `ToneSuggestionSubagent` MUST remain unchanged. `TemplateAssistantAgent` MUST see exactly one subagent with the same name and description, requiring no modification.

### Testing Strategy

- **New file: `template_assistant/tests/test_key_classifier.py`**:
  - `test_stage1_structural_suffix`: `EN.LOGO_URL` → structural, no LLM call.
  - `test_stage1_structural_substring`: `EN.FOOTER_COPYRIGHT` → structural, no LLM call.
  - `test_stage1_passes_ambiguous`: `EN.PARAGRAPH_1` with prose value → not caught, passed to Stage 2.
  - `test_stage2_classifies_tone`: stub LLM returns `[{"key": "EN.PARAGRAPH_1", "role": "tone"}]`, verify in `tone_bearing`.
  - `test_stage2_hallucinated_key_discarded`: LLM returns a key not in input, verify absent from both outputs.
  - `test_stage2_fallback_on_failure`: LLM call throws, verify all Stage 2 keys land in `tone_bearing`.
  - `test_all_structural_no_llm_call`: all keys caught by Stage 1, verify Stage 2 is never called.
  - `test_state_keys_written`: after `_classify_keys_tool`, `session.state` contains both `tone_bearing_keys` and `structural_keys`.
- **Updated: `template_assistant/tests/test_tone_suggestion_subagent.py`**:
  - `test_suggest_reads_tone_bearing_keys`: verify `SuggestAgent` reads from `tone_bearing_keys`, not `eligible_keys`.
  - `test_apply_refuses_without_suggestion_id`: `ApplyAgent` returns error dict when `suggestion_id` absent.
  - `test_e2e_structural_keys_excluded`: end-to-end with real DB/Redis. The test MUST assert that no key in the returned suggestions has a name matching any suffix or substring from the Stage 1 heuristic lists. This assertion holds regardless of the specific keys present in the test template, making the test robust to template content changes.
- **Note**: LLM calls in classifier tests use a stub injected via `set_classifier_llm_fn` — real DB and Redis are used throughout. `_llm_classify_keys` MUST expose a module-level override via `set_classifier_llm_fn(fn)` following the same pattern as `set_llm_batch_fn`. Tests inject a stub via this function; production code uses the default LLM call.

### Edge Cases

- **Classification failure/timeout**: `_llm_classify_keys` MUST catch LLM call exceptions and fall back to treating all ambiguous keys (the Stage 2 input) as `tone`. This fallback MUST be logged as a warning, not surfaced as an error to the user. This ensures no valid tone-bearing keys are silently dropped.
- **Partial confirmation**: The orchestrator passes the user's confirmed key list (or `None` for "all") to `apply_tone_suggestions` as the `confirmed_keys` argument. The snapshot still covers the full suggestion batch, not only the confirmed subset, so undo restores everything regardless of what was confirmed.
- **Template structure change between suggest and apply**: `ApplyAgent`'s all-or-nothing graph validation (FR-006) handles this. If a key disappeared from the graph between suggest and apply, `KeyNotInGraphError` fires and nothing is written. No additional handling is needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of structural elements (e.g., navigation, legal boilerplate, system links) are filtered out and never sent for tone rewriting.
- **SC-002**: The system successfully processes tone rewrites without the instruction-adherence degradation previously seen in the monolithic approach.
- **SC-003**: The orchestrator correctly routes intents to the appropriate specialized agents without breaking the existing conversational flow.
- **SC-004**: The external interface remains 100% compatible with the main assistant.

## Assumptions

- The existing underlying capabilities (emotion baseline evaluation, tone profile lookup, snapshotting) are preserved and reused by the new specialized agents.
- The initial list of eligible elements is correctly built before delegation to the classifier.
- The storage infrastructure supports the snapshot and working copy operations required by the applier and undoer.