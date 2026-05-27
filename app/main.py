from __future__ import annotations

import os

os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import streamlit as st

import torchvision  # noqa: F401 — load before transformers vision submodules are inspected

from app.components.chat import render_chat, render_quick_action_chips
from app.components.preview import render_preview
from app.components.sidebar import render_sidebar
from app.components.tone_panel import render_tone_panel
from app.components.working_copy import render_wc_table

st.set_page_config(page_title="StrongMail Agent Studio", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="column"] > div:first-child {
        overflow-y: auto;
        max-height: 82vh;
    }
    [data-testid="stSidebar"] {
        min-width: 220px;
        max-width: 220px;
    }
    .block-container {
        padding-top: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Session defaults
st.session_state.setdefault("lang_local", "EN")
st.session_state.setdefault("param_cust_brand", "SKRILL")
st.session_state.setdefault("active_tab_index", 1)
st.session_state.setdefault("working_copy", {})
st.session_state.setdefault("wc_modified_keys", set())
st.session_state.setdefault("wc_edit_count", 0)
st.session_state.setdefault("ta_messages", [])
st.session_state.setdefault("ga_messages", [])
st.session_state.setdefault("tone_stale", False)
st.session_state.setdefault("show_preview", True)

render_sidebar()

st.title("StrongMail Agent Studio")
TAB_LABELS = ["Template Assistant", "General Agent"]
st.session_state.setdefault("active_tab_index", 1)

st.radio(
    "Navigation",
    options=list(range(len(TAB_LABELS))),
    format_func=lambda i: TAB_LABELS[i],
    horizontal=True,
    key="active_tab_index",
)

if st.session_state.active_tab_index == 0:
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        template = st.session_state.get("template_name")
        if template:
            st.caption(f"Editing: **{template}**")
        else:
            st.info("Select or open a template to begin editing.")
    with header_col2:
        st.session_state.show_preview = st.toggle(
            "Show preview",
            value=st.session_state.show_preview,
        )

    render_quick_action_chips()

    from app.session import ensure_working_copy, load_tone_baseline

    ensure_working_copy()
    load_tone_baseline()

    left_col, right_col = st.columns([3, 2])
    with left_col:
        if st.session_state.show_preview:
            render_preview()
        render_chat("ta")
    with right_col:
        render_wc_table()
        render_tone_panel()
else:
    render_chat("ga")
