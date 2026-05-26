# Internal Delegation Contracts: Refactor Tone Suggestion Subagent

This document defines the tool contracts used for internal delegation within the `ToneSuggestionSubagent`.

## Tool: `load_eligible_keys`

**Purpose**: Loads eligible keys explicitly, handling DB/Redis unavailability gracefully.

**Parameters**:
- `force_reload` (bool): If True, clears the cache and rebuilds.
- `tool_context` (ToolContext): The ADK tool context.

**Behavior**:
- Reads session context from `tool_context.state`.
- Calls `build_resolution_graph` and `resolve_template`.
- Calls `_build_reachable_eligible` to filter by reachability and content eligibility rules.
- Writes result to `tool_context.state["eligible_keys"]`.
- If `force_reload` is False and `eligible_keys` already in state, returns cached value immediately.

**Returns**:
- On success: `{"eligible_keys": dict, "total": int}`
- On DB/Redis failure: `{"error": str, "message": str}`

## Tool: `finalize_rewrites`

**Purpose**: Called by `SuggestAgent` to emit its JSON rewrites, replacing event scraping.

**Parameters**:
- `rewrites` (list[dict]): List of `{"key": str, "new_value": str}`.
- `tool_context` (ToolContext): The ADK tool context.

**Behavior**:
- Validates each key against `tool_context.state["eligible_keys"]`.
- Discards keys not in `eligible_keys` (hallucinated keys).
- Filters out rewrites where `new_value == current value`.
- Writes to `tool_context.state`:
  - `suggestions`: list of `{key, old_value, new_value, suggestion_id}`
  - `suggestion_id`: str (passed through from state, not regenerated)
- MUST NOT write `tone_bearing_keys` or `structural_keys`.

**Returns**:
- `{"accepted": int, "discarded": int, "suggestions": list}`

## Tool: `suggest_tone_rewrite`

**Purpose**: Modified orchestrator tool to initiate the rewrite process.

**Parameters**:
- `target_intent` (str): The desired tone.
- `tone_bearing_keys` (list[str]): Passed explicitly from the orchestrator (formerly read from state).
- `tool_context` (ToolContext): The ADK tool context.

**Behavior**:
- Reads `tone_bearing_keys` from the parameter.
- Calls `capture_snapshot` BEFORE building the rewrite prompt.
- Does NOT write `suggestions` or `suggestion_id` to state.

**Returns**:
- `{"rewrite_prompt": str, "eligible_keys": dict, "target_emotions": list, "baseline_emotions": list, "suggestion_id": str, "snapshot_saved": bool, "snapshot_overwritten": bool}`

## Tool: `apply_tone_suggestions`

**Purpose**: Modified orchestrator tool to apply confirmed suggestions.

**Parameters**:
- `suggestions` (list[dict]): The confirmed suggestions.
- `tool_context` (ToolContext): The ADK tool context.

**Behavior**:
- Validates `suggestion_id` cross-match before writing (raises `SuggestionIdMismatchError` on mismatch).
- `await`s calls to `get_pool()` and `get_redis()`.
- Does NOT call `capture_snapshot`.

**Returns**:
- `{"applied": int, "message": str}` (Note: `snapshot_overwritten` is removed).

## Tool: `undo_tone_suggestions`

**Purpose**: Modified orchestrator tool to undo applied suggestions.

**Parameters**:
- `keys` (list[str] | None): The keys to undo, or None for full undo.
- `tool_context` (ToolContext): The ADK tool context.

**Behavior**:
- Deletes snapshot Redis hash on full undo (`keys=None`).
- Leaves snapshot on partial undo.

**Returns**:
- `{"restored": int, "message": str, "snapshot_cleared": bool}`