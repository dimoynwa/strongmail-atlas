# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build a Streamlit web application called StrongMail Agent Studio that provides a conversational UI over two existing Google ADK agents (Template Assistant and General Agent). The application allows template authors to search for templates, chat with an AI to refine tone and content, view a live HTML preview, and manually edit template keys. It relies heavily on Streamlit's session state and async capabilities to integrate with the headless ADK processes.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: streamlit>=1.32.0, pandas, nest_asyncio, Google ADK

**Storage**: PostgreSQL (template metadata), Redis (working copy state)

**Testing**: pytest, pytest-asyncio (integration tests with real DB/Redis, no mocking)

**Target Platform**: Web Browser (via Streamlit)

**Project Type**: web-app

**Performance Goals**: Live preview updates < 2s

**Constraints**: Must use ADK session lifecycle, strict write boundary (UI never writes directly to DB/Redis), async event generator consumption required.

**Scale/Scope**: Single-page app with persistent sidebar, multiple tabs, live HTML rendering, and data editor.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Passes. No specific constitution rules are violated by this web application design.

## Project Structure

### Documentation (this feature)

```text
specs/011-agent-studio-ui/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
app/
├── app.py                  
├── components/
│   ├── sidebar.py          
│   ├── chat.py             
│   ├── preview.py          
│   ├── working_copy.py     
│   └── tone_panel.py       
├── session.py              
└── .streamlit/
    └── config.toml         
```

**Structure Decision**: The project uses a simple Streamlit application structure with a main entry point (`app.py`), a `components/` directory for modular UI rendering functions, and a `session.py` file for state and ADK integration logic.

## Implementation Details

The following specific implementation patterns MUST be followed to satisfy the technical constraints:

- **ADK Event Generator**: `run_agent_turn(query: str) -> tuple[str, str | None]` in `session.py` MUST iterate all events from `runner.run_async(user_id=..., session_id=..., new_message=query)` using `async for event in runner.run_async(...)`. Collect the final `event.content.parts[0].text` when `event.is_final_response()` is True. Collect the first tool name from any intermediate event where `event.content` contains a function call part — this becomes the tool caption on the assistant bubble. Return `(response_text, tool_name_or_none)`.
- **Working Copy Init Sequence**: `init_working_copy()` in `session.py` MUST:
  1. Call `run_agent_turn("__INIT__: call get_eligible_keys with force_reload=True and return the result as JSON")` — a special system-style message that triggers the tool call via the runner.
  2. Parse the JSON from the response text to get `eligible_keys: dict[str, str]`. On error response, set `st.session_state.working_copy = {}`, display `st.error("Could not load editable keys: {message}")` in the right panel, and continue (don't block session creation).
  3. Call `run_agent_turn("__INIT__: call get_working_copy and return the result as JSON")` to get existing Redis overrides.
  4. Merge: for each key in `eligible_keys`, override value with Redis value if present.
  5. Set `st.session_state.working_copy = merged_dict`, `wc_modified_keys = set(redis_overrides.keys())`, and `wc_edit_count = len(redis_overrides)`.
- **Async Helper**: `run_sync()` MUST be implemented as a module-level helper in `session.py` using `nest_asyncio.apply()` at module load. It must wrap `asyncio.run()` so that callbacks can safely execute async ADK runner methods without creating per-call event loops that crash Streamlit.
- **Session ID**: `session_id = str(uuid.uuid4())` is generated in `init_session()` in `session.py` before the ADK session is created. It is stored in both `st.session_state.session_id` and the ADK session state dict.
- **Working Copy Edits**: The `on_wc_edit` callback in `components/working_copy.py` MUST read `st.session_state["wc_editor"]["edited_rows"]`. It MUST map the integer row indices back to the actual string key names using the current `working_copy` dict ordering (e.g., via `working_copy_df.iloc[row_idx]["key"]`).
- **Diff Card Flow**: The diff card interaction in `components/chat.py` MUST rely on `st.session_state.pending_diff`. The `pending_diff` dict in session state must include a `snapshot_overwritten: bool` field populated by parsing the `suggest_rewrites` JSON response. The diff card renderer reads this field to conditionally show the `st.warning()`. The three button outcomes are:
  1. **Apply all**: Calls `apply_suggestions(keys=None)` via the ADK runner.
  2. **Apply selected**: Calls `apply_suggestions(keys=[...selected...])` via the ADK runner.
  3. **Discard**: Clears `pending_diff` from session state without any agent call.
- **Preview Height**: The live HTML preview in `components/preview.py` MUST use the dynamic height formula: `max(400, min(800, len(html) // 8))`.
- **General Agent Navigation**: The "Open →" button flow on a General Agent result card MUST execute exactly these four steps in order:
  1. Set `st.session_state.template_name` to the selected template.
  2. Set `st.session_state.active_tab_index` to `0` (Template Assistant).
  3. Call `init_working_copy()` to pre-populate the working copy.
  4. Call `st.rerun()` to force the UI to render the new state.
- **Tab Switching**: `st.tabs()` does not support programmatic switching via session state in Streamlit <= 1.40. The workaround is: store `st.session_state.active_tab_index` as an integer (0 = Template Assistant, 1 = General Agent). In `app.py`, render the tab that matches `active_tab_index` by conditionally rendering content, OR use a single `st.tabs()` call and check `st.session_state.active_tab_index` to auto-scroll/focus. Document the chosen approach. If using `st.tabs()`, note that the visual tab selection cannot be forced programmatically — the user will see the correct content but may need to click the tab header themselves. An alternative is to replace `st.tabs()` with `st.radio()` for navigation (fully controllable via session state).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
