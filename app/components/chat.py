from __future__ import annotations

import json
import re

import streamlit as st

from app.models import PendingDiff, TemplateCard
from app.session import init_working_copy, parse_pending_diff, run_agent_turn


def _messages_key(agent_key: str) -> str:
    return f"{agent_key}_messages"


def _apply_suggestions(keys: list[str] | None) -> None:
    if keys is None:
        msg = "System: call apply_tone_suggestions with all pending suggestions"
    else:
        msg = f"System: call apply_tone_suggestions for keys {json.dumps(keys)}"
    run_agent_turn(msg, agent_key="ta")


def on_apply_all() -> None:
    diff = st.session_state.pending_diff
    if diff is None:
        return
    try:
        _apply_suggestions(None)
        st.session_state.pending_diff = None
        st.session_state.tone_stale = True
        for entry in diff.entries:
            st.session_state.working_copy[entry.key] = entry.new_value
            st.session_state.wc_modified_keys.add(entry.key)
        st.session_state.wc_edit_count = st.session_state.get("wc_edit_count", 0) + len(
            diff.entries
        )
    except Exception as exc:
        st.error(f"Could not apply suggestions: {exc}")
        return
    st.rerun()


def on_apply_selected(selected_keys: list[str]) -> None:
    diff = st.session_state.pending_diff
    if diff is None or not selected_keys:
        return
    try:
        _apply_suggestions(selected_keys)
        st.session_state.pending_diff = None
        st.session_state.tone_stale = True
        for entry in diff.entries:
            if entry.key in selected_keys:
                st.session_state.working_copy[entry.key] = entry.new_value
                st.session_state.wc_modified_keys.add(entry.key)
        st.session_state.wc_edit_count = st.session_state.get("wc_edit_count", 0) + len(
            selected_keys
        )
    except Exception as exc:
        st.error(f"Could not apply suggestions: {exc}")
        return
    st.rerun()


def on_discard_diff() -> None:
    st.session_state.pending_diff = None
    st.rerun()


def render_diff_card(diff: PendingDiff) -> None:
    if diff.snapshot_overwritten:
        st.warning(
            "Note: applying these suggestions will replace the undo snapshot "
            "from your previous suggestion batch."
        )

    for entry in diff.entries:
        st.markdown(
            f"<del style='color:#ef4444'>{entry.old_value}</del> → "
            f"<span style='color:#22c55e'>{entry.new_value}</span>",
            unsafe_allow_html=True,
        )

    col1, col2, col3 = st.columns(3)
    if col1.button("Apply all", key="diff_apply_all"):
        on_apply_all()
    with col2.expander("Apply selected"):
        selected = st.multiselect(
            "Keys",
            [entry.key for entry in diff.entries],
            key="diff_selected_keys",
        )
        if st.button("Apply selected", key="diff_apply_selected"):
            on_apply_selected(selected)
    if col3.button("Discard", key="diff_discard"):
        on_discard_diff()


def _parse_template_cards(text: str) -> list[TemplateCard]:
    cards: list[TemplateCard] = []
    payload = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                payload = None
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "template_name" in item:
                cards.append(
                    TemplateCard(
                        template_name=str(item["template_name"]),
                        summary=str(item.get("summary", "")),
                        distance=float(item.get("distance", 0.5)),
                    )
                )
    return cards


def _render_template_card(result: TemplateCard) -> None:
    st.markdown(f"**{result.template_name}**")
    st.caption(result.summary)
    similarity = max(0.0, min(1.0, 1.0 - result.distance))
    st.progress(similarity, text=f"Match {similarity:.0%}")

    def _open_template() -> None:
        st.session_state.template_name = result.template_name
        st.session_state.active_tab_index = 0
        init_working_copy()
        st.rerun()

    st.button("Open →", key=f"open_{result.template_name}", on_click=_open_template)


def render_chat(agent_key: str) -> None:
    """Render chat UI for Template Assistant (ta) or General Agent (ga)."""
    messages_key = _messages_key(agent_key)
    st.session_state.setdefault(messages_key, [])

    for msg in st.session_state[messages_key]:
        with st.chat_message(msg["role"]):
            if msg.get("tool"):
                st.caption(f"⚙ {msg['tool']}")
            st.write(msg["content"])
            if msg.get("diff"):
                render_diff_card(msg["diff"])

    if st.session_state.get("pending_diff") and agent_key == "ta":
        render_diff_card(st.session_state.pending_diff)

    if prompt := st.chat_input("Message", key=f"chat_input_{agent_key}"):
        st.session_state[messages_key].append({"role": "user", "content": prompt})
        response, tool = run_agent_turn(prompt, agent_key=agent_key)
        assistant_msg: dict = {"role": "assistant", "content": response}
        if tool:
            assistant_msg["tool"] = tool

        if agent_key == "ta":
            pending = parse_pending_diff(response)
            if pending:
                st.session_state.pending_diff = pending
                assistant_msg["diff"] = pending

        st.session_state[messages_key].append(assistant_msg)
        st.rerun()

    if agent_key == "ga":
        for msg in reversed(st.session_state[messages_key]):
            if msg["role"] == "assistant":
                for card in _parse_template_cards(msg["content"]):
                    _render_template_card(card)
                break


def render_quick_action_chips() -> None:
    chips = [
        "Show placeholders",
        "Full preview",
        "Compare tone",
        "Reset all changes",
        "What changed?",
    ]
    cols = st.columns(len(chips))
    for col, label in zip(cols, chips, strict=True):
        if col.button(label, key=f"chip_{label}"):
            st.session_state.setdefault("ta_messages", [])
            st.session_state.ta_messages.append({"role": "user", "content": label})
            response, tool = run_agent_turn(label, agent_key="ta")
            assistant_msg: dict = {"role": "assistant", "content": response}
            if tool:
                assistant_msg["tool"] = tool
            pending = parse_pending_diff(response)
            if pending:
                st.session_state.pending_diff = pending
                assistant_msg["diff"] = pending
            st.session_state.ta_messages.append(assistant_msg)
            st.rerun()
