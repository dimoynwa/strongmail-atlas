# Feature Specification: StrongMail Agent Studio

**Feature Branch**: `011-agent-studio-ui`

**Created**: 2026-05-27

**Status**: Draft

**Input**: User description: "Build a Streamlit web application called StrongMail Agent Studio that provides a conversational UI over two existing Google ADK agents..."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Template Discovery and Selection (Priority: P1)

As a template author, I want to search for and discover email templates using a conversational interface so that I can quickly find the right template to work on across different brands and languages.

**Why this priority**: Without the ability to find and select a template, the rest of the application's functionality cannot be accessed.

**Independent Test**: Can be fully tested by interacting with the General Agent to search for templates, viewing the search results, and successfully opening a specific template for editing.

**Acceptance Scenarios**:

1. **Given** I am on the General Agent tab, **When** I ask to find templates related to a specific topic, **Then** I see a list of matching template cards with summaries and similarity scores.
2. **Given** I see a list of template search results, **When** I click "Open" on a template card, **Then** the application switches to the Template Assistant view for that specific template.
3. **Given** I am using the sidebar, **When** I change the language or brand without an active session, **Then** the available templates are updated without any warning prompts.

---

### User Story 2 - AI-Assisted Template Editing (Priority: P1)

As a template author, I want to chat with an AI assistant to query, edit, and improve a specific template, so that I can easily update content and refine the tone without manually editing code.

**Why this priority**: This is the core value proposition of the application, allowing non-technical users to safely modify email templates.

**Independent Test**: Can be fully tested by selecting a template, asking the assistant to rewrite a section, and successfully applying the suggested changes to the working copy.

**Acceptance Scenarios**:

1. **Given** I have a template selected, **When** I ask the assistant to rewrite a paragraph, **Then** I receive a diff card showing the old and new values.
2. **Given** I have received a rewrite suggestion, **When** I choose to "Apply all" or "Apply selected", **Then** the changes are saved to my working copy and reflected in the live preview.
3. **Given** I have unsaved rewrite suggestions, **When** I ask for a new rewrite, **Then** the previous suggestions are replaced and I am warned if my previous snapshot was overwritten.

---

### User Story 3 - Live Preview and Manual Editing (Priority: P2)

As a template author, I want to see a live visual preview of my template and manually edit specific content keys, so that I can verify how my changes look in the final email format.

**Why this priority**: Visual feedback is essential for email design, and manual overrides provide a necessary fallback when AI suggestions aren't perfect.

**Independent Test**: Can be fully tested by manually modifying a value in the working copy table and verifying that the live preview updates immediately with the change highlighted.

**Acceptance Scenarios**:

1. **Given** I am viewing the Template Assistant tab, **When** I toggle the preview visibility, **Then** the live preview panel expands or collapses accordingly.
2. **Given** I have made changes to the template, **When** I view the live preview, **Then** the modified sections are visually highlighted.
3. **Given** I am viewing the working copy table, **When** I manually edit a value, **Then** the change is saved and the live preview updates immediately.

---

### User Story 4 - Tone Evaluation and Management (Priority: P2)

As a template author, I want to evaluate the emotional tone of my template and track how my edits affect it, so that I can ensure the communication aligns with brand guidelines.

**Why this priority**: Tone consistency is a key requirement for enterprise communications, but it's secondary to basic editing capabilities.

**Independent Test**: Can be fully tested by viewing the tone evaluation panel, making an edit to the template, observing the "stale" warning, and successfully re-evaluating the tone.

**Acceptance Scenarios**:

1. **Given** I am viewing a template, **When** I look at the tone evaluation panel, **Then** I see the top 5 emotions displayed with their relative scores.
2. **Given** I have an active tone evaluation, **When** I modify the template content, **Then** the tone panel displays a warning that the evaluation is stale.
3. **Given** I have made tone-related changes, **When** I click "Undo tone", **Then** the most recent AI tone suggestions are reverted.

---

### User Story 5 - Session Management and Safety (Priority: P3)

As a template author, I want my work to be safely isolated in a session and to be warned before taking actions that would discard my progress, so that I don't accidentally lose my edits.

**Why this priority**: Prevents data loss and ensures a smooth user experience, though it's a supporting feature to the core editing workflows.

**Independent Test**: Can be fully tested by making edits to a template, attempting to change the brand or language, and verifying the confirmation guard appears and works correctly.

**Acceptance Scenarios**:

1. **Given** I have an active session with unsaved changes, **When** I attempt to change the language or brand, **Then** I am prompted with a warning to confirm the session reset.
2. **Given** I have an active session, **When** I select a different template from the sidebar, **Then** my session is silently reset and the new template is loaded.
3. **Given** I have made multiple changes, **When** I click "Reset all", **Then** I am asked for confirmation before all my modifications are discarded.

### Edge Cases

- What happens when the user asks the Template Assistant a question unrelated to the current template?
- How does the system handle concurrent edits if multiple users try to modify the same template/brand/language combination?
- What happens if the AI suggests a rewrite for a key that no longer exists or is not eligible for tone changes?
- How does the system behave if the underlying backend services (database, cache, emotion classifier) become unavailable during an active session?
- What happens if the user closes the browser tab while having unapplied rewrite suggestions?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a persistent sidebar for global navigation, including language selection, brand selection, and template search/selection.
- **FR-002**: System MUST display the health status of critical backend services in the sidebar.
- **FR-003**: System MUST provide a "General Agent" conversational interface for searching and discovering templates.
- **FR-004**: System MUST display template search results as actionable cards containing a summary, similarity score, and a mechanism to open the template.
- **FR-005**: System MUST provide a "Template Assistant" conversational interface scoped to the currently selected template.
- **FR-006**: System MUST present AI-suggested rewrites in a structured format showing the original and proposed text, allowing the user to apply all, apply specific parts, or discard the suggestions.
- **FR-007**: System MUST provide a live, visually rendered preview of the selected template.
- **FR-008**: System MUST visually highlight modified content within the live preview.
- **FR-009**: System MUST provide a tabular view of the template's editable content (working copy) that allows for manual, inline modifications.
- **FR-010**: System MUST provide a tone evaluation panel displaying the top emotional characteristics of the current template text.
- **FR-011**: System MUST flag the tone evaluation as stale whenever the template content is modified, requiring explicit re-evaluation.
- **FR-012**: System MUST allow users to reset all current session changes or specifically undo the last applied AI tone suggestions.
- **FR-013**: System MUST warn the user and require confirmation before resetting an active session due to a change in global context (language or brand).
- **FR-014**: System MUST provide quick-action prompts (e.g., "Show placeholders", "Compare tone") within the Template Assistant interface to facilitate common tasks.

### Technical Requirements & Constraints

While this specification focuses on user value, the following technical constraints MUST be strictly adhered to during implementation to ensure proper integration with the existing ADK agents:

- **TR-001 (Session Lifecycle)**: The ADK Runner and Session MUST be stored in `st.session_state` and never recreated on rerun. The session state dict injected at template open must contain `template_name`, `lang_local`, `param_cust_brand`, and a `session_id` (a UUID generated in Python via `str(uuid.uuid4())` in `session.py:init_session()`, not from ADK). The session resets on language/brand change (with confirmation) or template change (silently).
- **TR-002 (Working Copy Initialization)**: `init_working_copy()` MUST call `get_eligible_keys(force_reload=True)` via the ADK runner to determine editable keys. The UI MUST NOT reimplement the `is_tone_affecting()` filter or call resolution tools directly, as the `ToneSuggestionSubagent` owns this eligibility logic. If `get_eligible_keys` fails, the UI MUST gracefully catch the exception, display an error message, and leave the working copy empty to prevent cascading failures.
- **TR-003 (Diff Card Interaction)**: The `pending_diff` MUST persist in session state until user action. "Apply all" calls `apply_suggestions(keys=None)`. "Apply selected" calls `apply_suggestions(keys=[...selected...])`. "Discard" clears `pending_diff` without any agent call. If the `suggest_rewrites` response has `snapshot_overwritten=True`, a warning MUST be shown above the diff card. If an `apply_suggestions` call fails, the error MUST be caught and displayed, and `pending_diff` MUST remain intact in session state so the user can retry.
- **TR-004 (Working Copy Table)**: The table edit callback MUST read `st.session_state["wc_editor"]["edited_rows"]`. Because `edited_rows` is a dictionary keyed by the integer row index, the callback MUST map this index back to the actual template key using the dataframe's index or column. The exact code pattern MUST be used:
  ```python
  edited_rows = st.session_state["wc_editor"]["edited_rows"]
  for row_idx, changes in edited_rows.items():
      # Map the integer row index back to the string key name
      key_name = working_copy_df.iloc[row_idx]["key"] 
      if "value" in changes:
          run_sync(runner.set_working_copy_value(key_name, changes["value"]))
  ```
  After writes, it MUST set `tone_stale=True` and call `st.rerun()`.
- **TR-005 (Status Indicators)**: Health checks MUST run once at startup (using `@st.cache_resource`). PostgreSQL checks via `get_pool()` and `SELECT 1`. Redis checks via `get_redis()` and `PING`. GoEmotions checks if `get_classifier()` returns non-None. These display in the sidebar footer as coloured dots (green=ok, red=error). Each check MUST be wrapped in a `try/except` block that catches exceptions and marks the service as unhealthy (red dot) rather than crashing the app.
- **TR-006 (General Agent Navigation)**: The "Open →" flow on a result card MUST set `st.session_state.template_name`, set `st.session_state.active_tab = "Template Assistant"`, call `init_working_copy()` to pre-populate the working copy, and then call `st.rerun()`. Since `st.tabs()` does not support programmatic switching, the implementation MUST use conditional rendering or `st.radio` (styled as hidden tabs) tied to `st.session_state.active_tab` to achieve the programmatic tab switch.
- **TR-007 (UI Layout)**: A CSS injection block MUST be used to enable the three-column independent scroll layout. The application requires Streamlit >= 1.32 to use `st.container(height=N)`. The following verbatim CSS MUST be injected:
  ```html
  <style>
      /* Independent scrolling for layout columns */
      div[data-testid="column"] {
          overflow-y: auto;
          height: 85vh;
      }
      /* Hide scrollbar for cleaner look */
      div[data-testid="column"]::-webkit-scrollbar {
          width: 0px;
      }
  </style>
  ```
- **TR-008 (Async Pattern & Event Consumption)**: `nest_asyncio` MUST be applied once at app startup. A `run_sync(coro)` helper MUST wrap `asyncio.run()` for callbacks. `asyncio.run()` MUST NEVER be called inside `@st.cache_resource` functions. For ADK event consumption, `run_agent_turn()` in `session.py` MUST iterate all events from `runner.run_async()`. It MUST collect intermediate tool-use events to display as captions on the assistant bubble, collect the final `is_final_response()` event, and return its text. The exact collection pattern MUST be used to prevent partial consumption:
  ```python
  async def run_agent_turn(runner, prompt):
      tool_calls = []
      final_text = ""
      async for event in runner.run_async(prompt):
          # Collect intermediate events (pseudo-code depending on ADK event structure)
          if getattr(event, "is_tool_call", lambda: False)():
              tool_calls.append(event.tool_name)
          # Collect final response
          elif getattr(event, "is_final_response", lambda: False)():
              final_text = event.text
      return final_text, tool_calls
  ```

### Key Entities *(include if feature involves data)*

- **Template**: The core communication asset, consisting of multiple content keys, associated with specific languages and brands.
- **Working Copy**: An isolated, session-specific instance of a template's content that tracks modifications before they are permanently saved.
- **Tone Evaluation**: A structured assessment of the emotional characteristics of a template's text.
- **Rewrite Suggestion**: A proposed modification to one or more template content keys generated by the AI assistant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can successfully locate a specific template using the General Agent within 3 conversational turns.
- **SC-002**: Users can apply an AI-suggested tone improvement to a template in under 2 minutes.
- **SC-003**: The live preview updates to reflect manual or AI-driven content changes in under 2 seconds.
- **SC-004**: 100% of destructive session actions (changing brand/language with an active session, resetting all changes) are protected by a confirmation prompt.

## Assumptions

- The underlying AI agents (Template Assistant and General Agent) are already fully functional and expose the necessary interfaces for integration.
- The backend infrastructure (database, cache) is capable of supporting the expected concurrent user load.
- Authentication and authorization are handled outside the scope of this specific UI application, or the application is intended for internal use within a trusted network.
- The provided template HTML is safe to render within the browser environment.
