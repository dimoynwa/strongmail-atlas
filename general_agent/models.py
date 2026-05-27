from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


DEFAULT_LIMIT = 10
MAX_LIMIT = 50


def clamp_limit(limit: int = DEFAULT_LIMIT) -> int:
    """Enforce result limits (default 10, max 50)."""
    return max(1, min(limit, MAX_LIMIT))


@dataclass(frozen=True)
class TemplateSearchResult:
    template_id: str
    template_name: str
    summary: str
    score: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToneDiscoveryResult:
    template_id: str
    template_name: str
    emotions: dict[str, float]
    evaluated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evaluated_at"] = self.evaluated_at.isoformat()
        return data


@dataclass(frozen=True)
class StructuralSummary:
    template_id: str
    template_name: str
    content_block_count: int
    placeholder_count: int
    unresolvable_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolutionHealthResult:
    template_id: str
    template_name: str
    total_keys: int
    unresolvable_keys: int
    health_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
