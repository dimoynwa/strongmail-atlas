from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Optional

from api.refresh.models import ProgressEvent

ToneJobStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class ToneJob:
    job_id: str
    status: ToneJobStatus
    started_at: str
    finished_at: Optional[str]
    error: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = ["ProgressEvent", "ToneJob", "ToneJobStatus"]
