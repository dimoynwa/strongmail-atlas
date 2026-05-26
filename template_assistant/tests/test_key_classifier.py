"""Tests for the two-stage tone key classifier."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from template_assistant.subagents.tone_suggestion_subagent import (
    _apply_structural_heuristics,
    _classify_keys_tool,
    classify_keys,
    set_classifier_llm_fn,
)


@dataclass
class FakeToolState:
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class FakeToolContext:
    state: FakeToolState


def _long_prose(suffix: str = "") -> str:
    return (
        "We are delighted to welcome you to our platform and hope you enjoy "
        f"everything we have prepared for you today.{suffix}"
    )


@pytest.fixture(autouse=True)
def reset_classifier_llm():
    set_classifier_llm_fn(None)
    yield
    set_classifier_llm_fn(None)


@pytest.mark.asyncio
async def test_stage1_structural_suffix():
    assert _apply_structural_heuristics("EN.LOGO_URL") is True
    result = await classify_keys(
        {"EN.LOGO_URL": "https://example.com/logo.png"},
        {},
    )
    assert "EN.LOGO_URL" in result["structural"]
    assert result["stage1_structural_count"] == 1
    assert result["tone_bearing_count"] == 0


@pytest.mark.asyncio
async def test_stage1_structural_substring():
    assert _apply_structural_heuristics("EN.FOOTER_COPYRIGHT") is True
    result = await classify_keys(
        {"EN.FOOTER_COPYRIGHT": _long_prose()},
        {},
    )
    assert "EN.FOOTER_COPYRIGHT" in result["structural"]
    assert result["stage1_structural_count"] == 1


@pytest.mark.asyncio
async def test_stage1_tone_bearing():
    assert _apply_structural_heuristics("EN.PARAGRAPH_1") is False

    async def fail_if_called(_prompt: str) -> str:
        raise AssertionError("LLM should not be called for Stage 1 structural keys only")

    set_classifier_llm_fn(fail_if_called)
    result = await classify_keys({"EN.PARAGRAPH_1": _long_prose()}, {})
    assert result["stage1_structural_count"] == 0
    assert "EN.PARAGRAPH_1" not in result["structural"]


@pytest.mark.asyncio
async def test_stage2_llm_classification():
    async def stub_llm(_prompt: str) -> str:
        return json.dumps([{"key": "EN.PARAGRAPH_1", "role": "tone"}])

    set_classifier_llm_fn(stub_llm)
    result = await classify_keys({"EN.PARAGRAPH_1": _long_prose()}, {})
    assert "EN.PARAGRAPH_1" in result["tone_bearing"]
    assert result["tone_bearing_count"] == 1
    assert result["stage2_structural_count"] == 0


@pytest.mark.asyncio
async def test_stage2_hallucinated_key_discarded():
    async def stub_llm(_prompt: str) -> str:
        return json.dumps(
            [
                {"key": "EN.PARAGRAPH_1", "role": "tone"},
                {"key": "EN.PHANTOM_KEY", "role": "tone"},
            ]
        )

    set_classifier_llm_fn(stub_llm)
    result = await classify_keys({"EN.PARAGRAPH_1": _long_prose()}, {})
    assert "EN.PHANTOM_KEY" not in result["tone_bearing"]
    assert "EN.PHANTOM_KEY" not in result["structural"]


@pytest.mark.asyncio
async def test_stage2_fallback_on_failure():
    async def failing_llm(_prompt: str) -> str:
        raise RuntimeError("LLM unavailable")

    set_classifier_llm_fn(failing_llm)
    with patch(
        "template_assistant.subagents.tone_suggestion_subagent.logger"
    ) as mock_logger:
        result = await classify_keys({"EN.PARAGRAPH_1": _long_prose()}, {})
    assert "EN.PARAGRAPH_1" in result["tone_bearing"]
    mock_logger.warning.assert_called()


@pytest.mark.asyncio
async def test_classify_keys_empty_input():
    llm_called = False

    async def track_llm(_prompt: str) -> str:
        nonlocal llm_called
        llm_called = True
        return "[]"

    set_classifier_llm_fn(track_llm)
    result = await classify_keys({}, {})
    assert result["tone_bearing_count"] == 0
    assert result["stage1_structural_count"] == 0
    assert llm_called is False


@pytest.mark.asyncio
async def test_classify_keys_all_structural():
    llm_called = False

    async def track_llm(_prompt: str) -> str:
        nonlocal llm_called
        llm_called = True
        return "[]"

    set_classifier_llm_fn(track_llm)
    result = await classify_keys(
        {
            "EN.LOGO_URL": "https://example.com/logo.png",
            "EN.FOOTER_COPYRIGHT": _long_prose(),
        },
        {},
    )
    assert result["tone_bearing_count"] == 0
    assert result["stage1_structural_count"] == 2
    assert llm_called is False


@pytest.mark.asyncio
async def test_state_keys_written():
    async def stub_llm(_prompt: str) -> str:
        return json.dumps([{"key": "EN.PARAGRAPH_1", "role": "tone"}])

    set_classifier_llm_fn(stub_llm)
    state = FakeToolState(
        {
            "eligible_keys": {
                "EN.PARAGRAPH_1": _long_prose(),
                "EN.LOGO_URL": "https://example.com/logo.png",
            }
        }
    )
    ctx = FakeToolContext(state=state)
    await _classify_keys_tool(ctx)  # type: ignore[arg-type]
    assert "tone_bearing_keys" in state.data
    assert "structural_keys" in state.data
    assert "EN.PARAGRAPH_1" in state.data["tone_bearing_keys"]
    assert "EN.LOGO_URL" in state.data["structural_keys"]
