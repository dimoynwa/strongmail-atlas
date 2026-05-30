from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Optional

JobType = Literal["template", "full"]
JobStatus = Literal["pending", "running", "done", "failed"]
EventType = Literal[
    "step_start", "step_done", "step_error", "item_done", "job_done", "job_failed"
]


@dataclass
class RefreshJob:
    job_id: str
    type: JobType
    target: Optional[str]
    status: JobStatus
    started_at: str
    finished_at: Optional[str]
    error: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProgressEvent:
    type: EventType
    step: Optional[str]
    message: str
    count: Optional[int]
    total: Optional[int]
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LinkedBlocksResult:
    block_ids: list[str]
    rule_ids: list[str]
    template_id: str
