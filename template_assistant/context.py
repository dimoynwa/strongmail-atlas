from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SessionContextMissingError(ValueError):
    """Raised when required session context fields are absent."""


class MissingClassificationError(Exception):
    """Raised when tone suggestions are requested without classified keys."""

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "MissingClassificationError",
            "message": "Key classification must run before tone suggestions can be generated.",
        }


class SuggestionIdMismatchError(Exception):
    """Raised when apply receives suggestions from a stale batch."""

    def __init__(self, expected: str, received: str) -> None:
        self.expected = expected
        self.received = received
        super().__init__(f"Expected suggestion_id {expected!r}, got {received!r}.")

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "SuggestionIdMismatchError",
            "message": "The suggestion batch has expired. Please generate new suggestions.",
        }


@dataclass(frozen=True)
class SessionContext:
    template_name: str
    lang_local: str
    param_cust_brand: str
    session_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "lang_local", self.lang_local.upper())
        object.__setattr__(self, "param_cust_brand", self.param_cust_brand.upper())


def validate_session_context(session_state: dict) -> SessionContext:
    """Build and validate session context from ADK session state."""
    missing = [
        field
        for field in ("template_name", "lang_local", "param_cust_brand", "session_id")
        if not session_state.get(field)
    ]
    if missing:
        raise SessionContextMissingError(
            f"Missing required session context fields: {', '.join(missing)}"
        )

    return SessionContext(
        template_name=str(session_state["template_name"]),
        lang_local=str(session_state["lang_local"]),
        param_cust_brand=str(session_state["param_cust_brand"]),
        session_id=str(session_state["session_id"]),
    )


def build_resolution_context(session_context: SessionContext) -> dict[str, str]:
    return {
        "LANG_LOCAL": session_context.lang_local,
        "PARAM_CUST_BRAND": session_context.param_cust_brand,
    }
