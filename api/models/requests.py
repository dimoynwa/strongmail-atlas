from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CreateSessionRequest(BaseModel):
    template_name: str
    lang_local: str
    param_cust_brand: str

    @field_validator("lang_local", "param_cust_brand")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class ChatStreamRequest(BaseModel):
    message: str
    session_id: str | None = None
    agent: Literal["template", "general"]


class WorkingCopyPatchRequest(BaseModel):
    key: str
    value: str


class ToneEvaluateRequest(BaseModel):
    top_n: int = Field(default=5, ge=1, le=28)


class ToneApplyRequest(BaseModel):
    keys: list[str] | None = None


class ToneUndoRequest(BaseModel):
    keys: list[str] | None = None
