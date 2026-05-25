# Research: Tone Suggestion Validation

## Decisions

### 1. Eligibility Filter Implementation
- **Decision**: Implement `is_eligible_for_rewrite` as a standalone helper function in `tone_suggestion_subagent.py`.
- **Rationale**: Keeps the tool function (`suggest_tone_rewrite`) clean and allows for isolated unit testing of the complex filtering logic.
- **Alternatives considered**: Inlining the logic inside the tool function (rejected due to complexity and testability concerns).

### 2. LLM Prompt Constraints
- **Decision**: Explicitly instruct the LLM to only return keys from the provided list and request structured JSON output.
- **Rationale**: Reduces the likelihood of hallucinated keys and ensures the output is easily parsable.
- **Alternatives considered**: Relying on the LLM to infer constraints from the input data (rejected due to unreliability).

### 3. Graph Validation in `apply_tone_suggestions`
- **Decision**: Implement an atomic all-or-nothing check. Validate all keys against the graph before writing any to Redis.
- **Rationale**: Prevents partial writes and ensures the working copy remains consistent.
- **Alternatives considered**: Writing valid keys and skipping invalid ones (rejected as it could lead to an inconsistent state and user confusion).