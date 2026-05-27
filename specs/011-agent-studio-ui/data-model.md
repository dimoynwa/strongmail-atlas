# Data Model: StrongMail Agent Studio

**Feature**: 011-agent-studio-ui
**Date**: 2026-05-27

## Entities

### StreamlitSessionState
Tracks the application state across reruns.
- `runner`: The ADK Runner instance. (Default: None)
- `adk_session`: The ADK Session instance. (Default: None)
- `template_name`: The currently selected template. (Default: None)
- `lang_local`: The currently selected language. (Default: "EN")
- `param_cust_brand`: The currently selected brand. (Default: "SKRILL")
- `session_id`: UUID for the current session. (Default: None)
- `active_tab_index`: The currently active tab index (0 = Template Assistant, 1 = General Agent). (Default: 1)
- `working_copy`: Dict mapping keys to their current values. (Default: {})
- `wc_modified_keys`: Set of keys that have been modified. (Default: `set()`)
- `wc_edit_count`: Number of edits made. (Default: 0)
- `pending_diff`: The latest rewrite suggestions (`PendingDiff` object). (Default: None)
- `tone_stale`: Boolean indicating if the tone evaluation is outdated. (Default: False)
- `tone_scores`: Dict mapping emotion names to scores. (Default: None)
- `tone_stored`: Dict mapping emotion names to stored scores for delta calculation. (Default: None)
- `show_preview`: Boolean indicating if the preview column is visible. (Default: True)
- `messages`: List of message dictionaries (`{"role": str, "content": str, "tool": str?, "diff": dict?}`). (Default: `[]`)

*Note: Streamlit internally manages a `wc_editor` key for the `st.data_editor` widget state. This is Streamlit-owned and must never be initialised or written directly by application code.*

### WorkingCopyRow
Represents a row in the working copy data editor.
- `key` (string): The template content key.
- `value` (string): The current value of the key.
- `modified` (boolean): Indicates if the value has been modified from its original state.

### DiffEntry
Represents a proposed change to a specific key.
- `key` (string): The template content key.
- `old_value` (string): The original value before the proposed change.
- `new_value` (string): The proposed new value.

### PendingDiff
Represents a batch of proposed changes from the AI assistant.
- `entries` (list[DiffEntry]): The list of proposed changes.
- `snapshot_overwritten` (boolean): Indicates if a previous snapshot was overwritten by this suggestion.

### TemplateCard
Represents a template search result from the General Agent.
- `template_name` (string): The name of the template.
- `summary` (string): A brief summary excerpt of the template.
- `distance` (float): The raw cosine distance from the agent response (0 = identical, higher = less similar). The UI progress bar renders `1 - distance`.

### StatusIndicator
Represents the health status of a backend service.
- `name` (string): The name of the service (e.g., PostgreSQL, Redis, GoEmotions).
- `healthy` (boolean): Indicates if the service is operational.
- `error_message` (string, optional): The error message if the service is unhealthy.
