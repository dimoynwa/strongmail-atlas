from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
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
from template_assistant.subagents.working_copy_subagent import get_working_copy, set_working_copy_value
from template_assistant.tone_profiles import lookup_tone_profile
from template_assistant.utils.text import extract_plain_text

logger = logging.getLogger(__name__)

RewriteFn = Callable[[str, str, dict[str, float], str], Awaitable[str]]
LlmBatchFn = Callable[[str], Awaitable[str]]

_rewrite_fn: RewriteFn | None = None
_llm_batch_fn: LlmBatchFn | None = None

_COLOUR_PATTERN = re.compile(
    r"^(#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})|rgb\s*\(|rgba\s*\()",
    re.IGNORECASE,
)
_BARE_TOKEN_PATTERN = re.compile(r"^(##[^#]+##\s*)+$")


@dataclass
class EligibilityResult:
    key: str
    value: str
    eligible: bool
    reason: str | None


@dataclass
class DiscardedSuggestion:
    key: str
    reason: str


class KeyNotInGraphError(Exception):
    """Raised when apply_tone_suggestions receives keys absent from the resolution graph."""

    def __init__(self, invalid_keys: list[str], valid_keys_not_written: list[str]) -> None:
        self.invalid_keys = invalid_keys
        self.valid_keys_not_written = valid_keys_not_written
        super().__init__(
            f"Keys not in resolution graph: {invalid_keys}. "
            f"No keys were written; valid keys not applied: {valid_keys_not_written}."
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "KeyNotInGraphError",
            "invalid_keys": self.invalid_keys,
            "valid_keys_not_written": self.valid_keys_not_written,
        }


def set_rewrite_fn(fn: RewriteFn | None) -> None:
    global _rewrite_fn
    _rewrite_fn = fn


def set_llm_batch_fn(fn: LlmBatchFn | None) -> None:
    global _llm_batch_fn
    _llm_batch_fn = fn


def _has_valid_prefix(key: str, lang_local: str, param_cust_brand: str) -> bool:
    upper_key = key.upper()
    if "." not in upper_key:
        return True
    prefixes = (
        f"{lang_local.upper()}.",
        f"{param_cust_brand.upper()}.",
        "GENERIC.",
    )
    return any(upper_key.startswith(prefix) for prefix in prefixes)


def evaluate_eligibility(
    key: str,
    value: str,
    lang_local: str,
    param_cust_brand: str,
) -> EligibilityResult:
    """Evaluate a single key/value pair for tone rewrite eligibility."""
    if not _has_valid_prefix(key, lang_local, param_cust_brand):
        return EligibilityResult(key, value, False, "wrong_prefix")
    if key.upper().startswith("SM_RULE_"):
        return EligibilityResult(key, value, False, "sm_rule")
    stripped = value.strip()
    if stripped.lower().startswith(("http://", "https://")):
        return EligibilityResult(key, value, False, "url")
    if _COLOUR_PATTERN.match(stripped):
        return EligibilityResult(key, value, False, "colour_code")
    if stripped.isdigit():
        return EligibilityResult(key, value, False, "numeric")
    if _BARE_TOKEN_PATTERN.match(stripped):
        return EligibilityResult(key, value, False, "bare_token")
    if len(stripped) <= 20:
        return EligibilityResult(key, value, False, "too_short")
    return EligibilityResult(key, value, True, None)


def is_eligible_for_rewrite(
    key: str,
    value: str,
    lang_local: str = "",
    param_cust_brand: str = "",
) -> bool:
    """Return whether a placeholder key/value may be tone-rewritten."""
    if not lang_local and not param_cust_brand:
        upper_key = key.upper()
        if upper_key.endswith(("_URL", "_COLOR", "_ID")):
            return False
        if value.startswith("http"):
            return False
        if len(value) < 20:
            return False
        return True
    return evaluate_eligibility(key, value, lang_local, param_cust_brand).eligible


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


async def _build_reachable_eligible(
    graph: Any,
    resolution: Any,
    session_context: SessionContext,
    session_state: dict,
) -> tuple[dict[str, str], list[str]]:
    """Apply reachability pre-filter, then content eligibility filter."""
    reachable = set(resolution.resolved_keys)
    wc = await get_working_copy(session_state)
    eligible: dict[str, str] = {}
    ineligible_keys: list[str] = []
    for key, graph_value in graph.items():
        if key not in reachable:
            continue
        value = wc.get(key, graph_value)
        result = evaluate_eligibility(
            key,
            value,
            session_context.lang_local,
            session_context.param_cust_brand,
        )
        if result.eligible:
            eligible[key] = value
        else:
            ineligible_keys.append(key)
    return eligible, ineligible_keys


def _build_llm_prompt(
    eligible: dict[str, str],
    target_intent: str,
    target_profile: dict[str, float],
) -> str:
    keys_payload = [{"key": key, "current_value": value} for key, value in sorted(eligible.items())]
    return (
        f"Rewrite placeholder values to match the tone intent: {target_intent!r}.\n"
        f"Target emotion weights: {json.dumps(target_profile)}\n"
        f"Eligible keys and current values:\n{json.dumps(keys_payload, indent=2)}\n\n"
        "Return rewrites ONLY for keys from this exact list. "
        "Do not introduce, rename, or abbreviate any key. "
        "Use the exact key string as provided.\n"
        "Respond with JSON only: a list of objects with \"key\" and \"new_value\" fields."
    )


def _parse_llm_rewrites(raw: str) -> list[dict[str, str]]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("LLM response must be a JSON list")
    result: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        new_value = item.get("new_value")
        if isinstance(key, str) and isinstance(new_value, str):
            result.append({"key": key, "new_value": new_value})
    return result


async def _call_batch_llm(
    prompt: str,
    eligible: dict[str, str],
    target_profile: dict[str, float],
    template_context: str,
) -> str:
    if _llm_batch_fn is not None:
        return await _llm_batch_fn(prompt)
    rewrites = []
    for key, current_value in sorted(eligible.items()):
        new_value = await _generate_rewrite(key, current_value, target_profile, template_context)
        rewrites.append({"key": key, "new_value": new_value})
    return json.dumps(rewrites)


def _validate_llm_rewrites(
    raw_items: list[dict[str, str]],
    eligible: dict[str, str],
) -> tuple[list[dict[str, str]], list[DiscardedSuggestion]]:
    eligible_keys = set(eligible.keys())
    suggestions: list[dict[str, str]] = []
    discarded: list[DiscardedSuggestion] = []
    for item in raw_items:
        key = item["key"]
        if key in eligible_keys:
            suggestions.append(item)
        else:
            logger.warning("Discarding hallucinated tone rewrite key: %s", key)
            discarded.append(DiscardedSuggestion(key=key, reason="hallucinated_key"))
    return suggestions, discarded


async def suggest_tone_rewrite(target_intent: str, session_state: dict) -> dict[str, Any]:
    """Suggest tone rewrites with strict eligibility and hallucination filtering."""
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

    eligible, ineligible_keys = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )

    suggestion_id = str(uuid.uuid4())
    if not eligible:
        return {
            "suggestions": [],
            "ineligible_keys": ineligible_keys,
            "discarded_keys": [],
            "target_emotions": target_profile,
            "snapshot_saved": False,
            "suggestion_id": suggestion_id,
            "message": "No eligible keys found for tone rewriting.",
        }

    prompt = _build_llm_prompt(eligible, target_intent, target_profile)
    raw_response = await _call_batch_llm(
        prompt, eligible, target_profile, resolution.resolved_body
    )
    raw_items = _parse_llm_rewrites(raw_response)
    accepted, discarded = _validate_llm_rewrites(raw_items, eligible)

    delta = _predict_delta(baseline, target_profile)
    tone_suggestions = [
        ToneSuggestion(
            key=item["key"],
            current_value=eligible[item["key"]],
            suggested_value=item["new_value"],
            predicted_delta=delta,
        )
        for item in accepted
    ]

    payload: dict[str, Any] = {
        "suggestions": [
            {"key": t.key, "new_value": t.suggested_value} for t in tone_suggestions
        ],
        "ineligible_keys": ineligible_keys,
        "discarded_keys": [asdict(d) for d in discarded],
        "target_emotions": target_profile,
        "snapshot_saved": False,
        "suggestion_id": suggestion_id,
    }
    if not tone_suggestions:
        payload["message"] = "No valid tone rewrite keys were generated."
    return payload


async def suggest_tone_rewrites(target_intent: str, session_state: dict) -> list[ToneSuggestion]:
    """Suggest rewrites for eligible keys to match the requested tone intent."""
    session_context = validate_session_context(session_state)
    target_profile = lookup_tone_profile(target_intent) or {"optimism": 0.5, "approval": 0.5}

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

    eligible, _ineligible_keys = await _build_reachable_eligible(
        graph, resolution, session_context, session_state
    )

    suggestions: list[ToneSuggestion] = []
    for key in sorted(eligible.keys()):
        value = eligible[key]
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
    graph_keys = set(graph.keys())

    invalid_keys: list[str] = []
    valid_keys: list[str] = []
    for item in normalized:
        canonical = item.key.upper()
        if canonical not in graph_keys:
            invalid_keys.append(item.key)
        else:
            valid_keys.append(item.key)

    if invalid_keys:
        raise KeyNotInGraphError(
            invalid_keys=invalid_keys,
            valid_keys_not_written=valid_keys,
        )

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
) -> dict[str, Any]:
    return await suggest_tone_rewrite(target_intent, tool_context.state.to_dict())


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
           - Require lang_local, param_cust_brand, or GENERIC. prefix (or bare keys)
           - Exclude SM_RULE_* keys
           - Exclude URL, CSS colour, numeric-only, and short (<=20 char) values
        7. If no eligible keys remain, inform the user and stop — do not
           attempt rewrites on ineligible keys.
        8. Call suggest_tone_rewrites, which builds the LLM prompt internally with:
           - KEYS AND CURRENT VALUES: the eligible key set as JSON
           - TONE TARGET: the target emotion weight profile
           The prompt sent to the LLM must include all of the following instructions verbatim:
            KEYS AND CURRENT VALUES:
            (eligible keys and current values as JSON)

            TONE TARGET:
            (target emotion weights as JSON)

            INSTRUCTIONS:
            - You are rewriting email template copy values to shift their emotional tone toward the target emotions listed above.
            - For each key, produce a rewritten version of the value that feels more
              aligned with the target tone while preserving the original meaning,
              approximate length, and any formatting markers (e.g. ##TOKEN## references
              must be kept in place exactly as they appear).
            - Do NOT append tone labels, annotations, tags, or comments to the original
              value. The new_value must be a standalone rewrite, not the original value
              with additions.
            - Do NOT copy the old value into new_value unchanged. Every returned key
              must have a genuinely rewritten value. If you cannot meaningfully rewrite
              a value, omit that key from the response entirely.
            - Return ONLY keys from the provided list. Do not introduce, rename,
              abbreviate, or invent any key.
            - Respond with valid JSON only — no preamble, no explanation, no markdown
              fences. The response must be a JSON array of objects with exactly two
              fields per object: "key" (string) and "new_value" (string).

            EXAMPLE OUTPUT FORMAT:
            [
                {"key": "EN.PARAGRAPH_1", "new_value": "Rewritten prose here."},
                {"key": "EN.SUBJECT", "new_value": "Rewritten subject here."}
            ]

        9. Capture the pre-suggestion snapshot via capture_snapshot BEFORE
           writing anything to Redis. The snapshot stores, for each affected
           key: the current Redis working copy value if one exists, or the
           graph value if not (stored as None to signal "not in working copy").
       10. Write all suggested values to the Redis working copy via
           set_working_copy_value. The snapshot MUST be fully written before
           this step begins. All keys are validated against the resolution
           graph before any write — invalid keys abort the entire batch.
       11. Present results to the user: for each changed key, show the key name,
           the old value, and the new value. Confirm how many changes were applied.

        ## Undo flow
        When the user asks to undo tone suggestions:
        1. Validate SessionContext.
        2. Read the snapshot from working-copy-snapshot:{{template_name}}:{{session_id}}.
        3. If no snapshot exists, tell the user there are no tone suggestions
           to undo in this session — do not raise an error.
        4. For each key in the undo scope (all keys or a named subset):
           - If snapshot value is None: delete the key from the working copy
             (it was not in the working copy before suggestions were applied)
           - If snapshot value is a string: write that string back to the
             working copy (restores the value the user had before suggestions)
        5. Confirm to the user exactly which keys were restored and to what values.

        ## Your tools
        - suggest_tone_rewrites: runs steps 1–8 above and returns suggestions,
          ineligible keys, and any discarded hallucinated keys.
        - apply_tone_suggestions: runs steps 9–10 above — captures snapshot
          then writes to working copy after graph validation.
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
        - The LLM rewrite prompt must always include the tone target emotions, the
          explicit no-annotation instruction, the no-unchanged-copy instruction, and
          the JSON-only output format. Never call the LLM with a partial prompt that
          omits any of these four elements.
        - After parsing the LLM JSON response, discard any key where new_value is
          identical to old_value (the LLM copied the original unchanged). Log a
          warning for each discarded key. Do not present unchanged values as
          suggestions to the user.
        """,
        tools=[
            _suggest_tone_rewrites_tool,
            _apply_tone_suggestions_tool,
            _undo_tone_suggestions_tool,
        ],
    )


ToneSuggestionSubagent = create_tone_suggestion_subagent()
