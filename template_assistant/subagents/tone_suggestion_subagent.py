from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from template_assistant.llm import get_llm_model

from shared.db import get_pool
from shared.redis_client import get_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import resolve_body
from template_assistant.context import (
    MissingClassificationError,
    SessionContext,
    SuggestionIdMismatchError,
    build_resolution_context,
    validate_session_context,
)
from template_assistant.ml.goemotions import get_classifier, scores_from_pipeline_result
from template_assistant.models import ToneSuggestion
from template_assistant.services import (
    SNAPSHOT_NONE_SENTINEL,
    build_tone_eligible_keys,
    fetch_template_bodies,
    resolve_template,
    select_reachability_body,
    snapshot_key,
    working_copy_key,
)
from template_assistant.subagents.working_copy_subagent import get_working_copy, set_working_copy_value
from template_assistant.tone_profiles import lookup_tone_profile
from template_assistant.utils.text import extract_plain_text

logger = logging.getLogger(__name__)

_SUGGEST_AGENT_INSTRUCTION = (
    "You are generating tone rewrites. The keys in rewrite_prompt are "
    "ordered by their reading sequence in the email — rewrite them as a "
    "coherent set, not independently. Return JSON only: a list of objects "
    "with 'key' and 'new_value' fields. Return ONLY keys from eligible_keys. "
    "Do not annotate, append labels, or copy values unchanged."
)

_SNAPSHOT_OVERWRITE_WARNING = (
    "Note: applying these suggestions will replace the undo snapshot from "
    "your previous suggestion batch. You will not be able to undo that earlier "
    "batch individually after confirming."
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
    "LOGO",
    "ICON",
    "COLOR",
    "COLOUR",
    "BACKGROUND",
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
    del resolution
    wc = await get_working_copy(session_state)
    eligible = await build_tone_eligible_keys(
        session_context, graph=graph, working_copy=wc
    )
    pool = get_pool()
    redis_client = get_redis()
    html_body, text_body = await fetch_template_bodies(
        pool,
        session_context.template_name,
        session_context.lang_local,
        session_context.param_cust_brand,
    )
    body = select_reachability_body(html_body, text_body)
    if not body.strip():
        return eligible, []

    context = build_resolution_context(session_context)
    accumulated_keys: set[str] = set()
    await resolve_body(
        pool,
        redis_client,
        graph,
        body,
        context,
        session_context.session_id,
        session_context.template_name,
        accumulated_keys=accumulated_keys,
    )
    reachable = accumulated_keys
    ineligible_keys: list[str] = []
    for key, graph_value in graph.items():
        if key not in reachable or key in eligible:
            continue
        value = wc.get(key, graph_value)
        result = evaluate_eligibility(
            key,
            value,
            session_context.lang_local,
            session_context.param_cust_brand,
        )
        if not result.eligible:
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


def _normalize_rewrite_items(rewrites: Any) -> list[dict[str, str]]:
    """Normalize rewrite input from tool callers or raw JSON strings."""
    if isinstance(rewrites, str):
        rewrites = _parse_llm_rewrites(_strip_json_fences(rewrites))
    if not isinstance(rewrites, list):
        raise ValueError("Rewrites must be a JSON list")
    normalized: list[dict[str, str]] = []
    for item in rewrites:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        new_value = item.get("new_value")
        if isinstance(key, str) and isinstance(new_value, str):
            normalized.append({"key": key, "new_value": new_value})
    return normalized


async def load_eligible_keys(
    force_reload: bool,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Load eligible keys into session state, with optional cache bypass."""
    state = tool_context.state.to_dict()
    if not force_reload and state.get("eligible_keys"):
        eligible = state["eligible_keys"]
        return {"eligible_keys": eligible, "total": len(eligible)}

    if force_reload and "eligible_keys" in tool_context.state.to_dict():
        tool_context.state["eligible_keys"] = {}

    try:
        session_context = validate_session_context(state)
        pool = get_pool()
        graph = await build_resolution_graph(pool, session_context.template_name)
        wc = await get_working_copy(state)
        eligible = await build_tone_eligible_keys(
            session_context, graph=graph, working_copy=wc
        )
        tool_context.state["eligible_keys"] = eligible
        return {"eligible_keys": eligible, "total": len(eligible)}
    except Exception as exc:
        logger.warning("Failed to load eligible keys", exc_info=True)
        return {
            "error": type(exc).__name__,
            "message": f"Could not load eligible keys: {exc}",
        }


async def finalize_rewrites(
    rewrites: list[dict] | str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Validate LLM rewrites and write suggestions to session state."""
    state = tool_context.state.to_dict()
    eligible = dict(state.get("eligible_keys", {}))
    suggestion_id = state.get("suggestion_id")
    if not suggestion_id:
        return {
            "error": "missing_suggestion_id",
            "message": "Cannot finalize rewrites without a suggestion_id in session state.",
        }

    try:
        raw_items = _normalize_rewrite_items(rewrites)
    except (json.JSONDecodeError, ValueError):
        return {
            "error": "parse_error",
            "message": "SuggestAgent returned invalid JSON.",
        }

    accepted, discarded = _validate_llm_rewrites(raw_items, eligible)
    suggestions = [
        {
            "key": item["key"],
            "old_value": eligible.get(item["key"], ""),
            "new_value": item["new_value"],
            "suggestion_id": suggestion_id,
        }
        for item in accepted
        if item["new_value"] != eligible.get(item["key"], "")
    ]

    tool_context.state["suggestions"] = suggestions
    if discarded:
        tool_context.state["discarded_keys"] = [asdict(d) for d in discarded]

    return {
        "accepted": len(suggestions),
        "discarded": len(discarded) + (len(accepted) - len(suggestions)),
        "suggestions": suggestions,
    }


async def suggest_tone_rewrite(
    target_intent: str,
    tone_bearing_keys: dict[str, str] | None,
    session_state: dict,
) -> dict[str, Any]:
    """Build the rewrite prompt and metadata for SuggestAgent to produce rewrites."""
    if tone_bearing_keys is None:
        raise MissingClassificationError()
    if not tone_bearing_keys:
        return {"message": "No eligible keys found for tone rewriting."}

    session_context = validate_session_context(session_state)
    eligible = dict(tone_bearing_keys)

    target_profile = lookup_tone_profile(target_intent)
    if target_profile is None:
        target_profile = {"optimism": 0.5, "approval": 0.5}

    pool = get_pool()
    redis_client = get_redis()
    graph = await build_resolution_graph(pool, session_context.template_name)
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

    snap_key = snapshot_key(session_context)
    existing_snapshot = await redis_client.hgetall(snap_key)
    snapshot_overwritten = bool(existing_snapshot)
    await capture_snapshot(ordered_keys, session_context, redis_client, graph)
    snapshot_saved = bool(ordered_keys)

    rewrite_prompt = _build_llm_prompt(
        eligible, target_intent, target_profile, resolution.resolved_body
    )
    return {
        "rewrite_prompt": rewrite_prompt,
        "eligible_keys": ordered_keys,
        "target_emotions": target_profile,
        "baseline_emotions": baseline,
        "suggestion_id": suggestion_id,
        "snapshot_saved": snapshot_saved,
        "snapshot_overwritten": snapshot_overwritten,
        "instruction": _SUGGEST_AGENT_INSTRUCTION,
    }


async def apply_tone_suggestions(
    suggestions: list[dict[str, Any]] | list[ToneSuggestion],
    session_state: dict,
) -> dict:
    """Write confirmed suggestions to the working copy."""
    session_context = validate_session_context(session_state)
    expected_suggestion_id = session_state.get("suggestion_id")

    normalized: list[ToneSuggestion] = []
    for item in suggestions:
        if isinstance(item, ToneSuggestion):
            normalized.append(item)
            continue
        item_suggestion_id = item.get("suggestion_id")
        if expected_suggestion_id and item_suggestion_id:
            if item_suggestion_id != expected_suggestion_id:
                raise SuggestionIdMismatchError(expected_suggestion_id, item_suggestion_id)
        suggested = item.get("suggested_value", item.get("new_value", ""))
        normalized.append(
            ToneSuggestion(
                key=item["key"],
                current_value=item.get("current_value", item.get("old_value", "")),
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

    for item in normalized:
        await set_working_copy_value(item.key, item.suggested_value, session_state)

    return {
        "applied": len(normalized),
        "message": f"Applied {len(normalized)} tone rewrites.",
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
            "snapshot_cleared": False,
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

    snapshot_cleared = keys is None
    if snapshot_cleared:
        await redis_client.delete(snap_key)

    return {
        "restored": restored,
        "message": f"Restored {restored} placeholder(s).",
        "snapshot_cleared": snapshot_cleared,
    }


async def _classify_keys_tool(tool_context: ToolContext) -> dict[str, Any]:
    state = tool_context.state.to_dict()
    eligible_keys = state.get("eligible_keys", {})
    return await classify_keys(eligible_keys, state)


async def _suggest_tone_rewrites_tool(
    target_intent: str,
    tone_bearing_keys: dict[str, str] | None,
    tool_context: ToolContext,
) -> dict[str, Any]:
    if tone_bearing_keys is None:
        raise MissingClassificationError()
    result = await suggest_tone_rewrite(
        target_intent,
        tone_bearing_keys,
        tool_context.state.to_dict(),
    )
    if "suggestion_id" in result:
        tool_context.state["suggestion_id"] = result["suggestion_id"]
    return result


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
    for item in suggestions:
        item_suggestion_id = item.get("suggestion_id")
        if item_suggestion_id and item_suggestion_id != suggestion_id:
            raise SuggestionIdMismatchError(suggestion_id, item_suggestion_id)
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
        tone intent and the tone_bearing_keys dict passed explicitly by the orchestrator.
        Never apply changes — only produce suggestions for user review.

        When _suggest_tone_rewrites_tool returns a payload containing rewrite_prompt:
        1. The keys in rewrite_prompt are ordered by their reading sequence in the
        email — treat them as a coherent set, not as independent strings.
        2. Reason over all keys together: the tone shift must feel consistent from
        the first key to the last, as the same recipient reads them in sequence.
        3. Generate a JSON array of objects with exactly two fields per object:
        "key" (string) and "new_value" (string).
        4. Return ONLY keys from the eligible_keys list in the tool result.
        5. Do NOT copy the old value into new_value unchanged.
        6. Do NOT append tone labels, annotations, or comments to values.
        7. PRESERVE THE ORIGINAL MESSAGE PURPOSE AND MEANING. The rewrite must
        communicate the same factual content, call-to-action, and intent as
        the original — only the voice, tone, and phrasing may change. Do not
        add new information, omit required details, or change what the email
        is asking the recipient to do.
        8. Write in the SAME PERSON AND REGISTER as the original (first person,
        second person, etc.). If the original addresses "you", the rewrite
        must too.
        9. After generating JSON rewrites, call finalize_rewrites(rewrites=[...])
        with the full list as the parameter. Do not emit the JSON as response
        text. Do not proceed until finalize_rewrites has been called.
        10. Do NOT call any other tool or delegate to any other agent.
        """,
        tools=[_suggest_tone_rewrites_tool, finalize_rewrites],
    )


def create_apply_agent() -> LlmAgent:
    return LlmAgent(
        name="ApplyAgent",
        model=get_llm_model("TONE_SUGGESTION"),
        description=(
            "Applies confirmed tone suggestions after explicit user confirmation."
        ),
        instruction="""
        You are the Apply Agent. You are only invoked when the user has confirmed tone changes.
        You MUST immediately call the tool named `_apply_tone_suggestions_tool` using the list 
        of confirmed suggestions passed by the orchestrator.
        
        Do not explain what you are going to do. Execute `_apply_tone_suggestions_tool` 
        and return the success or failure message directly to the user.
        """,
        tools=[_apply_tone_suggestions_tool],
    )


def create_undo_agent() -> LlmAgent:
    return LlmAgent(
        name="UndoAgent",
        model=get_llm_model("TONE_SUGGESTION"),
        description="Restores the working copy from the pre-suggestion tone snapshot.",
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
        instruction=f"""
        You are the Tone Suggestion orchestrator. Delegate to specialist subagents
        in the correct order and never call their tools directly yourself except
        load_eligible_keys.

        ## Suggest flow (strict order)
        Step 0: Call load_eligible_keys(force_reload=True). If the result contains an
        "error" key, relay the "message" value to the user as a plain sentence and stop.
        Step 1: Delegate to KeyClassifierAgent.
        Step 2: Read tone_bearing_keys from KeyClassifierAgent's tool return value.
        Pass it explicitly to SuggestAgent via _suggest_tone_rewrites_tool's parameter.
        Step 3: After SuggestAgent completes, read session.state["suggestions"] and
        session.state["suggestion_id"].
        Step 4: If snapshot_overwritten is true, prepend this warning: "{_SNAPSHOT_OVERWRITE_WARNING}"
        Step 5: Present each suggestion (Old vs New) side by side.
        Step 6: Wait for explicit user confirmation before any apply step.

        ## Apply flow (Handling Confirmations)
        Step 7: If the user confirms ALL suggestions, delegate to ApplyAgent with the full list.
        Step 8: PARTIAL CONFIRMATION: If the user asks to apply ONLY specific keys (e.g., "Apply only X and Y"), you MUST filter the session.state["suggestions"] list to include ONLY those keys, and pass that filtered list to the ApplyAgent. Do not ask for confirmation again.
        Step 9: When a user confirms, you MUST immediately delegate to ApplyAgent. Do NOT reply with phrases like "I will apply this" or "Changes will be applied" without triggering the ApplyAgent.

        ## Undo flow
        Step 10: Delegate to UndoAgent at any time when the user asks to undo tone changes.

        ## Behaviour rules
        - Never rewrite structural keys.
        - Never apply suggestions without user confirmation and a valid suggestion_id.
        - Never write to PostgreSQL.
        """,
        sub_agents=[KeyClassifierAgent, SuggestAgent, ApplyAgent, UndoAgent],
        tools=[load_eligible_keys],
    )


ToneSuggestionSubagent = create_tone_suggestion_subagent()
