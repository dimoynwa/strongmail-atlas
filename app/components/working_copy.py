from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app.session import run_agent_turn


def on_wc_edit() -> None:
    edited_rows = st.session_state.get("wc_editor", {}).get("edited_rows", {})
    if not edited_rows:
        return

    keys = list(st.session_state.working_copy.keys())
    for row_idx, changes in edited_rows.items():
        if "value" not in changes:
            continue
        key_name = keys[int(row_idx)]
        new_value = changes["value"]
        run_agent_turn(
            f"System: call set_working_copy_value with key={key_name} value={new_value}"
        )
        st.session_state.working_copy[key_name] = new_value
        st.session_state.wc_modified_keys.add(key_name)
        st.session_state.wc_edit_count = st.session_state.get("wc_edit_count", 0) + 1
        st.session_state.tone_stale = True

    st.rerun()


def _refresh_working_copy_from_agent() -> None:
    response, _ = run_agent_turn(
        "System: call get_working_copy and return only the JSON object"
    )
    try:
        payload = json.loads(response.strip())
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        overrides = payload if "overrides" not in payload else {
            item["key"]: item["value"]
            for item in payload.get("overrides", [])
            if isinstance(item, dict) and "key" in item
        }
        for key, value in overrides.items():
            st.session_state.working_copy[key] = value
        st.session_state.wc_modified_keys = set(overrides.keys())
        st.session_state.wc_edit_count = len(overrides)


def on_reset_all_confirmed() -> None:
    run_agent_turn("System: call reset_working_copy")
    st.session_state.working_copy = {}
    st.session_state.pop("_wc_init_failed", None)
    st.session_state.wc_modified_keys = set()
    st.session_state.wc_edit_count = 0
    st.session_state.tone_stale = False
    st.rerun()


def on_undo_tone() -> None:
    run_agent_turn("System: call undo_suggestions")
    _refresh_working_copy_from_agent()
    st.session_state.tone_stale = True
    st.rerun()


def render_wc_table() -> None:
    st.subheader("Working copy")
    working_copy = st.session_state.get("working_copy", {})
    if not working_copy:
        st.caption("No editable keys loaded.")
        return

    df = pd.DataFrame(
        [{"key": key, "value": value} for key, value in working_copy.items()]
    )
    st.data_editor(
        df,
        column_config={
            "key": st.column_config.TextColumn("Key", disabled=True),
            "value": st.column_config.TextColumn("Value"),
        },
        hide_index=True,
        use_container_width=True,
        key="wc_editor",
        on_change=on_wc_edit,
    )

    footer_col1, footer_col2 = st.columns(2)
    with footer_col1:
        if st.button("Reset all", key="wc_reset_all"):
            st.session_state._confirm_reset_all = True
    with footer_col2:
        if st.button("Undo tone", key="wc_undo_tone"):
            on_undo_tone()

    if st.session_state.get("_confirm_reset_all"):
        st.warning("Reset all working copy changes?")
        c1, c2 = st.columns(2)
        if c1.button("Confirm reset", key="wc_reset_confirm"):
            st.session_state.pop("_confirm_reset_all", None)
            on_reset_all_confirmed()
        if c2.button("Cancel", key="wc_reset_cancel"):
            st.session_state.pop("_confirm_reset_all", None)
            st.rerun()
