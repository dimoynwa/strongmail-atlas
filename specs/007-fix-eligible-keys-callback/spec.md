# Feature Specification: Populate `eligible_keys` via `before_agent_callback`

**Spec ID**: `007-fix-eligible-keys-callback`
**Branch**: `006-fix-eligible-keys-callback`
**Parent spec**: `006-refactor-tone-suggestion-orchestrator`
**Created**: 2026-05-26
**Status**: Draft

---

## Problem

`ToneSuggestionSubagent` has `tools=[]`. Its orchestrator instruction tells the
LLM to call `_build_reachable_eligible()` as the first step of the suggest flow,
but this is a plain Python function — not an ADK tool. The LLM cannot call it.
`session.state["eligible_keys"]` is never populated, `KeyClassifierAgent` reads
an empty dict, and zero keys reach the rewrite LLM.

The correct fix is to populate `eligible_keys` in a `before_agent_callback` on
`ToneSuggestionSubagent`. This runs automatically before the LLM sees any input,
removes the dependency on LLM instruction-adherence for step ordering, and keeps
`tools=[]` on the orchestrator.

---

## Functional Requirements

**FR-001**: A `before_agent_callback` named `_populate_eligible_keys` MUST be
added to `ToneSuggestionSubagent`. It MUST run before the orchestrator LLM
processes any user input.

**FR-002**: `_populate_eligible_keys` MUST call `validate_session_context`,
`build_resolution_graph`, `resolve_template`, and `_build_reachable_eligible`
in that order, then write the result to `callback_context.state["eligible_keys"]`.

**FR-003**: `_populate_eligible_keys` MUST return `None` in all non-error paths.
It MUST NOT short-circuit the agent by returning a `Content` object.

**FR-004**: If `session.state["eligible_keys"]` is already populated and
non-empty, `_populate_eligible_keys` MUST skip all DB and Redis calls and return
`None` immediately. This guard prevents redundant round trips on follow-up turns
(apply, undo, second suggestion request).

**FR-005**: If `validate_session_context` raises `SessionContextMissingError`,
the exception MUST propagate naturally. No special handling is required in the
callback — ADK surfaces this to the caller.

**FR-006**: The ineligible keys returned by `_build_reachable_eligible` are
discarded in the callback. They are not written to `session.state` and are not
needed downstream.

**FR-007**: `suggest_tone_rewrite` and `suggest_tone_rewrites` MUST NOT fall
back to calling `_build_reachable_eligible` when `tone_bearing_keys` is absent
from `session_state`. The existing `else` fallback branch in both functions MUST
be replaced with a hard error return:

```python
if "tone_bearing_keys" not in session_state:
    return {
        "error": "missing_tone_bearing_keys",
        "message": "KeyClassifierAgent must run before SuggestAgent.",
    }
eligible = dict(session_state["tone_bearing_keys"])
```

This ensures the classifier is never bypassed silently.

**FR-008**: The orchestrator instruction MUST be updated to remove the step
that tells the LLM to build `eligible_keys`. The new step 1 of the suggest
flow MUST read:

```
1. Delegate to KeyClassifierAgent. eligible_keys is already populated in
   session.state before this instruction runs.
```

---

## Data Model

No new session state keys are introduced. This fix populates an existing key:

| Key | Type | Writer | Reader |
|---|---|---|---|
| `eligible_keys` | `dict[str, str]` | `_populate_eligible_keys` callback | `KeyClassifierAgent` |

The writer changes from "orchestrator LLM tool call" to "before_agent_callback".
The reader and the key name are unchanged.

---

## Constraints & Boundaries

- **One file only**: `template_assistant/subagents/tone_suggestion_subagent.py`.
- **No changes to subagents**: `KeyClassifierAgent`, `SuggestAgent`, `ApplyAgent`,
  and `UndoAgent` are unchanged.
- **No changes to tools**: `_classify_keys_tool`, `_suggest_tone_rewrites_tool`,
  `_apply_tone_suggestions_tool`, `_undo_tone_suggestions_tool` are unchanged
  except the fallback removal in FR-007 which touches `suggest_tone_rewrite` and
  `suggest_tone_rewrites`.
- **`tools=[]` stays**: `ToneSuggestionSubagent` MUST keep `tools=[]`. The
  callback replaces the need for a tool on the orchestrator.
- **No changes to** `shared/resolution/`, `TemplateAssistantAgent`,
  `ResolutionSubagent`, `WorkingCopySubagent`, `ToneEvaluationSubagent`,
  or any existing test file.

---

## Imports Required

Add to existing imports in `tone_suggestion_subagent.py`:

```python
from google.adk.agents.callback_context import CallbackContext
from google.genai.types import Content
```

---

## Implementation

```python
async def _populate_eligible_keys(
    callback_context: CallbackContext,
) -> Content | None:
    """Populate session.state eligible_keys before the orchestrator LLM runs.

    Skips all DB and Redis calls if eligible_keys is already present and
    non-empty — prevents redundant round trips on follow-up turns.
    Returns None always; never short-circuits the agent.
    """
    state = callback_context.state.to_dict()
    if state.get("eligible_keys"):
        return None
    session_context = validate_session_context(state)
    pool = get_pool()
    graph = await build_resolution_graph(pool, session_context.template_name)
    resolution = await resolve_template(session_context)
    eligible, _ = await _build_reachable_eligible(
        graph, resolution, session_context, state
    )
    callback_context.state["eligible_keys"] = eligible
    return None
```

Wire onto `ToneSuggestionSubagent`:

```python
ToneSuggestionSubagent = LlmAgent(
    name="ToneSuggestionSubagent",
    ...
    before_agent_callback=_populate_eligible_keys,
    sub_agents=[KeyClassifierAgent, SuggestAgent, ApplyAgent, UndoAgent],
    tools=[],
)
```

---

## Testing

Add to `template_assistant/tests/test_tone_suggestion_subagent.py`:

**`test_callback_populates_eligible_keys`**
Invoke `_populate_eligible_keys` with a `CallbackContext` whose state contains
valid session context but no `eligible_keys`. Assert that `eligible_keys` is
written to `callback_context.state` and is a non-empty dict. Uses real
PostgreSQL and Redis.

**`test_callback_skips_if_already_populated`**
Invoke `_populate_eligible_keys` with `eligible_keys` already present and
non-empty in state. Mock `build_resolution_graph` and assert it is never called.
Assert `eligible_keys` is unchanged after the callback returns.

**`test_callback_returns_none`**
Invoke `_populate_eligible_keys` in both the skip path and the populate path.
Assert the return value is `None` in both cases.

**`test_suggest_errors_without_tone_bearing_keys`**
Call `suggest_tone_rewrite` with a `session_state` dict that contains
`eligible_keys` but no `tone_bearing_keys`. Assert the return value is a dict
containing `"error": "missing_tone_bearing_keys"` and no `suggestions` key.

All existing tests must pass unchanged.

---

## Success Criteria

**SC-001**: When a user sends "Make this template more admirational", the
orchestrator callback populates `eligible_keys` before the LLM runs,
`KeyClassifierAgent` receives a non-empty dict, and suggestions contain only
tone-bearing keys.

**SC-002**: On a follow-up message ("apply all"), the callback detects
`eligible_keys` already in state and makes no DB or Redis calls.

**SC-003**: `suggest_tone_rewrite` called without prior `KeyClassifierAgent`
execution returns `{"error": "missing_tone_bearing_keys", ...}` rather than
silently falling back to `_build_reachable_eligible`.