# Internal Delegation Contract: ToneSuggestionSubagent

This contract defines the strict rules of engagement between the `ToneSuggestionSubagent` (orchestrator) and its four specialist subagents.

## 1. Pre-Delegation Setup
- The orchestrator MUST call `_build_reachable_eligible()` in Python before any delegation to the subagents.
- The result MUST be written to `session.state["eligible_keys"]`.

## 2. Suggest Flow Sequence
The orchestrator MUST enforce the following sequence for generating and presenting suggestions:
1. **Orchestrator** receives intent.
2. **Orchestrator** delegates to `KeyClassifierAgent`.
   - *Constraint*: `KeyClassifierAgent` MUST always precede `SuggestAgent` in a suggest flow.
3. **Orchestrator** delegates to `SuggestAgent`.
4. **Orchestrator** presents the generated diff to the user.
5. **Orchestrator** WAITS for explicit user confirmation (Human-in-the-loop gate).
6. **Orchestrator** delegates to `ApplyAgent` only after confirmation.

## 3. Apply Constraints
- `ApplyAgent` MUST NEVER be invoked without a valid `suggestion_id` present in `session.state`.
- `ApplyAgent` MUST perform all-or-nothing graph validation before writing to Redis.

## 4. Undo Flow Sequence
- The orchestrator delegates to `UndoAgent` based on user intent.
- *Constraint*: There is NO prerequisite for invoking `UndoAgent`. It can be triggered at any time, regardless of whether `KeyClassifierAgent` or `SuggestAgent` have run in this session. If no snapshot exists, it returns a safe message.