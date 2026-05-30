from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    atlas_root = Path(__file__).resolve().parents[2]
    return [
        atlas_root,
        atlas_root.parent / "paysafe-email-tone-of-voice",
    ]


def ensure_pipeline_importable() -> None:
    for root in _candidate_roots():
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)


def apply_env(env: dict[str, str]) -> None:
    for key, value in env.items():
        if value is not None:
            os.environ[key] = value
    ensure_pipeline_importable()


def get_responses_dir() -> Path:
    responses = Path(__file__).resolve().parents[2] / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    return responses
