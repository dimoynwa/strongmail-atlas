# Tasks: StrongMail Agent Studio

**Input**: Design documents from `/specs/011-agent-studio-ui/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `app/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project structure (`app/components/`) and empty files per implementation plan (including `app/ml.py`)
- [X] T002 [P] Create `.streamlit/config.toml` with sidebar width (220px) and a dark or neutral theme consistent with a professional internal tool
- [X] T003 [P] Add `streamlit>=1.32.0`, `pandas`, `nest_asyncio` to `requirements.txt` (or equivalent dependency file)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Implement `run_sync()` module-level helper with `nest_asyncio.apply()` in `app/session.py`
- [X] T005 Implement `init_session()` to generate `session_id = str(uuid.uuid4())` (stored in both `st.session_state.session_id` and the ADK session state dict) and setup ADK runner/session in `app/session.py`. Store runner in `st.session_state["runner"]` and ADK session in `st.session_state["adk_session"]`. Check for their existence before creating — never recreate on rerun.
- [X] T006 Implement `run_agent_turn(query: str) -> tuple[str, str | None]` in `app/session.py`. Use `async for event in runner.run_async(user_id=..., session_id=..., new_message=query)`. When `event.is_final_response()` is True, capture `event.content.parts[0].text` as the response. For tool caption extraction from intermediate events, use: `next((p.function_call.name for p in (event.content.parts or []) if hasattr(p, "function_call") and p.function_call), None)` — check for `function_call` attribute existence before accessing `.name`, never assume `parts[0]` is a function call part. Return `(response_text, tool_name_or_none)`. Never `await` the generator directly.
- [X] T007 Implement `init_working_copy()` sequence with error handling in `app/session.py`. Step 1: send init message to trigger `get_eligible_keys(force_reload=True)` via runner — exact message string: `"System: call get_eligible_keys with force_reload=True. Respond with only a JSON object mapping key names to their current values, no other text."` Step 2: parse `eligible_keys` dict from response JSON. On parse error or `{"error": ...}` response, set `working_copy={}`, surface `st.error("Could not load editable keys: {message}")`, and return early. Step 3: send init message to trigger `get_working_copy` via runner — exact message string: `"System: call get_working_copy. Respond with only a JSON object with an 'overrides' array, no other text."` Step 4: parse Redis overrides from response JSON. Step 5: merge and set `st.session_state.working_copy`, `wc_modified_keys = set(override keys)`, `wc_edit_count = len(overrides)`, `ta_messages = []`, `tone_stale = False`. These exact message strings must be used — JSON parsing in steps 2 and 4 depends on the agent returning clean JSON.
- [X] T008 Implement `reset_session()` helper in `app/session.py`. Clears `runner`, `adk_session`, `session_id`, `template_name`, `working_copy`, `wc_modified_keys`, `wc_edit_count`, `ta_messages`, `pending_diff`, `tone_scores`, `tone_stale` from `st.session_state`.
- [X] T009 [P] Setup main `app/app.py` entry point with `nest_asyncio.apply()` at the top (before any Streamlit rendering), CSS injection block (exact selectors: `[data-testid="column"] > div:first-child { overflow-y: auto; max-height: 82vh; }`, `[data-testid="stSidebar"] { min-width: 220px; max-width: 220px; }`, `.block-container { padding-top: 1rem; }`), and tab navigation using `st.radio(["Template Assistant", "General Agent"], horizontal=True, key="active_tab_index")`. **This is the required approach** — `st.radio()` is used (not `st.tabs()`) because the "Open →" flow (T015) must programmatically switch tabs via `st.session_state.active_tab_index`, which `st.tabs()` does not support. Renders Template Assistant content when `active_tab_index == 0`, General Agent content when `active_tab_index == 1`.
- [X] T010 Implement `render_sidebar()` skeleton in `app/components/sidebar.py` with status indicators that test all three health checks (PostgreSQL, Redis, GoEmotions) with a real connection. Health checks run once at startup via `@st.cache_resource`. Each check must be wrapped in `try/except Exception as e` — set `healthy=False, error_message=str(e)` on any exception, never let a health check crash the app. PostgreSQL: call `get_pool()` then run `SELECT 1`. Redis: call `get_redis()` then run `PING`. GoEmotions: check `get_classifier() is not None`. These checks use `asyncio.run()` directly at `@st.cache_resource` call time — do NOT use `run_sync()` here, as `run_sync()` is for Streamlit callbacks only.
- [X] T011 Integration test for `init_working_copy` and session state initialization in `tests/integration/test_session.py` (Validation checkpoint — must pass before Phase 3 begins)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Template Discovery and Selection (Priority: P1) 🎯 MVP

**Goal**: Search for and discover email templates using the General Agent, and open a specific template.

**Independent Test**: Can interact with the General Agent to search for templates, view search results, and successfully open a specific template which switches the tab and initializes the working copy.

### Implementation for User Story 1

- [X] T012 [P] [US1] Create `app/components/chat.py` with a `render_chat(agent_key: str)` stub — signature, docstring, and `st.chat_input()` skeleton only. No message loop. Initialise separate message list keys: `st.session_state.setdefault("ta_messages", [])` for the Template Assistant and `st.session_state.setdefault("ga_messages", [])` for the General Agent. The `render_chat(agent_key)` function reads from `st.session_state[f"{agent_key}_messages"]` — never from a shared `messages` key. This prevents Template Assistant and General Agent conversation histories from mixing when the user switches tabs.
- [X] T013 [US1] Implement template list (radio buttons) with silent session reset in `app/components/sidebar.py`. On template change: call `reset_session()` silently (no confirmation), then call `init_session()` and `init_working_copy()` for the new template.
- [X] T014 [US1] Implement language and brand selectors with session reset confirmation in `app/components/sidebar.py`. Populate options from DB at startup via `@st.cache_resource`. Confirmation guard condition: show `st.warning()` if and only if `st.session_state.get("session_id") is not None` AND `st.session_state.get("wc_edit_count", 0) > 0`. If no active session, change silently with no confirmation.
- [X] T015 [US1] Implement `TemplateCard` rendering and the "Open →" 4-step callback in `app/components/chat.py` (co-located with General Agent chat rendering). **Dependency:** Must be implemented after T013 to avoid session state conflicts on `template_name`. The "Open →" callback executes exactly these steps in order: (1) `st.session_state.template_name = result.template_name`, (2) `st.session_state.active_tab_index = 0`, (3) call `init_working_copy()`, (4) call `st.rerun()`.

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - AI-Assisted Template Editing (Priority: P1)

**Goal**: Chat with the Template Assistant to query, edit, and improve a specific template, applying suggested changes to the working copy.

**Independent Test**: Can select a template, ask the assistant to rewrite a section, and successfully apply the suggested changes to the working copy.

### Implementation for User Story 2

- [X] T016 [P] [US2] Complete `render_chat(agent_key: str)` in `app/components/chat.py` (extending the T012 stub) — implement full message loop reading `st.session_state[f"{agent_key}_messages"]`, `st.chat_message()` rendering for each message, `st.caption()` for tool name when present, and diff card rendering call when `msg.get("diff")` is set. On `st.chat_input()` submit: call `run_agent_turn(query)` via `run_sync()`, append user and assistant messages to the appropriate `{agent_key}_messages` list, parse the response for a JSON diff payload and store as `st.session_state.pending_diff` if present, then `st.rerun()`.
- [X] T017 [US2] Implement tool caption extraction and display on assistant bubbles in `app/components/chat.py`. Tool name comes from the second element of the `run_agent_turn()` return tuple. Store as `msg["tool"]` in the messages list. Render as `st.caption(f"⚙ {msg['tool']}")` inside the `st.chat_message("assistant")` block, before `st.write(msg["content"])`.
- [X] T018a [US2] Define `PendingDiff` dataclass in `app/models.py`: `entries: list[DiffEntry]` and `snapshot_overwritten: bool`. `DiffEntry` fields: `key: str`, `old_value: str`, `new_value: str`. `st.session_state.pending_diff` is typed `PendingDiff | None`. Populate by parsing the `suggest_rewrites` JSON response — read `snapshot_overwritten` field from the response dict before constructing the `PendingDiff`.
- [X] T018 [US2] Implement `render_diff_card(diff: PendingDiff)` as a standalone function in `app/components/chat.py`. **Dependency:** Requires T018a (`PendingDiff` dataclass). If `diff.snapshot_overwritten` is True, render `st.warning("Note: applying these suggestions will replace the undo snapshot from your previous suggestion batch.")` above the card. Render each `DiffEntry` as old value (red strikethrough) → new value (green) using `st.markdown(unsafe_allow_html=True)`. Three buttons: **Apply all** calls `apply_suggestions(keys=None)` via runner then clears `pending_diff`; **Apply selected** expands `st.multiselect()` then calls `apply_suggestions(keys=[...selected...])` via runner then clears `pending_diff`; **Discard** clears `pending_diff` without any agent call. After any apply: set `tone_stale=True`, update `wc_edit_count`, call `st.rerun()`. Test cases must cover: all applied, subset applied, all discarded, `snapshot_overwritten=True` warning shown.
- [X] T019 [US2] Implement "Apply all", "Apply selected", and "Discard" button callbacks as named functions in `app/components/chat.py` (called by T018's button handlers). Keep callbacks separate from rendering logic so they can be tested independently.
- [X] T020 [US2] Implement quick-action chips row in `app/components/chat.py`. Chips: `["Show placeholders", "Full preview", "Compare tone", "Reset all changes", "What changed?"]`. Each chip calls `run_agent_turn(label)` via `run_sync()` and appends to `ta_messages` — same code path as a typed chat message.

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Live Preview and Manual Editing (Priority: P2)

**Goal**: See a live visual preview of the template and manually edit specific content keys.

**Independent Test**: Can manually modify a value in the working copy table and verify that the live preview updates immediately with the change highlighted.

### Implementation for User Story 3

- [X] T021 [P] [US3] Implement `render_preview()` with HTML resolution, highlight injection, and dynamic height formula in `app/components/preview.py`. Call `run_agent_turn("System: call resolve_full_template and return only the resolved_html string, no other text.")` via `run_sync()` to get HTML. For highlight injection: iterate `st.session_state.wc_modified_keys`, look up each key's resolved value in `st.session_state.working_copy`, and inject `str.replace(value, f'<span style="border-left:2px solid #22c55e;padding-left:6px;color:#166534">{value}</span>', count=1)` — `count=1` replaces only the first occurrence; document this limitation in a comment. Render via `st.components.v1.html(html, height=max(400, min(800, len(html) // 8)), scrolling=True)`.
- [X] T022 [P] [US3] Implement "Show preview" toggle logic in `app/app.py`. Use `st.session_state.setdefault("show_preview", True)` and a `st.toggle("Show preview")` in the Template Assistant header. When False, render `col1` at full width instead of the three-column split.
- [X] T023 [US3] Implement `render_wc_table()` using `st.data_editor` in `app/components/working_copy.py`. Build DataFrame from `st.session_state.working_copy`. Column config: `key` column disabled, `value` column editable. `hide_index=True`, `use_container_width=True`, `key="wc_editor"`. Render the table before wiring the edit callback — `on_change` is set as a parameter to `st.data_editor`, pointing to the `on_wc_edit` function defined in T024.
- [X] T024 [US3] Implement `on_wc_edit` callback in `app/components/working_copy.py`. Read changed rows from `st.session_state["wc_editor"]["edited_rows"]` — this is a dict of `{row_index: {"value": new_value}}`. Map row index to key name via: `keys = list(st.session_state.working_copy.keys()); key_name = keys[row_idx]`. Do NOT use the `"key"` column value from `edited_rows` — the `key` column is disabled in `st.data_editor` and will not appear in `edited_rows`. For each changed row: call `run_agent_turn(f"System: call set_working_copy_value with key={key_name} value={new_value}")` via `run_sync()`, update `st.session_state.working_copy[key_name]`, add to `wc_modified_keys`, increment `wc_edit_count`, set `tone_stale=True`. Call `st.rerun()` after all writes.
- [X] T025 [US3] Implement "Reset all" footer button with `st.warning()` confirmation in `app/components/working_copy.py`. On confirm: call `run_agent_turn("System: call reset_working_copy")` via `run_sync()`, then clear `working_copy`, `wc_modified_keys`, set `wc_edit_count=0`, `tone_stale=False`, call `st.rerun()`.

**Checkpoint**: All user stories 1-3 should now be independently functional

---

## Phase 6: User Story 4 - Tone Evaluation and Management (Priority: P2)

**Goal**: Evaluate the emotional tone of the template and track how edits affect it.

**Independent Test**: Can view the tone evaluation panel, make an edit to the template, observe the "stale" warning, and successfully re-evaluate the tone.

### Implementation for User Story 4

- [X] T026 [P] [US4] Implement GoEmotions and encoder `@st.cache_resource` wrappers in `app/ml.py`. `load_classifier()` wraps `from template_assistant.ml.goemotions import get_classifier; return get_classifier()`. `load_encoder()` wraps `from general_agent.ml.embeddings import get_encoder; return get_encoder()`. Both use `@st.cache_resource` to ensure models are loaded only once across all sessions. Never call `run_sync()` inside these functions — they are synchronous cache loaders.
- [X] T027 [US4] Implement `render_tone_bars()` with emotion progress bars and delta calculation in `app/components/tone_panel.py`. Read `st.session_state.tone_scores` (current) and `st.session_state.tone_stored` (historical baseline). For top 5 emotions sorted by score descending: render `st.progress(score, text=f"{label}  {score:.2f}")` with delta caption `f"{'▲' if delta > 0 else '▼'}{abs(delta):.2f}"` where `delta = score - tone_stored.get(label, score)`.
- [X] T028 [US4] Implement stale indicator logic tied to `st.session_state.tone_stale` in `app/components/tone_panel.py`. When `tone_stale` is True, render `st.warning("Scores may be outdated — working copy has changed")` above the bars. `tone_stale` is set True by: any `set_working_copy_value` call, any `apply_suggestions` call, any `reset_working_copy` call. It is set False only after `evaluate_tone` completes and `tone_scores` is updated.
- [X] T029 [US4] Implement "Re-evaluate tone" button callback in `app/components/tone_panel.py`. On click: call `run_agent_turn("System: call evaluate_tone and return only the emotions JSON object, no other text.")` via `run_sync()`, parse response JSON into `st.session_state.tone_scores`, set `tone_stale=False`, call `st.rerun()`.
- [X] T030 [US4] Implement "Undo tone" footer button callback in `app/components/working_copy.py`. On click (no confirmation required — undo is non-destructive): call `run_agent_turn("System: call undo_suggestions")` via `run_sync()`, refresh `working_copy` from Redis by calling `run_agent_turn("System: call get_working_copy and return only the JSON object")` and re-parsing, recompute `wc_modified_keys` and `wc_edit_count`, set `tone_stale=True`, call `st.rerun()`.

**Checkpoint**: All user stories 1-4 should now be independently functional

---

## Phase 7: User Story 5 - Session Management and Safety (Priority: P3)

**Goal**: Ensure work is safely isolated and warn before destructive actions.

**Independent Test**: Can attempt to change brand/language with unsaved changes and verify the confirmation guard appears.

### Implementation for User Story 5

- [X] T031 [US5] Refine language/brand selector callbacks in `app/components/sidebar.py` to include the confirmation guard. Show `st.warning()` confirmation if and only if `st.session_state.get("session_id") is not None` AND `st.session_state.get("wc_edit_count", 0) > 0`. "Unsaved changes" in this context means `wc_edit_count > 0` — all changes are already persisted to Redis, but the working copy session would be discarded on reset. If no active session (`session_id is None`), change lang/brand silently with no confirmation.
- [X] T032 [US5] Ensure template change silently calls `reset_session()` in `app/components/sidebar.py`. No `st.warning()` confirmation. Immediately follow with `init_session()` and `init_working_copy()` for the new template.

**Checkpoint**: All user stories should now be independently functional

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T033 [P] Verify all ADK runner calls are properly wrapped in `run_sync()` by running `grep -rn "asyncio.run\|runner.run_async" app/ | grep -v "run_sync\|run_agent_turn"` (expected result: 0 matches)
- [X] T034 [P] Verify UI never writes directly to Redis/PostgreSQL (strict write boundary) by running `grep -rn "redis\|asyncpg\|get_pool\|get_redis" app/ | grep -v "session.py\|ml.py\|health"` (expected result: 0 matches outside allowed files)
- [X] T035 Run end-to-end smoke test covering: select template → working copy populated → send chat message → apply tone suggestion → verify working copy updated → undo suggestion → verify working copy restored

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - User stories can proceed sequentially in priority order (US1 → US2 → US3 → US4 → US5)
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, US1 and US2 can start in parallel (if team capacity allows)
- UI components (`preview.py`, `tone_panel.py`) can be developed in parallel with core chat logic

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Add User Story 5 → Test independently → Deploy/Demo