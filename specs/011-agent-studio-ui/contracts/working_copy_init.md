# Working Copy Init Sequence

**Feature**: 011-agent-studio-ui
**Date**: 2026-05-27

This contract defines the exact sequence of operations required to initialize the working copy for a selected template. It ensures that the UI relies on the ADK agents for business logic (like tone eligibility) and data retrieval.

## Sequence

1. **Create ADK Session**: Initialize a new ADK `InMemorySession` with a state dictionary containing `template_name`, `lang_local`, `param_cust_brand`, and a newly generated `session_id` (UUID).
2. **Fetch Eligible Keys**:
   - Call `run_agent_turn("__init_eligible_keys__")` to trigger the `get_eligible_keys(force_reload=True)` tool call via the ADK runner.
   - *Note: If the ADK supports direct tool invocation via the runner API, that approach is preferred over sending a special text prompt. The implementation must document the chosen approach.*
3. **Parse Eligible Keys**: Extract the list of eligible keys from the response.
4. **Fetch Working Copy Overrides**: Run a `get_working_copy` tool call (via the runner) to retrieve any existing Redis overrides for the current session.
5. **Merge and Populate**: Merge the eligible keys with their current values (including any Redis overrides) and populate `st.session_state.working_copy`.

## Error Handling

- If `get_eligible_keys` fails, the UI MUST gracefully catch the exception, display an error message, and leave the working copy empty to prevent cascading failures.
