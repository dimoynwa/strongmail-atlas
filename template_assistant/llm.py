from __future__ import annotations

import os
from typing import Union

from dotenv import load_dotenv

load_dotenv()

# LiteLLM reads this at import time; set before any litellm/google-adk import when possible.
os.environ.setdefault("LITELLM_MODIFY_PARAMS", "true")
os.environ.setdefault("LITELLM_LOG", "WARNING")

from google.adk.models.lite_llm import LiteLlm

ModelSpec = Union[LiteLlm, str]

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
BEDROCK_MODEL = os.getenv(
    "BEDROCK_MODEL", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
BEDROCK_MODEL_NOVA_PRO = os.getenv("BEDROCK_MODEL_NOVA_PRO", "eu.amazon.nova-pro-v1:0")

# --- Qwen (OpenAI-compatible server) — also used by ``adk_agents.model_factory`` -----------------

_DEFAULT_QWEN_MODEL = "openai//models/Qwen/Qwen3.5-27B"
_DEFAULT_QWEN_BASE = "http://gpuserver2.neterra.skrill.net:8010/v1"
_DEFAULT_QWEN_KEY = "fake"

def qwen_litellm_model() -> str:
    return os.getenv("QWEN_LITELLM_MODEL", _DEFAULT_QWEN_MODEL)


def qwen_api_base() -> str:
    return os.getenv("QWEN_BASE_URL", _DEFAULT_QWEN_BASE)


def qwen_api_key() -> str:
    return os.getenv("QWEN_API_KEY", _DEFAULT_QWEN_KEY)

def _default_model_provider() -> str:
    return os.getenv("TEMPLATE_ASSISTANT_MODEL", os.getenv("ADK_AGENT_MODEL", "bedrock"))


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _configure_litellm() -> None:
    try:
        import litellm
    except ImportError:
        return

    litellm.modify_params = _env_truthy("LITELLM_MODIFY_PARAMS", "true")
    if _env_truthy("LITELLM_SUPPRESS_DEBUG_INFO", "true"):
        litellm.suppress_debug_info = True


def _bedrock_litellm_model_id(raw: str) -> str:
    model_id = (raw or "").strip()
    if not model_id:
        return model_id
    lowered = model_id.lower()
    if lowered.startswith(("bedrock/", "anthropic/", "vertex_ai/")):
        return model_id
    return f"bedrock/{model_id}"


def _resolve_provider(provider: str) -> ModelSpec:
    _configure_litellm()

    if provider == "qwen":
        return LiteLlm(
            model=qwen_litellm_model(),
            api_base=qwen_api_base(),
            api_key=qwen_api_key(),
            kwargs={"enable_thinking": False},
        )

    if provider == "gemini":
        return GEMINI_MODEL

    if provider == "ollama":
        return LiteLlm(
            model=f"openai/{OLLAMA_MODEL}",
            api_base=OLLAMA_BASE_URL,
            api_key=OLLAMA_API_KEY,
        )

    if provider == "bedrock":
        return LiteLlm(
            model=_bedrock_litellm_model_id(BEDROCK_MODEL),
            max_tokens=4096,
        )

    if provider == "bedrock_nova_pro":
        return LiteLlm(
            model=_bedrock_litellm_model_id(BEDROCK_MODEL_NOVA_PRO),
            max_tokens=4096,
        )

    if provider == "openai":
        return LiteLlm(
            model="openai/gpt-4o"
        )

    raise ValueError(
        f"Unsupported model provider {provider!r}. "
        "Use one of: qwen, gemini, ollama, bedrock, bedrock_nova_pro, openai."
    )


def get_llm_model(agent_key: str | None = None) -> ModelSpec:
    """Return the ADK model spec for an agent, defaulting to Bedrock."""
    env_name = f"TEMPLATE_ASSISTANT_{agent_key}_MODEL" if agent_key else None
    provider = (
        (os.getenv(env_name) if env_name else None)
        or _default_model_provider()
    ).strip().lower()
    return _resolve_provider(provider)
