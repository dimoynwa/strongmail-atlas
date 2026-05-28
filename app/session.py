from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, TypeVar

import streamlit as st

from app.async_utils import run_async
from app.models import PendingDiff
from app.runtime import (
    STUDIO_USER_ID,
    create_runner,
    extract_overrides,
    fetch_resolved_html,
    fetch_working_copy_sources,
    load_stored_tone,
    merge_working_copy,
    parse_json_object,
    parse_pending_diff,
    run_agent_turn_async,
)

T = TypeVar("T")

# Backward-compatible aliases for tests and callers.
_parse_json_object = parse_json_object
_extract_overrides = extract_overrides
_create_runner = create_runner
_run_agent_turn_async = run_agent_turn_async
_fetch_resolved_html = fetch_resolved_html
_fetch_working_copy_sources = fetch_working_copy_sources
_load_stored_tone_async = load_stored_tone


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    return run_async(coro)


def init_session() -> None:
    if st.session_state.get("runner") and st.session_state.get("adk_session"):
        return

    import uuid

    session_id = str(uuid.uuid4())
    st.session_state.session_id = session_id

    state = {
        "template_name": st.session_state.get("template_name"),
        "lang_local": st.session_state.get("lang_local", "EN"),
        "param_cust_brand": st.session_state.get("param_cust_brand", "SKRILL"),
        "session_id": session_id,
    }

    from template_assistant.agent import app as template_assistant_app

    runner, adk_session = run_sync(
        create_runner(template_assistant_app, "template_assistant", state)
    )
    st.session_state.runner = runner
    st.session_state.adk_session = adk_session


def init_ga_runner() -> None:
    if st.session_state.get("ga_runner") and st.session_state.get("ga_adk_session"):
        return

    import uuid

    from general_agent.agent import app as general_agent_app

    session_id = str(uuid.uuid4())
    st.session_state.ga_session_id = session_id
    state = {
        "lang_local": st.session_state.get("lang_local", "EN"),
        "param_cust_brand": st.session_state.get("param_cust_brand", "SKRILL"),
        "session_id": session_id,
    }
    runner, adk_session = run_sync(
        create_runner(general_agent_app, "general_agent", state)
    )
    st.session_state.ga_runner = runner
    st.session_state.ga_adk_session = adk_session


def get_resolved_html() -> str:
    """Resolve template HTML directly (read-only, bypasses LLM routing)."""
    if not st.session_state.get("template_name"):
        return ""

    init_session()
    session_state = {
        "template_name": st.session_state.template_name,
        "lang_local": st.session_state.get("lang_local", "EN"),
        "param_cust_brand": st.session_state.get("param_cust_brand", "SKRILL"),
        "session_id": st.session_state.session_id,
    }
    return run_async(fetch_resolved_html(session_state))


def run_agent_turn(query: str, *, agent_key: str = "ta") -> tuple[str, str | None]:
    if agent_key == "ga":
        init_ga_runner()
        runner = st.session_state["ga_runner"]
        session_id = st.session_state["ga_session_id"]
    else:
        init_session()
        runner = st.session_state["runner"]
        session_id = st.session_state["session_id"]

    return run_async(
        run_agent_turn_async(query, runner=runner, session_id=session_id)
    )


def _session_state_dict() -> dict[str, Any]:
    return {
        "template_name": st.session_state.get("template_name"),
        "lang_local": st.session_state.get("lang_local", "EN"),
        "param_cust_brand": st.session_state.get("param_cust_brand", "SKRILL"),
        "session_id": st.session_state.get("session_id"),
    }


def _apply_working_copy_merge(
    eligible_keys: dict[str, str], overrides: dict[str, str], *, reset_messages: bool
) -> None:
    merged = merge_working_copy(eligible_keys, overrides)
    st.session_state.working_copy = merged
    st.session_state.wc_modified_keys = set(overrides.keys())
    st.session_state.wc_edit_count = len(overrides)
    if reset_messages:
        st.session_state.ta_messages = []
        st.session_state.tone_stale = False


def init_working_copy() -> None:
    if not st.session_state.get("template_name"):
        return

    init_session()

    try:
        eligible_keys, overrides = run_async(fetch_working_copy_sources(_session_state_dict()))
    except Exception as exc:
        st.session_state.working_copy = {}
        st.error(f"Could not load editable keys: {exc}")
        return

    _apply_working_copy_merge(eligible_keys, overrides, reset_messages=True)


def ensure_working_copy() -> None:
    """Populate working copy when a template is selected but keys were not loaded."""
    if not st.session_state.get("template_name"):
        return
    if st.session_state.get("working_copy"):
        return
    if st.session_state.get("_wc_init_failed"):
        return

    init_session()
    try:
        eligible_keys, overrides = run_async(fetch_working_copy_sources(_session_state_dict()))
    except Exception as exc:
        st.session_state._wc_init_failed = True
        st.session_state.working_copy = {}
        st.error(f"Could not load editable keys: {exc}")
        return

    st.session_state.pop("_wc_init_failed", None)
    _apply_working_copy_merge(eligible_keys, overrides, reset_messages=False)


def load_tone_baseline() -> None:
    """Load persisted tone scores from PostgreSQL for delta display."""
    if not st.session_state.get("template_name"):
        return
    if st.session_state.get("tone_stored") is not None:
        return

    init_session()
    try:
        stored = run_async(load_stored_tone(_session_state_dict()))
    except Exception:
        stored = None
    if stored:
        st.session_state.tone_stored = stored
        if st.session_state.get("tone_scores") is None:
            st.session_state.tone_scores = dict(stored)


async def _persist_tone_scores_async(scores: dict[str, float]) -> None:
    from app.runtime import ensure_infrastructure
    from template_assistant.subagents.tone_evaluation_subagent import store_tone_scores

    await ensure_infrastructure()
    await store_tone_scores(scores, _session_state_dict())


def persist_tone_scores(scores: dict[str, float]) -> None:
    """Save evaluated tone scores to template_tone_evaluations."""
    init_session()
    run_async(_persist_tone_scores_async(scores))
    st.session_state.tone_stored = dict(scores)


def reset_session() -> None:
    for key in (
        "runner",
        "adk_session",
        "session_id",
        "template_name",
        "working_copy",
        "wc_modified_keys",
        "wc_edit_count",
        "ta_messages",
        "pending_diff",
        "tone_scores",
        "tone_stored",
        "tone_stale",
        "_wc_init_failed",
    ):
        if key in st.session_state:
            del st.session_state[key]
