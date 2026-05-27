from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiffEntry:
    key: str
    old_value: str
    new_value: str


@dataclass
class PendingDiff:
    entries: list[DiffEntry]
    snapshot_overwritten: bool


@dataclass
class TemplateCard:
    template_name: str
    summary: str
    distance: float
