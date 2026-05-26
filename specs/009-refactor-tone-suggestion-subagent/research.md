# Research & Decisions: Refactor Tone Suggestion Subagent

## Decisions

### 1. Tool-based Suggestion Emission
**Decision**: Replace `after_agent_callback` event scraping with a dedicated `finalize_rewrites` ADK tool.
**Rationale**: Event scraping is an anti-pattern that is sensitive to ADK version changes and fails silently on malformed JSON. A dedicated tool provides a clear contract, allows for input validation, and handles errors gracefully.
**Alternatives considered**: Modifying the callback to handle malformed JSON better (rejected because it remains fragile and undocumented).

### 2. Explicit Eligible Keys Loading
**Decision**: Replace `before_agent_callback` with a `load_eligible_keys` tool called explicitly by the orchestrator.
**Rationale**: Callbacks that perform DB/Redis I/O can fail silently or bubble exceptions up without a clear error path to the user. An explicit tool allows the orchestrator to catch errors and relay them as plain messages.
**Alternatives considered**: Wrapping the callback in a try-except block that writes to session state (rejected because it's less explicit than a tool call).

### 3. Snapshot Lifecycle
**Decision**: Move `capture_snapshot` from `apply_tone_suggestions` to `suggest_tone_rewrite`.
**Rationale**: The snapshot must reflect the state *before* any suggestions are generated, so that applying a second batch doesn't overwrite the snapshot of the original state without warning.
**Alternatives considered**: Keeping it in apply but adding a check (rejected because the snapshot should represent the baseline against which the user is reviewing suggestions).

### 4. Dependency Injection and State Management
**Decision**: Remove module-level mutable state (`_classifier_llm_fn`) and pass `tone_bearing_keys` explicitly as a tool parameter rather than through session state.
**Rationale**: Module-level mutable state causes cross-session test bleeding. Passing turn-scoped data via session state creates implicit dependencies and race conditions. Explicit parameters and standard monkeypatching resolve these issues.
**Alternatives considered**: None. These are standard Python and ADK best practices.

### 5. Error Handling
**Decision**: Introduce `MissingClassificationError` and `SuggestionIdMismatchError` with `to_payload()` methods.
**Rationale**: Provides structured, user-facing error messages when expected state or parameters are missing or mismatched.
**Alternatives considered**: Raising standard `ValueError` (rejected because it doesn't provide a clean payload for the orchestrator to relay).

### 6. FIX-10 Audit: `services.resolve_template` return type
**Finding**: Branch A — wraps shared `ResolutionResult` from `shared/resolution/resolver.py`.

`template_assistant/services.py` imports and returns `ResolutionResult` directly, constructing it
with `resolved_body`, `unresolvable`, and `resolved_keys`. Field names in
`tone_suggestion_subagent.py` already match the shared type (`resolved_body`,
`resolved_keys`). No `ServiceResolutionResult` dataclass is needed and no field renames
are required.