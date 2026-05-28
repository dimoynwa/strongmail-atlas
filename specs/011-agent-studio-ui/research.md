# Research: StrongMail Agent Studio

**Feature**: 011-agent-studio-ui
**Date**: 2026-05-27

## Technical Context Unknowns

The user provided a very detailed specification that resolved most technical unknowns. The following decisions are based on the user's explicit instructions:

### ADK Event Generator Consumption Pattern
- **Decision**: `run_agent_turn()` in `session.py` will iterate all events from `runner.run_async()`, collect intermediate tool-use events for captions, collect the final `is_final_response()` event, and return its text.
- **Rationale**: ADK's `runner.run_async()` is an async generator that yields events, not a single response. A partial consumer would miss events or fail to capture the final response.
- **Alternatives considered**: None. This is the required pattern for consuming ADK events.

### Working Copy Initialization
- **Decision**: `init_working_copy()` will call `get_eligible_keys(force_reload=True)` via the ADK runner (e.g., by sending a special prompt `__init_eligible_keys__` or calling the tool directly if supported). It will then parse the eligible keys, run `get_working_copy` to get existing Redis overrides, and merge them into `st.session_state.working_copy`.
- **Rationale**: The UI must not reimplement the `is_tone_affecting()` filter. The `ToneSuggestionSubagent` owns this eligibility logic.
- **Alternatives considered**: Reimplementing the filter in the UI (rejected because it duplicates logic and risks drift).

### Streamlit Tabs Programmatic Switch
- **Decision**: Use conditional rendering or `st.radio` (styled as hidden tabs) tied to `st.session_state.active_tab` to achieve programmatic tab switching.
- **Rationale**: `st.tabs()` does not support programmatic switching natively in Streamlit.
- **Alternatives considered**: Native `st.tabs()` (rejected due to lack of programmatic control).

### CSS Injection for Layout
- **Decision**: Inject a specific CSS block to enable independent scrolling for layout columns (`overflow-y: auto; height: 85vh;`).
- **Rationale**: Required to achieve the specified three-column layout with independent scrolling.
- **Alternatives considered**: None. Streamlit's native layout options do not support this specific requirement without custom CSS.
