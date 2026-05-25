import pytest
from unittest.mock import MagicMock, patch

from template_assistant.llm import get_llm_model


def test_default_provider_is_bedrock():
    with patch.dict(
        "os.environ",
        {"TEMPLATE_ASSISTANT_MODEL": "bedrock", "BEDROCK_MODEL": "eu.test-model"},
        clear=False,
    ):
        model = get_llm_model()
    assert hasattr(model, "model")
    assert str(model.model).startswith("bedrock/")


def test_gemini_provider_returns_string():
    with patch.dict(
        "os.environ",
        {"TEMPLATE_ASSISTANT_MODEL": "gemini", "GEMINI_MODEL": "gemini-2.5-flash-lite"},
        clear=False,
    ):
        assert get_llm_model() == "gemini-2.5-flash-lite"


def test_per_agent_override():
    with patch.dict(
        "os.environ",
        {
            "TEMPLATE_ASSISTANT_MODEL": "bedrock",
            "TEMPLATE_ASSISTANT_ROOT_MODEL": "gemini",
            "GEMINI_MODEL": "gemini-2.5-flash-lite",
        },
        clear=False,
    ):
        assert get_llm_model("ROOT") == "gemini-2.5-flash-lite"
