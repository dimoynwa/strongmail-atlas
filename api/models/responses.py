from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Any | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    template_name: str
    lang_local: str
    param_cust_brand: str
    tone_key_count: int
    working_copy_overrides: int


class TemplateListItem(BaseModel):
    name: str
    id: str
    key_count: int
    last_modified: str | None
    summary: str | None


class TemplateListResponse(BaseModel):
    templates: list[TemplateListItem]
    total: int


class LocalesResponse(BaseModel):
    locales: list[str]


class BrandsResponse(BaseModel):
    brands: list[str]


class WorkingCopyOverride(BaseModel):
    key: str
    value: str
    set_at: str | None = None


class WorkingCopyResponse(BaseModel):
    session_id: str
    overrides: list[WorkingCopyOverride]
    total_overrides: int
    session_has_changes: bool


class WorkingCopyInitResponse(WorkingCopyResponse):
    initialized: bool
    source: Literal["created", "existing"]
    tone_key_count: int


class WorkingCopyPatchResponse(BaseModel):
    key: str
    value: str
    previous_value: str | None
    success: bool


class WorkingCopyDeleteResponse(BaseModel):
    keys_cleared: int
    success: bool


class UnresolvableKey(BaseModel):
    key: str
    reason: str
    detail: str = ""


class PreviewResponse(BaseModel):
    resolved_html: str
    resolved_text: str
    unresolvable_keys: list[UnresolvableKey]
    total_placeholders: int
    resolved_count: int
    unresolvable_count: int
    tokens_scanned: int
    resolved_token_count: int
    scan_sources: list[str]
    evaluated_from: Literal["working_copy", "graph"]


class ToneEvaluateResponse(BaseModel):
    emotions: dict[str, float]
    model: str
    evaluated_from: str
    plain_text_length: int
    warning: str | None = None


class ToneStoredResponse(BaseModel):
    emotions: dict[str, float] | None
    evaluated_at: str | None
    model_id: str | None
    source: str


class ToneApplyResponse(BaseModel):
    applied: int
    keys: list[str]
    message: str


class ToneUndoResponse(BaseModel):
    restored: int
    message: str
    snapshot_cleared: bool


class HealthComponent(BaseModel):
    status: str
    latency_ms: int | None = None
    model: str | None = None
    active_sessions: int | None = None


class HealthResponse(BaseModel):
    status: str
    components: dict[str, HealthComponent | dict[str, Any]]
