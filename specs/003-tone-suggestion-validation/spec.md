# Feature Specification: Tone Suggestion Validation

**Feature Branch**: `003-tone-suggestion-validation`

**Created**: May 25, 2026

**Status**: Draft

**Input**: User description: "Patch the ToneSuggestionSubagent in template_assistant/subagents/tone_suggestion_subagent.py to prevent hallucinated placeholder keys from being written to the Redis working copy. This is a targeted patch to two existing tools..."

## Clarifications

### Session 2026-05-25
- Q: Are the data model additions explicit? → A: Yes, added a `Data Model Changes` section detailing `EligibilityResult`, `DiscardedSuggestion`, and updates to the tool return schema and error payload.
- Q: Is the testing strategy explicitly defined? → A: Yes, added a `Testing Strategy` section specifying `pytest` + `pytest-asyncio`, real DB/Redis, LLM stub fixtures, and the new test file.
- Q: Is the eligibility filter defined as a standalone helper function? → A: Yes, updated FR-013 to explicitly require `is_eligible_for_rewrite(key: str, value: str, lang_local: str, param_cust_brand: str) -> bool` and forbid inlining.
- Q: Are all five eligibility rules stated explicitly? → A: Yes, FR-001 through FR-006 cover all rules explicitly.
- Q: Is the working-copy-first resolution order stated? → A: Yes, FR-007 explicitly requires checking the Redis working copy value first.
- Q: Is the LLM prompt constraint stated as a hard instruction? → A: Yes, FR-008 and FR-009 were updated to include the exact instruction text and enforce structured JSON.
- Q: Is the post-LLM validation rule explicit? → A: Yes, FR-010 was updated to explicitly forbid raising exceptions or surfacing errors for hallucinated keys.
- Q: Is the apply_tone_suggestions graph check specified as an atomic all-or-nothing gate? → A: Yes, FR-011 and FR-012 were updated to explicitly require an atomic all-or-nothing gate.
- Q: Is KeyNotInGraphError specified as a reuse of the existing error class? → A: Yes, added to the new Boundaries & Constraints section.
- Q: Are the boundaries stated clearly? → A: Yes, added a Boundaries & Constraints section to forbid changes to `shared/resolution/` and other subagents.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prevent LLM Hallucinations in Tone Suggestions (Priority: P1)

As a user of the template assistant, I want the system to only suggest tone rewrites for valid placeholder keys, so that I am not prompted to confirm phantom keys that don't exist in the resolution graph.

**Why this priority**: Preventing hallucinated keys from being processed ensures the integrity of the resolution system and prevents confusing user prompts.

**Independent Test**: Can be fully tested by mocking an LLM response that includes hallucinated keys and verifying that only eligible keys are returned as suggestions.

**Acceptance Scenarios**:

1. **Given** an LLM response containing both eligible and hallucinated keys, **When** `suggest_tone_rewrite` processes the response, **Then** the hallucinated keys are silently discarded, a warning is logged, and only eligible keys are returned.
2. **Given** an LLM response containing *only* hallucinated keys, **When** `suggest_tone_rewrite` processes the response, **Then** an empty suggestion list is returned with a message indicating no valid keys were generated.

---

### User Story 2 - Strict Graph Validation Before Writing to Redis (Priority: P1)

As a system administrator, I want the system to strictly validate all keys against the resolution graph before writing them to the Redis working copy, so that invalid keys can never corrupt the working state.

**Why this priority**: This is the last line of defense against data corruption in the working copy.

**Independent Test**: Can be fully tested by attempting to apply a tone suggestion for a key that does not exist in the graph, verifying that a `KeyNotInGraphError` is raised and no partial writes occur.

**Acceptance Scenarios**:

1. **Given** a list of suggested keys where all exist in the graph, **When** `apply_tone_suggestions` is called, **Then** all keys are successfully written to Redis.
2. **Given** a list of suggested keys where one or more do *not* exist in the graph, **When** `apply_tone_suggestions` is called, **Then** a `KeyNotInGraphError` is raised listing the invalid keys, and NO keys are written to Redis.

### Edge Cases

- What happens when the LLM returns keys that match the eligibility rules but have slightly different casing? (Handled by exact string match constraint).
- How does the system handle an empty resolution graph? (No keys will be eligible, LLM will not be prompted with keys).
- What happens if a key's working-copy value is eligible, but its raw graph value is not (or vice versa)? (The working-copy value is used for eligibility checking if present).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST filter eligible keys for tone rewrite based on strict prefix matching (`lang_local`, `param_cust_brand`, or `GENERIC.`).
- **FR-002**: System MUST exclude keys starting with `SM_RULE_`.
- **FR-003**: System MUST exclude keys whose resolved values start with `http://` or `https://`.
- **FR-004**: System MUST exclude keys whose resolved values match CSS color patterns (`#RGB`, `#RRGGBB`, `rgb(...)`, `rgba(...)` case-insensitive).
- **FR-005**: System MUST exclude keys whose resolved values (stripped of whitespace) are numeric-only.
- **FR-006**: System MUST exclude keys whose resolved values (stripped of whitespace) are 20 characters or shorter.
- **FR-007**: System MUST use the working-copy value for eligibility checking if present; otherwise, it MUST use the raw graph value.
- **FR-008**: System MUST include the complete eligible key set in the LLM prompt and explicitly instruct the LLM: "Return rewrites ONLY for keys from this exact list. Do not introduce, rename, or abbreviate any key. Use the exact key string as provided."
- **FR-009**: System MUST request a structured JSON response from the LLM (list of objects with `key` and `new_value` only).
- **FR-010**: System MUST silently discard any keys returned by the LLM that are not in the eligible set and log a warning. It MUST NEVER raise an exception for hallucinated keys and MUST NEVER surface them to the user as an error.
- **FR-011**: System MUST verify ALL keys against the resolution graph before writing ANY key to Redis in `apply_tone_suggestions` (atomic all-or-nothing gate).
- **FR-012**: System MUST raise the existing `KeyNotInGraphError` and prevent any writes if any key in `apply_tone_suggestions` is not found in the graph. Never write some keys and reject others in the same call.
- **FR-013**: The eligibility filter logic MUST be encapsulated in a standalone helper function `is_eligible_for_rewrite(key: str, value: str, lang_local: str, param_cust_brand: str) -> bool` within `tone_suggestion_subagent.py`. It MUST NOT be inlined inside `suggest_tone_rewrite`.

### Key Entities

- **Resolution Graph**: The source of truth for all valid placeholder keys and their raw values.
- **Eligible Key Set**: A subset of the resolution graph keys that meet all criteria for tone rewriting.
- **Working Copy**: The Redis-backed store for modified placeholder values.

### Data Model Changes

- **`EligibilityResult` dataclass**: Fields: `key: str`, `value: str`, `eligible: bool`, `reason: str | None` (with enumerated reason values).
- **`DiscardedSuggestion` dataclass**: Fields: `key: str`, `reason: str` (e.g., "hallucinated_key").
- **`suggest_tone_rewrite` return schema**: Add `discarded_keys: list[DiscardedSuggestion]`.
- **`apply_tone_suggestions` error payload**: Add `invalid_keys` and `valid_keys_not_written` fields to `KeyNotInGraphError`.

### Boundaries & Constraints

- **No Shared Changes**: Do not modify `shared/resolution/` in any way.
- **No Other Subagents**: Do not modify any other subagent or tool outside of `tone_suggestion_subagent.py`.
- **Reuse Existing Code**: `build_graph()` and `KeyNotInGraphError` already exist from Spec 002 — reuse them, do not redefine them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of keys written to the Redis working copy by `apply_tone_suggestions` exist in the resolution graph.
- **SC-002**: 0% of hallucinated keys returned by the LLM are presented to the user as suggestions.
- **SC-003**: 100% of keys passed to the LLM for rewriting meet all eligibility criteria (prefix, length, non-numeric, non-URL, non-color).

## Testing Strategy

- **Framework**: `pytest` + `pytest-asyncio`.
- **Infrastructure**: Real PostgreSQL and Redis — no mocks for DB or Redis.
- **LLM Mocking**: LLM responses in `suggest_tone_rewrite` validation tests may use a pre-constructed JSON stub fixture, since the tests cover validation logic not LLM output quality.
- **New Test File**: `template_assistant/tests/test_tone_suggestion_key_validation.py`.
- **Constraint**: Existing tests must not be modified or deleted.

## Assumptions

- The `build_graph` function and `KeyNotInGraphError` exception are already implemented and available for use.
- The active `lang_local` and `param_cust_brand` are available in the context when `suggest_tone_rewrite` is called.
- The LLM is capable of following explicit instructions to only return keys from a provided list.