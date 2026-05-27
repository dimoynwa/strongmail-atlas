"""Validation tests for tone suggestion key eligibility and graph gates."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from template_assistant.context import validate_session_context
from template_assistant.services import working_copy_key
from template_assistant.context import MissingClassificationError
from template_assistant.subagents.tone_suggestion_subagent import (
    KeyNotInGraphError,
    apply_tone_suggestions,
    evaluate_eligibility,
    finalize_rewrites,
    is_eligible_for_rewrite,
    suggest_tone_rewrite,
)
from template_assistant.tests.test_resolution_subagent import _seed_template


LANG = "EN-US"
BRAND = "BRANDX"


def _eligible_key(name: str) -> str:
    return f"{LANG}.{name}"


def _long_text(suffix: str = "") -> str:
    return f"This is a long enough placeholder value for tone rewrite testing.{suffix}"


# --- T003: is_eligible_for_rewrite ---


def test_eligible_with_lang_prefix():
    assert is_eligible_for_rewrite(_eligible_key("PARAGRAPH_1"), _long_text(), LANG, BRAND)


def test_eligible_with_brand_prefix():
    assert is_eligible_for_rewrite(f"{BRAND}.PARAGRAPH_1", _long_text(), LANG, BRAND)


def test_eligible_with_generic_prefix():
    assert is_eligible_for_rewrite("GENERIC.PARAGRAPH_1", _long_text(), LANG, BRAND)


def test_ineligible_wrong_prefix():
    assert is_eligible_for_rewrite("FR.PARAGRAPH_1", _long_text(), LANG, BRAND) is False
    result = evaluate_eligibility("FR.PARAGRAPH_1", _long_text(), LANG, BRAND)
    assert result.reason == "wrong_prefix"


def test_ineligible_sm_rule():
    assert is_eligible_for_rewrite("SM_RULE_FOO", _long_text(), LANG, BRAND) is False
    assert evaluate_eligibility("SM_RULE_FOO", _long_text(), LANG, BRAND).reason == "sm_rule"


def test_ineligible_url_value():
    value = "https://example.com/a-very-long-path-that-is-not-short"
    assert is_eligible_for_rewrite(_eligible_key("LINK"), value, LANG, BRAND) is False
    assert evaluate_eligibility(_eligible_key("LINK"), value, LANG, BRAND).reason == "url"


def test_ineligible_colour_hex():
    assert is_eligible_for_rewrite(_eligible_key("COLOR"), "#FFFFFF", LANG, BRAND) is False
    assert evaluate_eligibility(_eligible_key("COLOR"), "#FFFFFF", LANG, BRAND).reason == "colour_code"


def test_ineligible_colour_rgb():
    assert is_eligible_for_rewrite(_eligible_key("COLOR"), "rgb(255, 0, 0)", LANG, BRAND) is False


def test_ineligible_numeric():
    assert is_eligible_for_rewrite(_eligible_key("COUNT"), "123456789012345678901", LANG, BRAND) is False
    assert evaluate_eligibility(_eligible_key("COUNT"), "123456789012345678901", LANG, BRAND).reason == "numeric"


def test_ineligible_too_short():
    assert is_eligible_for_rewrite(_eligible_key("TITLE"), "Sho", LANG, BRAND) is False
    assert evaluate_eligibility(_eligible_key("TITLE"), "Sho", LANG, BRAND).reason == "too_short"


def test_bare_key_without_dot_is_eligible():
    """Unprefixed canonical keys (test fixtures) remain eligible when other rules pass."""
    assert is_eligible_for_rewrite("GREETING", _long_text(), LANG, BRAND)


# --- T004/T005: SuggestAgent rewrite validation ---


@pytest.mark.asyncio
async def test_suggest_tone_rewrite_discards_hallucinated_keys(db_pool, redis_client, session_state):
    key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{key}##</p>",
        kv_pairs={key: _long_text()},
    )
    tone_bearing = {key: _long_text()}

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        tool_result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)

    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class _FakeState:
        data: dict[str, Any] = field(default_factory=dict)

        def to_dict(self) -> dict[str, Any]:
            return self.data

        def __setitem__(self, k: str, v: Any) -> None:
            self.data[k] = v

    @dataclass
    class _FakeCtx:
        state: _FakeState

    fin_ctx = _FakeCtx(
        state=_FakeState(
            {
                **session_state,
                "eligible_keys": tone_bearing,
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    result = await finalize_rewrites(
        [
            {"key": key, "new_value": _long_text(" Rewritten.")},
            {"key": "BODY", "new_value": "Hallucinated body text that is definitely long enough."},
        ],
        fin_ctx,  # type: ignore[arg-type]
    )

    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["key"] == key
    assert fin_ctx.state.data.get("discarded_keys")


@pytest.mark.asyncio
async def test_suggest_tone_rewrite_empty_when_only_hallucinated_keys(
    db_pool, redis_client, session_state
):
    key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{key}##</p>",
        kv_pairs={key: _long_text()},
    )
    tone_bearing = {key: _long_text()}

    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.get_classifier",
        return_value=lambda _text: [{"label": "joy", "score": 0.5}],
    ):
        tool_result = await suggest_tone_rewrite("warmer", tone_bearing, session_state)

    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class _FakeState:
        data: dict[str, Any] = field(default_factory=dict)

        def to_dict(self) -> dict[str, Any]:
            return self.data

        def __setitem__(self, k: str, v: Any) -> None:
            self.data[k] = v

    @dataclass
    class _FakeCtx:
        state: _FakeState

    fin_ctx = _FakeCtx(
        state=_FakeState(
            {
                **session_state,
                "eligible_keys": tone_bearing,
                "suggestion_id": tool_result["suggestion_id"],
            }
        )
    )
    result = await finalize_rewrites(
        [
            {"key": "BODY", "new_value": "Hallucinated body text that is definitely long enough."},
            {"key": "SUBJECT", "new_value": "Hallucinated subject line that is long enough."},
        ],
        fin_ctx,  # type: ignore[arg-type]
    )

    assert result["suggestions"] == []
    assert result["discarded"] == 2


# --- T010-T012: apply_tone_suggestions graph validation ---


@pytest.mark.asyncio
async def test_apply_raises_key_not_in_graph_error(db_pool, redis_client, session_state):
    key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{key}##</p>",
        kv_pairs={key: _long_text()},
    )
    suggestions = [
        {
            "key": "BODY",
            "current_value": "",
            "suggested_value": _long_text(" Invalid."),
            "predicted_delta": {},
        }
    ]
    with pytest.raises(KeyNotInGraphError) as exc_info:
        await apply_tone_suggestions(suggestions, session_state)
    err = exc_info.value
    assert err.invalid_keys == ["BODY"]
    assert err.valid_keys_not_written == []


@pytest.mark.asyncio
async def test_apply_prevents_partial_writes(db_pool, redis_client, session_state):
    valid_key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{valid_key}##</p>",
        kv_pairs={valid_key: _long_text()},
    )
    ctx = validate_session_context(session_state)
    suggestions = [
        {
            "key": valid_key,
            "current_value": _long_text(),
            "suggested_value": _long_text(" Updated."),
            "predicted_delta": {},
        },
        {
            "key": "SUBJECT",
            "current_value": "",
            "suggested_value": _long_text(" Invalid."),
            "predicted_delta": {},
        },
    ]
    with pytest.raises(KeyNotInGraphError) as exc_info:
        await apply_tone_suggestions(suggestions, session_state)
    err = exc_info.value
    assert "SUBJECT" in err.invalid_keys
    assert valid_key in err.valid_keys_not_written
    wc = await redis_client.hgetall(working_copy_key(ctx))
    assert valid_key not in wc and valid_key.upper() not in wc


@pytest.mark.asyncio
async def test_apply_succeeds_when_all_keys_valid(db_pool, redis_client, session_state):
    key = _eligible_key("PARAGRAPH_1")
    await _seed_template(
        db_pool,
        "TestTemplate",
        html=f"<p>##{key}##</p>",
        kv_pairs={key: _long_text()},
    )
    ctx = validate_session_context(session_state)
    new_value = _long_text(" Applied.")
    suggestions = [
        {
            "key": key,
            "current_value": _long_text(),
            "suggested_value": new_value,
            "predicted_delta": {"joy": 0.1},
        }
    ]
    result = await apply_tone_suggestions(suggestions, session_state)
    assert result["applied"] == 1
    wc = await redis_client.hgetall(working_copy_key(ctx))
    assert wc[key.upper()] == new_value
