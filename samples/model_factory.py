from typing import Union

import os

from dotenv import load_dotenv
from litellm import max_tokens

load_dotenv()

# Best-effort before any google-adk / litellm import (e.g. ``apps/resolve_app`` imports Runner first).
os.environ.setdefault("LITELLM_MODIFY_PARAMS", "true")
os.environ.setdefault("LITELLM_LOG", "WARNING")

from google.adk.models.lite_llm import LiteLlm


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


try:
    import litellm
except ImportError:
    pass
else:
    # Must set on the module after import: litellm may already have been imported (e.g. via
    # ``google.adk.runners``) before this file ran, so ``LITELLM_MODIFY_PARAMS`` was read as false.
    # Bedrock Converse needs ``modify_params`` to insert dummy assistant turns between user/tool
    # blocks (see litellm factory BedrockConverseMessagesProcessor).
    litellm.modify_params = _env_truthy("LITELLM_MODIFY_PARAMS", "true")
    if _env_truthy("LITELLM_SUPPRESS_DEBUG_INFO", "true"):
        litellm.suppress_debug_info = True

from strongmail.template_rag.litellm_providers import (
    qwen_api_base,
    qwen_api_key,
    qwen_litellm_model,
)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4")  # default model
QWEN_BASE_URL = qwen_api_base()
QWEN_API_KEY = qwen_api_key()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0")

# When a per-agent ``*_AGENT_MODEL`` env var is unset, use this (qwen | gemini | ollama | bedrock).
DEFAULT_ADK_MODEL = os.getenv("ADK_AGENT_MODEL", "bedrock")
# Inference profile / model id (no ``bedrock/`` prefix required; see ``bedrock_litellm_model``).
BEDROCK_MODEL_NOVA_PRO = os.getenv(
    "BEDROCK_MODEL_NOVA_PRO", "eu.amazon.nova-pro-v1:0"
)


def _bedrock_litellm_model_id(raw: str) -> str:
    """Use explicit ``bedrock/`` provider prefix for LiteLLM (inference profile or model id)."""
    s = (raw or "").strip()
    if not s:
        return s
    low = s.lower()
    if low.startswith("bedrock/") or low.startswith("anthropic/") or low.startswith(
        "vertex_ai/"
    ):
        return s
    return f"bedrock/{s}"


def get_model(model_name: str) -> Union[LiteLlm, str]:
    if model_name == "qwen":
        return LiteLlm(
            model=qwen_litellm_model(),
            api_base=qwen_api_base(),
            api_key=qwen_api_key(),
            kwargs={"enable_thinking": False},
        )

    elif model_name == "gemini":
        return GEMINI_MODEL

    elif model_name == "ollama":
        return LiteLlm(
            model=f"openai/{OLLAMA_MODEL}",  # important format
            api_base=OLLAMA_BASE_URL,
            api_key=OLLAMA_API_KEY,
        )

    elif model_name == "bedrock":
        import litellm
        litellm.modify_params = True
        return LiteLlm(
            model=_bedrock_litellm_model_id(BEDROCK_MODEL),
            max_tokens=4096,
        )

    elif model_name == "bedrock_nova_pro":
        import litellm
        litellm.modify_params = True
        
        return LiteLlm(
            model=_bedrock_litellm_model_id(BEDROCK_MODEL_NOVA_PRO),
            max_tokens=4096,
        )
    else:
        raise ValueError(f"Model {model_name} not supported")