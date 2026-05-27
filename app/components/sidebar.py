from __future__ import annotations

import streamlit as st

from app.async_utils import run_async_at_startup
from app.health import run_health_checks
from app.session import init_session, init_working_copy, reset_session
from general_agent.services import load_sidebar_metadata


@st.cache_resource
def _cached_sidebar_metadata() -> dict[str, list[str]]:
    return run_async_at_startup(load_sidebar_metadata())


def _has_unsaved_session() -> bool:
    return (
        st.session_state.get("session_id") is not None
        and st.session_state.get("wc_edit_count", 0) > 0
    )


def _apply_lang_brand_change() -> None:
    reset_session()
    init_session()
    if st.session_state.get("template_name"):
        init_working_copy()


def render_sidebar() -> None:
    st.sidebar.title("Agent Studio")

    metadata = _cached_sidebar_metadata()
    languages = metadata["languages"]
    brands = metadata["brands"]
    templates = metadata["templates"]

    st.session_state.setdefault("lang_local", languages[0] if languages else "EN")
    st.session_state.setdefault("param_cust_brand", brands[0] if brands else "SKRILL")

    pending_lang = st.session_state.get("_pending_lang")
    pending_brand = st.session_state.get("_pending_brand")

    if pending_lang is not None:
        st.sidebar.warning(
            f"Changing language to **{pending_lang}** will reset your session. Continue?"
        )
        col_a, col_b = st.sidebar.columns(2)
        if col_a.button("Confirm", key="confirm_lang"):
            st.session_state.lang_local = pending_lang
            st.session_state.pop("_pending_lang", None)
            _apply_lang_brand_change()
            st.rerun()
        if col_b.button("Cancel", key="cancel_lang"):
            st.session_state.pop("_pending_lang", None)
            st.rerun()

    if pending_brand is not None:
        st.sidebar.warning(
            f"Changing brand to **{pending_brand}** will reset your session. Continue?"
        )
        col_a, col_b = st.sidebar.columns(2)
        if col_a.button("Confirm", key="confirm_brand"):
            st.session_state.param_cust_brand = pending_brand
            st.session_state.pop("_pending_brand", None)
            _apply_lang_brand_change()
            st.rerun()
        if col_b.button("Cancel", key="cancel_brand"):
            st.session_state.pop("_pending_brand", None)
            st.rerun()

    selected_lang = st.sidebar.selectbox(
        "Language",
        languages,
        index=languages.index(st.session_state.lang_local)
        if st.session_state.lang_local in languages
        else 0,
        key="lang_selector",
    )
    if selected_lang != st.session_state.lang_local:
        if _has_unsaved_session():
            st.session_state._pending_lang = selected_lang
            st.rerun()
        else:
            st.session_state.lang_local = selected_lang
            _apply_lang_brand_change()
            st.rerun()

    selected_brand = st.sidebar.selectbox(
        "Brand",
        brands,
        index=brands.index(st.session_state.param_cust_brand)
        if st.session_state.param_cust_brand in brands
        else 0,
        key="brand_selector",
    )
    if selected_brand != st.session_state.param_cust_brand:
        if _has_unsaved_session():
            st.session_state._pending_brand = selected_brand
            st.rerun()
        else:
            st.session_state.param_cust_brand = selected_brand
            _apply_lang_brand_change()
            st.rerun()

    if templates:
        current = st.session_state.get("template_name")
        index = templates.index(current) if current in templates else 0
        selected_template = st.sidebar.radio(
            "Templates",
            templates,
            index=index,
            key="template_radio",
        )
        if selected_template != current:
            reset_session()
            st.session_state.template_name = selected_template
            init_session()
            init_working_copy()
            st.rerun()
    else:
        st.sidebar.caption("No templates found in database.")

    st.sidebar.divider()
    st.sidebar.caption("Service health")
    for status in run_health_checks():
        dot = "🟢" if status.healthy else "🔴"
        label = f"{dot} {status.name}"
        if status.healthy:
            st.sidebar.caption(label)
        else:
            st.sidebar.caption(f"{label}: {status.error_message}")
