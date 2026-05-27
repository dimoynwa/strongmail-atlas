# Data Model: Refactor Tone Suggestion Orchestrator

## Overview

This document defines the data structures and state management contracts for the refactored `ToneSuggestionSubagent` and its specialist subagents.

## Data Structures

### `KeyClassificationResult`

A dictionary (or TypedDict/dataclass) representing the return schema of the `classify_keys` tool.

```python
{
    "tone_bearing": dict[str, str],       # Keys classified as tone-bearing prose
    "structural": dict[str, str],         # Keys classified as structural chrome
    "stage1_structural_count": int,       # Number of keys caught by deterministic heuristics
    "stage2_structural_count": int,       # Number of keys caught by the LLM
    "tone_bearing_count": int             # Number of keys classified as tone-bearing (len(tone_bearing))
}
```

### `ApplyToneSuggestionsResult`

A dictionary representing the return schema of the `apply_tone_suggestions` tool.

```python
{
    "applied_keys": list[str],
    "skipped_keys": list[str],
    "total_applied": int,
    "working_copy_updated": bool,
    "snapshot_overwritten": bool,  # True if a prior snapshot was replaced
}
```

## Session State Key Inventory

The following keys in `session.state` form the strict data flow contract between the orchestrator and its subagents.

| Key | Type | Writer | Reader | Description |
|-----|------|--------|--------|-------------|
| `eligible_keys` | `dict[str, str]` | Orchestrator (`_build_reachable_eligible()`) | `KeyClassifierAgent` | The initial set of structurally eligible keys reachable in the template graph. |
| `tone_bearing_keys` | `dict[str, str]` | `KeyClassifierAgent` | `SuggestAgent` | The filtered subset of keys containing actual tone-bearing prose. |
| `structural_keys` | `dict[str, str]` | `KeyClassifierAgent` | Orchestrator (report only) | The filtered subset of structural keys (URLs, boilerplate, etc.). Never sent to the rewrite LLM. |
| `suggestions` | `list[dict]` | `SuggestAgent` | `ApplyAgent` | The generated tone rewrites. Each dict contains `key`, `old_value`, and `new_value`. |
| `suggestion_id` | `str` (UUID) | `SuggestAgent` | `ApplyAgent` | A unique identifier for the suggestion batch, used to enforce the confirmation gate. |

*Rule: A reader MUST NEVER be implemented before its writer.*