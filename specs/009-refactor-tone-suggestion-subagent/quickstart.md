# Quickstart: Refactor Tone Suggestion Subagent

This document outlines how to use the refactored `ToneSuggestionSubagent`.

## Overview

The `ToneSuggestionSubagent` has been refactored to eliminate anti-patterns (like event scraping and I/O in callbacks) and improve stability. The core functionality remains the same, but the internal delegation and state management are now more robust.

## Key Changes for Developers

1. **No More Event Scraping**: The `SuggestAgent` now emits its suggestions via the `finalize_rewrites` tool.
2. **Explicit Eligible Keys Loading**: The orchestrator must call the `load_eligible_keys` tool at the start of the suggest flow.
3. **Snapshot Lifecycle**: Snapshots are now captured *before* the rewrite prompt is built in `suggest_tone_rewrite`, not during `apply_tone_suggestions`.
4. **Explicit Dependencies**: `tone_bearing_keys` is passed explicitly from the orchestrator to the `SuggestAgent`'s tool, rather than being read from session state.
5. **Testing**: The module-level mutable `_classifier_llm_fn` has been removed. Use standard `pytest` monkeypatching to mock the classifier LLM in tests.

## Orchestrator Flow

The orchestrator instruction now follows this explicit flow:

1. **Load Eligible Keys**: Call `load_eligible_keys(force_reload=True)`. If it returns an error, relay the message to the user and stop.
2. **Classify Keys**: Delegate to `KeyClassifierAgent`.
3. **Suggest Rewrites**: Pass `tone_bearing_keys` explicitly to `SuggestAgent`'s `_suggest_tone_rewrites_tool`.
4. **Finalize Rewrites**: `SuggestAgent` calls `finalize_rewrites` with its JSON output.
5. **Warn User (if applicable)**: If `suggest_tone_rewrite` returned `snapshot_overwritten: true`, prepend a warning to the diff presentation.
6. **Apply/Undo**: Proceed with apply or undo as requested by the user.

## Error Handling

- **DB/Redis Outages**: Handled gracefully by `load_eligible_keys`, returning a structured error dict.
- **Missing Classification**: Raises `MissingClassificationError` if `SuggestAgent` is called without `tone_bearing_keys`.
- **Suggestion ID Mismatch**: Raises `SuggestionIdMismatchError` if the confirmed suggestions don't match the session state during apply.