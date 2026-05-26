# Quickstart: Refactor Tone Suggestion Orchestrator

This feature is a targeted refactor of an existing internal agent component. There are no new CLI commands, API endpoints, or user-facing setup steps required to run it.

## Development Setup

1. Ensure your local development environment is set up according to the main project README (Python 3.11+, Redis, PostgreSQL).
2. Run the test suite to verify the existing baseline before making changes:
   ```bash
   pytest template_assistant/tests/
   ```

## Implementation Steps

The implementation is strictly confined to `template_assistant/subagents/tone_suggestion_subagent.py` and its associated tests.

1. **Implement `classify_keys` and its ADK tool wrapper**:
   - Add the deterministic Stage 1 heuristics (`_apply_structural_heuristics`).
   - Add the LLM-based Stage 2 classification (`_llm_classify_keys`).
   - Create the `_classify_keys_tool` wrapper to manage `session.state`.
2. **Refactor existing tools**:
   - Verify `_suggest_tone_rewrites_tool` reads from `tone_bearing_keys`.
   - Update `_apply_tone_suggestions_tool` to return `snapshot_overwritten` and handle the all-or-nothing validation.
   - Update `_undo_tone_suggestions_tool` to return a message dict instead of raising `NoSnapshotError`.
3. **Define Subagents and Orchestrator**:
   - Define `KeyClassifierAgent`, `SuggestAgent`, `ApplyAgent`, and `UndoAgent` using `LlmAgent`.
   - Redefine `ToneSuggestionSubagent` as an orchestrator with `sub_agents` and no direct tools.
4. **Write and Update Tests**:
   - Create `template_assistant/tests/test_key_classifier.py` and implement the required test cases.
   - Update `template_assistant/tests/test_tone_suggestion_subagent.py` to verify the new data flow and constraints.