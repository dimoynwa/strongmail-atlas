from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from template_assistant.llm import get_llm_model

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.graph_builder import build_resolution_graph
from template_assistant.context import SessionContext, validate_session_context
from template_assistant.ml.goemotions import get_classifier, scores_from_pipeline_result
from template_assistant.models import ToneSuggestion
from template_assistant.services import (
    SNAPSHOT_NONE_SENTINEL,
    resolve_template,
    snapshot_key,
    working_copy_key,
)
from template_assistant.subagents.working_copy_subagent import set_working_copy_value
from template_assistant.tone_profiles import lookup_tone_profile
from template_assistant.utils.text import extract_plain_text

RewriteFn = Callable[[str, str, dict[str, float], str], Awaitable[str]]

_rewrite_fn: RewriteFn | None = None


def set_rewrite_fn(fn: RewriteFn | None) -> None:
    global _rewrite_fn
    _rewrite_fn = fn


def is_eligible_for_rewrite(key: str, value: str) -> bool:
    upper_key = key.upper()
    if upper_key.endswith(("_URL", "_COLOR", "_ID")):
        return False
    if value.startswith("http"):
        return False
    if len(value) < 20:
        return False
    return True


async def capture_snapshot(
    keys: list[str],
    session_context: SessionContext,
    redis: Any,
    graph: Any,
) -> None:
    """Capture pre-suggestion values for undo support."""
    wc_key = working_copy_key(session_context)
    snap_key = snapshot_key(session_context)
    await redis.delete(snap_key)
    for key in keys:
        canonical = key.upper()
        wc_val = await redis.hget(wc_key, canonical)
        if wc_val is not None:
            stored = wc_val
        else:
            graph_val = graph.get(canonical)
            stored = graph_val if graph_val is not None else SNAPSHOT_NONE_SENTINEL
        await redis.hset(snap_key, canonical, stored)


async def _default_rewrite(
    _key: str,
    current_value: str,
    target_profile: dict[str, float],
    _context: str,
) -> str:
    dominant = max(target_profile, key=target_profile.get)
    return f"{current_value} [{dominant} tone]"


async def _generate_rewrite(
    key: str,
    current_value: str,
    target_profile: dict[str, float],
    template_context: str,
) -> str:
    if _rewrite_fn is not None:
        return await _rewrite_fn(key, current_value, target_profile, template_context)
    return await _default_rewrite(key, current_value, target_profile, template_context)


def _predict_delta(
    baseline: dict[str, float], target_profile: dict[str, float]
) -> dict[str, float]:
    return {
        emotion: target_profile[emotion] - baseline.get(emotion, 0.0)
        for emotion in target_profile
    }


async def suggest_tone_rewrites(target_intent: str, session_state: dict) -> list[ToneSuggestion]:
    """Suggest rewrites for eligible keys to match the requested tone intent."""
    session_context = validate_session_context(session_state)
    target_profile = lookup_tone_profile(target_intent)
    if target_profile is None:
        target_profile = {"optimism": 0.5, "approval": 0.5}

    resolution = await resolve_template(session_context)
    plain_text = extract_plain_text(resolution.resolved_body)
    if plain_text:
        classifier = get_classifier()
        raw = classifier(plain_text)
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            baseline = scores_from_pipeline_result(raw[0])
        else:
            baseline = scores_from_pipeline_result(raw)
    else:
        baseline = {}

    pool = get_pool()
    graph = await build_resolution_graph(pool, session_context.template_name)
    redis_client = get_redis()

    suggestions: list[ToneSuggestion] = []
    from shared.resolution.resolver import resolve_key as shared_resolve_key
    from template_assistant.context import build_resolution_context

    context = build_resolution_context(session_context)
    structure_keys = set(graph.keys())
    for key in sorted(structure_keys):
        value, _unres = await shared_resolve_key(
            pool,
            redis_client,
            graph,
            key,
            context,
            session_context.session_id,
            session_context.template_name,
        )
        if value is None or not is_eligible_for_rewrite(key, value):
            continue
        suggested = await _generate_rewrite(
            key, value, target_profile, resolution.resolved_body
        )
        suggestions.append(
            ToneSuggestion(
                key=key,
                current_value=value,
                suggested_value=suggested,
                predicted_delta=_predict_delta(baseline, target_profile),
            )
        )

    return suggestions


async def apply_tone_suggestions(
    suggestions: list[dict[str, Any]] | list[ToneSuggestion],
    session_state: dict,
) -> dict:
    """Snapshot affected keys, then write suggestions to the working copy."""
    session_context = validate_session_context(session_state)
    normalized: list[ToneSuggestion] = []
    for item in suggestions:
        if isinstance(item, ToneSuggestion):
            normalized.append(item)
        else:
            normalized.append(
                ToneSuggestion(
                    key=item["key"],
                    current_value=item.get("current_value", ""),
                    suggested_value=item["suggested_value"],
                    predicted_delta=item.get("predicted_delta", {}),
                )
            )

    if not normalized:
        return {"applied": 0, "message": "No suggestions to apply."}

    pool = get_pool()
    graph = await build_resolution_graph(pool, session_context.template_name)
    redis_client = get_redis()
    keys = [item.key for item in normalized]
    await capture_snapshot(keys, session_context, redis_client, graph)

    for item in normalized:
        await set_working_copy_value(item.key, item.suggested_value, session_state)

    return {"applied": len(normalized), "message": f"Applied {len(normalized)} tone rewrites."}


async def undo_tone_suggestions(
    keys: list[str] | None,
    session_state: dict,
) -> dict:
    """Restore working copy values from the pre-suggestion snapshot."""
    session_context = validate_session_context(session_state)
    redis_client = get_redis()
    snap_key = snapshot_key(session_context)
    wc_key = working_copy_key(session_context)

    snapshot = await redis_client.hgetall(snap_key)
    if not snapshot:
        return {"restored": 0, "message": "No tone suggestion snapshot exists to undo."}

    target_keys = keys if keys is not None else list(snapshot.keys())
    restored = 0
    for key in target_keys:
        canonical = key.upper()
        if canonical not in snapshot:
            continue
        original = snapshot[canonical]
        if original == SNAPSHOT_NONE_SENTINEL:
            await redis_client.hdel(wc_key, canonical)
        else:
            await redis_client.hset(wc_key, canonical, original)
        restored += 1

    return {"restored": restored, "message": f"Restored {restored} placeholder(s)."}


async def _suggest_tone_rewrites_tool(
    target_intent: str, tool_context: ToolContext
) -> list[dict]:
    suggestions = await suggest_tone_rewrites(target_intent, tool_context.state.to_dict())
    return [
        {
            "key": s.key,
            "current_value": s.current_value,
            "suggested_value": s.suggested_value,
            "predicted_delta": s.predicted_delta,
        }
        for s in suggestions
    ]


async def _apply_tone_suggestions_tool(
    suggestions: list[dict], tool_context: ToolContext
) -> dict:
    return await apply_tone_suggestions(suggestions, tool_context.state.to_dict())


async def _undo_tone_suggestions_tool(
    keys: list[str] | None, tool_context: ToolContext
) -> dict:
    return await undo_tone_suggestions(keys, tool_context.state.to_dict())


def create_tone_suggestion_subagent() -> LlmAgent:
    return LlmAgent(
        name="ToneSuggestionSubagent",
        model=get_llm_model("TONE_SUGGESTION"),
        description="""
        Owns the full end-to-end tone improvement cycle for the loaded template.
        Maps natural language tone intent to GoEmotions target profiles, identifies
        eligible placeholder keys for rewriting, generates LLM-based rewrites,
        applies them immediately to the Redis working copy, and supports undo
        of the most recent suggestion batch via a pre-suggestion snapshot.
        """,
        instruction="""
        You are the Tone Suggestion Subagent. You help template authors improve
        the emotional tone of their template by rewriting specific placeholder
        values and applying those rewrites to the session working copy.

        ## Full suggestion flow (always in this order)
        1. Validate SessionContext.
        2. Map the user's natural language intent to a target emotion weight
           profile using TONE_PROFILES. For unknown intents, use your LLM
           reasoning to derive a plausible weight dict anchored to the
           nearest known profile.
        3. Call resolve_full_template (respects working copy) to get current HTML.
        4. Call extract_plain_text to get plain text for baseline scoring.
        5. Run GoEmotions via get_classifier() to get baseline emotion scores.
        6. Filter all placeholder keys through is_eligible_for_rewrite:
           - Exclude keys ending in _URL, _COLOR, _ID
           - Exclude values starting with http
           - Exclude values shorter than 20 characters
        7. If no eligible keys remain, inform the user and stop — do not
           attempt rewrites on ineligible keys.
        8. For each eligible key, call the underlying LLM with:
           - The target emotion weight profile
           - The key's current resolved value
           - Surrounding resolved template context for coherence
           The LLM returns only the rewritten value — no key names,
           no explanations, no markdown formatting.
        9. Capture the pre-suggestion snapshot via capture_snapshot BEFORE
           writing anything to Redis. The snapshot stores, for each affected
           key: the current Redis working copy value if one exists, or the
           graph value if not (stored as None to signal "not in working copy").
       10. Write all suggested values to the Redis working copy via
           set_working_copy_value. The snapshot MUST be fully written before
           this step begins.
       11. Present results to the user: for each changed key, show the key name,
           the old value, and the new value. Confirm how many changes were applied.

        ## Undo flow
        When the user asks to undo tone suggestions:
        1. Validate SessionContext.
        2. Read the snapshot from working-copy-snapshot:{template_name}:{session_id}.
        3. If no snapshot exists, tell the user there are no tone suggestions
           to undo in this session — do not raise an error.
        4. For each key in the undo scope (all keys or a named subset):
           - If snapshot value is None: delete the key from the working copy
             (it was not in the working copy before suggestions were applied)
           - If snapshot value is a string: write that string back to the
             working copy (restores the value the user had before suggestions)
        5. Confirm to the user exactly which keys were restored and to what values.

        ## Your tools
        - suggest_tone_rewrites: runs steps 1–8 above and returns a list of
          ToneSuggestion objects.
        - apply_tone_suggestions: runs steps 9–10 above — captures snapshot
          then writes to working copy.
        - undo_tone_suggestions: runs the undo flow above. Accepts an optional
          list of specific keys; when None, undoes all keys in the snapshot.

        ## Behaviour rules
        - Always validate SessionContext as the first action in every tool call.
        - The snapshot MUST be written before any working copy writes.
          This ordering is non-negotiable — if snapshot write fails, abort.
        - A second call to apply_tone_suggestions overwrites the previous
          snapshot entirely. Never merge or append snapshots.
        - Never rewrite structural values — is_eligible_for_rewrite is the
          sole gatekeeper for which keys can be changed.
        - Never write to PostgreSQL.
        - Undo only covers the most recent suggestion batch. If the user
          has applied two batches, undo restores to the state before the
          second batch only.
        - When presenting suggestions before apply, always show both the
          current value and the proposed value side by side so the user
          can see exactly what will change.
        - Use set_working_copy_value from WorkingCopySubagent's shared module
          directly — do not delegate to WorkingCopySubagent via agent routing
          for this internal operation.
        """,
        tools=[
            _suggest_tone_rewrites_tool,
            _apply_tone_suggestions_tool,
            _undo_tone_suggestions_tool,
        ],
    )


ToneSuggestionSubagent = create_tone_suggestion_subagent()
