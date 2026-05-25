from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass(frozen=True)
class UnresolvableKey:
    key: str
    reason: str


@dataclass
class ToneEvaluationResult:
    scores: dict[str, float]
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: Literal["working_copy", "graph"] = "graph"
    low_coverage_warning: bool = False


@dataclass(frozen=True)
class ToneSuggestion:
    key: str
    current_value: str
    suggested_value: str
    predicted_delta: dict[str, float]
