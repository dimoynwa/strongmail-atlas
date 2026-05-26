from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from google.genai.types import Content

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

ClassifierLlmFn = Callable[[str], Awaitable[str]]

_classifier_llm_fn: ClassifierLlmFn | None = None

_SUGGEST_AGENT_INSTRUCTION = (
    "You are generating tone rewrites. The keys in rewrite_prompt are "
    "ordered by their reading sequence in the email — rewrite them as a "
    "coherent set, not independently. Return JSON only: a list of objects "
    "with 'key' and 'new_value' fields. Return ONLY keys from eligible_keys. "
    "Do not annotate, append labels, or copy values unchanged."
)

_STRUCTURAL_SUFFIXES = (
    "_URL",
    "_LINK",
    "_HREF",
    "_SRC",
    "_IMG",
    "_IMAGE",
    "_LOGO",
    "_ICON",
    "_COLOR",
    "_COLOUR",
    "_BG",
    "_BACKGROUND",
    "_ID",
    "_CODE",
    "_TAG",
    "_TRACK",
    "_OPENING_BODY",
    "_CLOSING_BODY",
)
_STRUCTURAL_SUBSTRINGS = (
    "FOOTER",
    "HEADER",
    "COPYRIGHT",
    "NAV",
    "PRIVACY",
    "LEGAL",
    "COOKIE",
    "UNSUBSCRIBE",
    "TRACKING",
    "PIXEL",
    "BEACON",
    "VIEWINBROWSER",
    "VIEW_IN_BROWSER",
    'LOGO',
    'ICON',
    'COLOR',
    'COLOUR',
    'BACKGROUND',
)

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


def set_classifier_llm_fn(fn: ClassifierLlmFn | None) -> None:
    global _classifier_llm_fn
    _classifier_llm_fn = fn


def _apply_structural_heuristics(key: str) -> bool:
    """Return True when the key name indicates structural chrome, not prose."""
    upper_key = key.upper()
    if any(upper_key.endswith(suffix) for suffix in _STRUCTURAL_SUFFIXES):
        return True
    return any(substring in upper_key for substring in _STRUCTURAL_SUBSTRINGS)


def _build_classifier_prompt(keys: dict[str, str]) -> str:
    keys_payload = [{"key": key, "value": value} for key, value in sorted(keys.items())]
    return (
        "Classify each template placeholder key as tone-bearing prose or structural chrome.\n"
        "Structural keys include URLs, navigation, legal boilerplate, tracking pixels, "
        "and layout chrome. Tone-bearing keys contain copy the author would rewrite for tone.\n"
        f"Keys to classify:\n{json.dumps(keys_payload, indent=2)}\n\n"
        "Respond with valid JSON only — a list of objects with exactly two fields: "
        '"key" (string) and "role" (either "tone" or "structural"). '
        "Return ONLY keys from the provided list."
    )


def _parse_classifier_response(raw: str) -> dict[str, str]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("Classifier LLM response must be a JSON list")
    result: dict[str, str] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        role = item.get("role")
        if isinstance(key, str) and role in ("tone", "structural"):
            result[key] = role
    return result


async def _default_classifier_llm(prompt: str) -> str:
    import litellm

    from template_assistant.llm import _configure_litellm

    _configure_litellm()
    model_spec = get_llm_model("TONE_SUGGESTION")
    model_id = model_spec if isinstance(model_spec, str) else model_spec.model
    response = await litellm.acompletion(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    content = response.choices[0].message.content
    return content if content else "[]"


async def _llm_classify_keys(keys: dict[str, str]) -> dict[str, str]:
    """Classify ambiguous keys via a single LLM call."""
    if not keys:
        return {}
    prompt = _build_classifier_prompt(keys)
    if _classifier_llm_fn is not None:
        raw = await _classifier_llm_fn(prompt)
    else:
        raw = await _default_classifier_llm(prompt)
    classified = _parse_classifier_response(raw)
    input_keys = set(keys.keys())
    return {key: role for key, role in classified.items() if key in input_keys}


async def classify_keys(
    eligible_keys: dict[str, str],
    session_state: dict,
) -> dict[str, Any]:
    """Two-stage key classification: deterministic heuristics then LLM."""
    del session_state  # read-only classifier; reserved for future session-aware rules
    tone_bearing: dict[str, str] = {}
    structural: dict[str, str] = {}
    ambiguous: dict[str, str] = {}
    stage1_structural_count = 0

    for key, value in eligible_keys.items():
        if _apply_structural_heuristics(key):
            structural[key] = value
            stage1_structural_count += 1
        else:
            ambiguous[key] = value

    stage2_structural_count = 0
    if ambiguous:
        try:
            stage2_roles = await _llm_classify_keys(ambiguous)
        except Exception:
            logger.warning(
                "LLM key classification failed; treating all ambiguous keys as tone-bearing",
                exc_info=True,
            )
            stage2_roles = {key: "tone" for key in ambiguous}

        for key, value in ambiguous.items():
            role = stage2_roles.get(key, "tone")
            if role == "structural":
                structural[key] = value
                stage2_structural_count += 1
            else:
                tone_bearing[key] = value

    return {
        "tone_bearing": tone_bearing,
        "structural": structural,
        "stage1_structural_count": stage1_structural_count,
        "stage2_structural_count": stage2_structural_count,
        "tone_bearing_count": len(tone_bearing),
    }


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
    if len(stripped) <= 5:
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


def _order_keys_by_reading_position(
    eligible: dict[str, str], resolved_body: str
) -> list[tuple[str, str]]:
    """Return eligible items ordered by first appearance in resolved_body."""
    with_position: list[tuple[int, int, str, str]] = []
    without_position: list[tuple[int, str, str]] = []
    for orig_idx, (key, value) in enumerate(eligible.items()):
        pos = resolved_body.find(key)
        if pos >= 0:
            with_position.append((pos, orig_idx, key, value))
        else:
            without_position.append((orig_idx, key, value))
    with_position.sort(key=lambda item: (item[0], item[1]))
    without_position.sort(key=lambda item: item[0])
    ordered = [(key, value) for _, _, key, value in with_position]
    ordered.extend((key, value) for _, key, value in without_position)
    return ordered


def _build_llm_prompt(
    eligible: dict[str, str],
    target_intent: str,
    target_profile: dict[str, float],
    resolved_body: str,
) -> str:
    ordered = _order_keys_by_reading_position(eligible, resolved_body)
    keys_payload = [
        {"key": key, "current_value": value} for key, value in ordered
    ]
    return (
        "TONE TARGET:\n"
        f"Intent: {target_intent}\n"
        f"Emotion weights: {json.dumps(target_profile)}\n\n"
        "KEYS TO REWRITE (in reading order):\n"
        f"{json.dumps(keys_payload, indent=2)}\n\n"
        "INSTRUCTIONS:\n"
        "- These keys appear in sequence in the same email. Rewrite them as a "
        "coherent set — the tone shift must feel consistent across all keys, "
        "not independently optimised per key.\n"
        "- For each key, produce a rewrite aligned with the tone target while "
        "preserving the original meaning, approximate length, and any ##TOKEN## "
        "references exactly as they appear.\n"
        "- Do NOT append tone labels, annotations, or tags to values.\n"
        "- Do NOT copy the old value into new_value unchanged.\n"
        "- Return ONLY keys from the provided list.\n"
        "- Respond with valid JSON only — no preamble, no explanation, no markdown "
        'fences. A JSON array of objects with exactly two fields: "key" and '
        '"new_value".\n\n'
        "EXAMPLE OUTPUT FORMAT:\n"
        "[\n"
        '    {"key": "EN.PARAGRAPH_1", "new_value": "Rewritten prose here."},\n'
        '    {"key": "EN.SUBJECT", "new_value": "Rewritten subject here."}\n'
        "]"
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


def _strip_json_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _extract_agent_response_text(callback_context: CallbackContext) -> str | None:
    for event in reversed(callback_context.session.events):
        if event.author != "SuggestAgent":
            continue
        if not event.content or not event.content.parts:
            continue
        texts = [
            part.text
            for part in event.content.parts
            if hasattr(part, "text") and part.text
        ]
        if texts:
            return "".join(texts).strip()
    return None


def _finalize_suggest_rewrites(
    raw_response: str,
    eligible: dict[str, str],
    suggestion_id: str,
) -> dict[str, Any]:
    """Parse and validate SuggestAgent JSON rewrites for session state."""
    raw_items = _parse_llm_rewrites(_strip_json_fences(raw_response))
    accepted, discarded = _validate_llm_rewrites(raw_items, eligible)
    suggestions = [
        item
        for item in accepted
        if item["new_value"] != eligible.get(item["key"], "")
    ]
    payload: dict[str, Any] = {
        "suggestions": suggestions,
        "suggestion_id": suggestion_id,
        "discarded_keys": [asdict(d) for d in discarded],
    }
    if not suggestions:
        payload["message"] = "No valid tone rewrite keys were generated."
    return payload


async def suggest_tone_rewrite(target_intent: str, session_state: dict) -> dict[str, Any]:
    """Build the rewrite prompt and metadata for SuggestAgent to produce rewrites."""
    session_context = validate_session_context(session_state)

    if "tone_bearing_keys" not in session_state:
        return {
            "error": "missing_tone_bearing_keys",
            "message": "KeyClassifierAgent must run before SuggestAgent.",
        }
    eligible = dict(session_state["tone_bearing_keys"])
    if not eligible:
        return {"message": "No eligible keys found for tone rewriting."}

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

    suggestion_id = str(uuid.uuid4())
    ordered_keys = [
        key for key, _ in _order_keys_by_reading_position(eligible, resolution.resolved_body)
    ]
    rewrite_prompt = _build_llm_prompt(
        eligible, target_intent, target_profile, resolution.resolved_body
    )
    return {
        "rewrite_prompt": rewrite_prompt,
        "eligible_keys": ordered_keys,
        "target_emotions": target_profile,
        "baseline_emotions": baseline,
        "suggestion_id": suggestion_id,
        "instruction": _SUGGEST_AGENT_INSTRUCTION,
    }


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
            suggested = item.get("suggested_value", item.get("new_value", ""))
            normalized.append(
                ToneSuggestion(
                    key=item["key"],
                    current_value=item.get("current_value", ""),
                    suggested_value=suggested,
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

    snap_key = snapshot_key(session_context)
    existing_snapshot = await redis_client.hgetall(snap_key)
    snapshot_overwritten = bool(existing_snapshot)

    keys = [item.key for item in normalized]
    await capture_snapshot(keys, session_context, redis_client, graph)

    for item in normalized:
        await set_working_copy_value(item.key, item.suggested_value, session_state)

    return {
        "applied": len(normalized),
        "message": f"Applied {len(normalized)} tone rewrites.",
        "snapshot_overwritten": snapshot_overwritten,
    }


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
        return {
            "restored": 0,
            "message": "No tone suggestion snapshot found for this session.",
        }

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


async def _populate_eligible_keys(
    callback_context: CallbackContext,
) -> Content | None:
    """Populate session.state eligible_keys before the orchestrator LLM runs.

    Skips all DB and Redis calls if eligible_keys is already present and
    non-empty — prevents redundant round trips on follow-up turns.
    Returns None always; never short-circuits the agent.
    """
    state = callback_context.state.to_dict()
    if state.get("eligible_keys"):
        return None
    session_context = validate_session_context(state)
    pool = get_pool()
    graph = await build_resolution_graph(pool, session_context.template_name)
    resolution = await resolve_template(session_context)
    eligible, _ = await _build_reachable_eligible(
        graph, resolution, session_context, state
    )
    callback_context.state["eligible_keys"] = eligible
    return None


async def _classify_keys_tool(tool_context: ToolContext) -> dict[str, Any]:
    state = tool_context.state.to_dict()
    eligible_keys = state.get("eligible_keys", {})
    result = await classify_keys(eligible_keys, state)
    tool_context.state["tone_bearing_keys"] = result["tone_bearing"]
    tool_context.state["structural_keys"] = result["structural"]
    return result


async def _suggest_tone_rewrites_tool(
    target_intent: str, tool_context: ToolContext
) -> dict[str, Any]:
    result = await suggest_tone_rewrite(target_intent, tool_context.state.to_dict())
    if "rewrite_prompt" in result:
        tool_context.state["pending_suggest_rewrite"] = {
            "suggestion_id": result["suggestion_id"],
        }
    return result


async def _process_suggest_agent_response(
    callback_context: CallbackContext,
) -> Content | None:
    """Parse SuggestAgent JSON output and write validated suggestions to session state."""
    pending = callback_context.state.get("pending_suggest_rewrite")
    if not pending:
        return None

    raw_text = _extract_agent_response_text(callback_context)
    if not raw_text:
        callback_context.state.pop("pending_suggest_rewrite", None)
        return None

    eligible = dict(callback_context.state.get("tone_bearing_keys", {}))
    try:
        finalized = _finalize_suggest_rewrites(
            raw_text,
            eligible,
            pending["suggestion_id"],
        )
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Failed to parse SuggestAgent rewrite response",
            exc_info=True,
        )
        callback_context.state["suggestions"] = []
        callback_context.state.pop("pending_suggest_rewrite", None)
        return None

    callback_context.state["suggestions"] = finalized["suggestions"]
    callback_context.state["suggestion_id"] = finalized["suggestion_id"]
    if finalized.get("discarded_keys"):
        callback_context.state["discarded_keys"] = finalized["discarded_keys"]
    callback_context.state.pop("pending_suggest_rewrite", None)
    return None


async def _apply_tone_suggestions_tool(
    suggestions: list[dict], tool_context: ToolContext
) -> dict:
    state = tool_context.state.to_dict()
    suggestion_id = state.get("suggestion_id")
    if not suggestion_id:
        return {
            "error": "missing_suggestion_id",
            "message": "Cannot apply tone suggestions without a valid suggestion_id in session state.",
        }
    return await apply_tone_suggestions(suggestions, state)


async def _undo_tone_suggestions_tool(
    keys: list[str] | None, tool_context: ToolContext
) -> dict:
    return await undo_tone_suggestions(keys, tool_context.state.to_dict())


_TONE_SUGGESTION_DESCRIPTION = """
        Owns the full end-to-end tone improvement cycle for the loaded template.
        Maps natural language tone intent to GoEmotions target profiles, identifies
        eligible placeholder keys for rewriting, generates LLM-based rewrites,
        applies them immediately to the Redis working copy, and supports undo
        of the most recent suggestion batch via a pre-suggestion snapshot.
        """


def create_key_classifier_agent() -> LlmAgent:
    return LlmAgent(
        name="KeyClassifierAgent",
        model=get_llm_model("TONE_SUGGESTION"),
        description=(
            "Classifies eligible template keys into tone-bearing prose and "
            "structural chrome using deterministic heuristics and a single LLM call."
        ),
        instruction="""
        You are the Key Classifier Agent. Your only job is to call classify_keys
        to split eligible placeholder keys into tone-bearing copy and structural
        elements. You never rewrite values or write to Redis or PostgreSQL.
        """,
        tools=[_classify_keys_tool],
    )


def create_suggest_agent() -> LlmAgent:
    return LlmAgent(
        name="SuggestAgent",
        model=get_llm_model("TONE_SUGGESTION"),
        description=(
            "Generates tone rewrite suggestions for tone-bearing keys only, "
            "using GoEmotions baseline scoring and strict hallucination filtering."
        ),
        instruction="""
        You are the Suggest Agent. Call _suggest_tone_rewrites_tool with the user's
        tone intent. Read candidate keys exclusively from session.state tone_bearing_keys.
        Never apply changes — only return suggestions for user review.

        When _suggest_tone_rewrites_tool returns a payload containing rewrite_prompt:
        1. The keys in rewrite_prompt are ordered by their reading sequence in the
           email — treat them as a coherent set, not as independent strings.
        2. Reason over all keys together: the tone shift must feel consistent from
           the first key to the last, as the same recipient reads them in sequence.
        3. Emit your response as a JSON array only, with no preamble, no
           explanation, and no markdown fences. Each object must have exactly
           two fields: "key" (string) and "new_value" (string).
        4. Return ONLY keys from the eligible_keys list in the tool result.
        5. Do NOT copy the old value into new_value unchanged.
        6. Do NOT append tone labels, annotations, or comments to values.
        7. Do NOT call any other tool or delegate to any other agent.
        """,
        tools=[_suggest_tone_rewrites_tool],
        after_agent_callback=_process_suggest_agent_response,
    )


def create_apply_agent() -> LlmAgent:
    return LlmAgent(
        name="ApplyAgent",
        model=get_llm_model("TONE_SUGGESTION"),
        description=(
            "Applies confirmed tone suggestions after explicit user confirmation, "
            "capturing a pre-apply snapshot before any working copy writes."
        ),
        instruction="""
        You are the Apply Agent. Only run after the user explicitly confirms a
        suggestion batch. Call apply_tone_suggestions with the confirmed suggestions.
        session.state must contain a valid suggestion_id before you apply anything.
        """,
        tools=[_apply_tone_suggestions_tool],
    )


def create_undo_agent() -> LlmAgent:
    return LlmAgent(
        name="UndoAgent",
        model=get_llm_model("TONE_SUGGESTION"),
        description="Restores the working copy from the pre-apply tone snapshot.",
        instruction="""
        You are the Undo Agent. Call undo_tone_suggestions when the user wants to
        revert applied tone changes. If no snapshot exists, relay the returned
        message without raising an error.
        """,
        tools=[_undo_tone_suggestions_tool],
    )


KeyClassifierAgent = create_key_classifier_agent()
SuggestAgent = create_suggest_agent()
ApplyAgent = create_apply_agent()
UndoAgent = create_undo_agent()


def create_tone_suggestion_subagent() -> LlmAgent:
    return LlmAgent(
        name="ToneSuggestionSubagent",
        model=get_llm_model("TONE_SUGGESTION"),
        description=_TONE_SUGGESTION_DESCRIPTION,
        instruction="""
        You are the Tone Suggestion orchestrator. Delegate to specialist subagents
        in the correct order and never call their tools directly yourself.

        ## Suggest flow (strict order)
        1. Delegate to KeyClassifierAgent. eligible_keys is already populated in
           session.state before this instruction runs.
        2. KeyClassifierAgent populates tone_bearing_keys and structural_keys.
           KeyClassifierAgent MUST run before SuggestAgent.
        3. Delegate to SuggestAgent to generate rewrites from tone_bearing_keys only.
           SuggestAgent calls _suggest_tone_rewrites_tool, then emits JSON rewrites
           as its response. Validated suggestions and suggestion_id are written to
           session.state automatically after SuggestAgent completes.
        4. Present each suggestion with current and proposed values side by side.
        5. Wait for explicit user confirmation before any apply step.

        ## Apply flow
        6. Only after confirmation, delegate to ApplyAgent. ApplyAgent requires
           suggestion_id in session.state and captures a snapshot before writing.

        ## Undo flow
        7. Delegate to UndoAgent at any time when the user asks to undo tone changes.

        ## Behaviour rules
        - Never rewrite structural keys — KeyClassifierAgent filters them out.
        - Never apply suggestions without user confirmation and a valid suggestion_id.
        - Snapshot writes MUST complete before any working copy writes during apply.
        - Never write to PostgreSQL.
        - When a prior undo snapshot is overwritten during apply, inform the user.
        """,
        before_agent_callback=_populate_eligible_keys,
        sub_agents=[KeyClassifierAgent, SuggestAgent, ApplyAgent, UndoAgent],
        tools=[],
    )


ToneSuggestionSubagent = create_tone_suggestion_subagent()
