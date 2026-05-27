from __future__ import annotations

import streamlit as st

from app.session import get_resolved_html


def render_preview() -> None:
    st.subheader("Live preview")
    if not st.session_state.get("template_name"):
        st.info("Select a template to preview.")
        return

    try:
        html = get_resolved_html()
    except Exception as exc:
        st.error(f"Could not render preview: {exc}")
        return

    if not html.strip():
        st.warning("Template resolved to empty HTML.")
        return

    working_copy = st.session_state.get("working_copy", {})
    modified_keys = st.session_state.get("wc_modified_keys", set())
    for key in modified_keys:
        value = working_copy.get(key)
        if value and value in html:
            # count=1: only the first occurrence is highlighted
            html = html.replace(
                value,
                f'<span style="border-left:2px solid #22c55e;padding-left:6px;color:#166534">{value}</span>',
                1,
            )

    height = max(400, min(800, len(html) // 8))
    st.components.v1.html(html, height=height, scrolling=True)
