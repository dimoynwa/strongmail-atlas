# Implementation Plan: Refactor Tone Suggestion Orchestrator

**Branch**: `006-refactor-tone-suggestion-orchestrator` | **Date**: 2026-05-26 | **Spec**: [specs/006-refactor-tone-suggestion-orchestrator/spec.md](spec.md)

**Input**: Feature specification from `/specs/006-refactor-tone-suggestion-orchestrator/spec.md`

## Summary

Refactor the `ToneSuggestionSubagent` from a monolithic `LlmAgent` into an orchestrator `LlmAgent` that delegates to four specialist subagents (`KeyClassifierAgent`, `SuggestAgent`, `ApplyAgent`, `UndoAgent`). The core addition is the `KeyClassifierAgent`, which uses a two-stage process (deterministic name heuristics + LLM classification) to filter out structural keys before they reach the rewrite LLM, improving suggestion quality and reducing LLM instruction-adherence degradation.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `google-genai` (ADK), `redis`

**Storage**: Redis (for working copy and snapshots), PostgreSQL (read-only for resolution graph)

**Testing**: `pytest`

**Target Platform**: Linux/Docker

**Project Type**: ADK Agent (Template Assistant)

**Performance Goals**: Minimal latency overhead for the deterministic Stage 1 classification; Stage 2 LLM call should be fast (small prompt, JSON output).

**Constraints**: No changes to `shared/resolution/`, `ResolutionSubagent`, `WorkingCopySubagent`, `ToneEvaluationSubagent`, `TemplateAssistantAgent`, or existing tests. All new agents and the `classify_keys` function must be added to `template_assistant/subagents/tone_suggestion_subagent.py` — not split into new files.

**Scale/Scope**: Targeted refactor of a single subagent module.

## Implementation Details

### CHANGED FILE (only one)
`template_assistant/subagents/tone_suggestion_subagent.py`

### NEW FUNCTIONS (add to existing file)
- `classify_keys(eligible_keys: dict[str, str], session_state: dict) -> dict`
  - **Stage 1**: `_apply_structural_heuristics(key: str) -> bool`
    Module-level helper. Returns True if the key name matches any known structural suffix or substring (case-insensitive). Full lists:
    - Suffixes: `_URL`, `_LINK`, `_HREF`, `_SRC`, `_IMG`, `_IMAGE`, `_LOGO`, `_ICON`, `_COLOR`, `_COLOUR`, `_BG`, `_BACKGROUND`, `_ID`, `_CODE`, `_TAG`, `_TRACK`
    - Substrings: `FOOTER`, `HEADER`, `COPYRIGHT`, `NAV`, `PRIVACY`, `LEGAL`, `COOKIE`, `UNSUBSCRIBE`, `TRACKING`, `PIXEL`, `BEACON`, `VIEWINBROWSER`, `VIEW_IN_BROWSER`
  - **Stage 2**: `_llm_classify_keys(keys: dict[str, str]) -> dict[str, str]`
    Module-level async function. Takes ambiguous keys (those not caught by Stage 1), builds the classification prompt, calls the LLM once, parses the JSON response `[{key, role}]`, and returns a `dict[str, str]` of key → "tone" | "structural". Discards any key the LLM returns that was not in the input — never add or rename keys.
  - `classify_keys` returns the `KeyClassificationResult` dict.

- `set_classifier_llm_fn(fn: Callable | None) -> None`
  Module-level injection point for the Stage 2 LLM call. Follows the same pattern as `set_llm_batch_fn`. Default is `None` (uses production LLM call). Tests set this to a stub before calling `classify_keys`.

- `_classify_keys_tool(tool_context: ToolContext) -> dict`
  ADK tool wrapper for `classify_keys`. Reads `eligible_keys` from `tool_context.state`. Writes `tone_bearing_keys` and `structural_keys` to `tool_context.state` after `classify_keys` returns.

- `_suggest_tone_rewrites_tool(target_intent: str, tool_context: ToolContext) -> dict`
  ADK tool wrapper for `suggest_tone_rewrites` (already exists). MUST read `tone_bearing_keys` from `session.state` rather than `eligible_keys` directly.

- `_apply_tone_suggestions_tool`
  Already exists. MUST read `suggestion_id` from `session.state`. If `session.state["suggestion_id"]` is absent or does not match the pending batch, return an error dict — do not proceed. The snapshot-before-write ordering is a hard ordering constraint: the snapshot MUST fully complete before any call to `set_working_copy_value()`. The return payload MUST include `snapshot_overwritten: bool`.

- `_undo_tone_suggestions_tool`
  Already exists — no changes needed.

### NEW AGENT DEFINITIONS (add to existing file)
- `KeyClassifierAgent = LlmAgent(name="KeyClassifierAgent", tools=[_classify_keys_tool])`
- `SuggestAgent = LlmAgent(name="SuggestAgent", tools=[_suggest_tone_rewrites_tool])`
- `ApplyAgent = LlmAgent(name="ApplyAgent", tools=[_apply_tone_suggestions_tool])`
- `UndoAgent = LlmAgent(name="UndoAgent", tools=[_undo_tone_suggestions_tool])`

### REFACTORED AGENT
- `ToneSuggestionSubagent = LlmAgent(name="ToneSuggestionSubagent", sub_agents=[KeyClassifierAgent, SuggestAgent, ApplyAgent, UndoAgent], tools=[])`
  The description string MUST be identical to the current implementation. `TemplateAssistantAgent` uses the description for routing — changing it breaks routing at the root level.

## Testing Strategy

### New test file: `template_assistant/tests/test_key_classifier.py`
- `test_stage1_structural_suffix`: key with `_URL` suffix → structural
- `test_stage1_structural_substring`: key with `FOOTER` substring → structural
- `test_stage1_tone_bearing`: key `EN.PARAGRAPH_1` with prose value → not caught by Stage 1, passes to Stage 2
- `test_stage2_llm_classification`: mock `_llm_classify_keys` to return `[{"key": "EN.PARAGRAPH_1", "role": "tone"}]` — verify result in `tone_bearing`
- `test_stage2_hallucinated_key_discarded`: LLM returns a key not in input — verify it is absent from both `tone_bearing` and `structural`
- `test_stage2_fallback_on_failure`: stub `_llm_classify_keys` to raise an exception, verify all Stage 2 input keys appear in `tone_bearing` and a warning is logged
- `test_classify_keys_empty_input`: empty `eligible_keys` → empty result, no LLM call
- `test_classify_keys_all_structural`: all keys caught by Stage 1 → no LLM call, `tone_bearing` is empty
- `test_state_keys_written`: after `_classify_keys_tool`, `session.state` contains `tone_bearing_keys` and `structural_keys`

### Updated test file: `template_assistant/tests/test_tone_suggestion_subagent.py`
- `test_suggest_reads_tone_bearing_keys`: verify `suggest_tone_rewrites` reads `tone_bearing_keys` from `session.state`, not `eligible_keys`
- `test_apply_refuses_without_suggestion_id`: `apply_tone_suggestions` returns error when `suggestion_id` absent from `session.state`
- `test_e2e_full_flow`: classify → suggest → apply → undo using real PostgreSQL and Redis, confirm only tone-bearing keys reach the LLM prompt
- `test_e2e_structural_keys_excluded`: end-to-end with real DB/Redis. The test MUST assert that no key in the returned suggestions has a name matching any suffix or substring from the Stage 1 heuristic lists. This assertion holds regardless of the specific keys present in the test template, making the test robust to template content changes.

All existing tests must continue to pass unchanged.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Library-First**: N/A (This is a targeted refactor within an existing agent module).
- **Test-First**: Pass. Explicit testing strategy defined in the spec, including new unit tests for the classifier and updated E2E tests.
- **Simplicity**: Pass. The refactor simplifies the monolithic LLM prompt by delegating responsibilities to specialized agents, aligning with ADK best practices.

## Project Structure

### Documentation (this feature)

```text
specs/006-refactor-tone-suggestion-orchestrator/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (generated later)
```

### Source Code (repository root)

```text
template_assistant/
├── subagents/
│   └── tone_suggestion_subagent.py  # ONLY file to be modified
└── tests/
    ├── test_key_classifier.py       # NEW file
    └── test_tone_suggestion_subagent.py # UPDATED file
```

**Structure Decision**: The refactor is strictly confined to `template_assistant/subagents/tone_suggestion_subagent.py` and its associated test files, per the boundary constraints in the spec.

## Complexity Tracking

No constitution violations detected. The refactor reduces complexity in the LLM prompt by introducing structural complexity (more subagents), which is a justified trade-off for improved LLM adherence.