from __future__ import annotations

import json

import streamlit as st

from app.session import persist_tone_scores, run_agent_turn


def render_tone_bars() -> None:
    tone_scores = st.session_state.get("tone_scores") or {}
    tone_stored = st.session_state.get("tone_stored") or {}

    if not tone_scores:
        st.caption("No tone evaluation yet.")
        return

    top = sorted(tone_scores.items(), key=lambda item: item[1], reverse=True)[:5]
    for label, score in top:
        delta = score - tone_stored.get(label, score)
        arrow = "▲" if delta > 0 else "▼"
        st.progress(score, text=f"{label}  {score:.2f}")
        st.caption(f"{arrow}{abs(delta):.2f}")


def on_reevaluate_tone() -> None:
    response, _ = run_agent_turn(
        "System: call evaluate_tone and return only the emotions JSON object, no other text."
    )
    try:
        payload = json.loads(response.strip())
    except json.JSONDecodeError:
        st.error("Could not parse tone evaluation response.")
        return
    if isinstance(payload, dict) and "scores" in payload:
        scores = payload["scores"]
    elif isinstance(payload, dict):
        scores = payload
    else:
        st.error("Unexpected tone evaluation format.")
        return
    tone_scores = {str(k): float(v) for k, v in scores.items()}
    st.session_state.tone_scores = tone_scores
    try:
        persist_tone_scores(tone_scores)
    except Exception as exc:
        st.error(f"Could not save tone scores: {exc}")
        return
    st.session_state.tone_stale = False
    st.rerun()


def render_tone_panel() -> None:
    st.subheader("Tone evaluation")

    if st.session_state.get("tone_stale"):
        st.warning("Scores may be outdated — working copy has changed")

    render_tone_bars()

    if st.button("Re-evaluate tone", key="reevaluate_tone"):
        on_reevaluate_tone()
