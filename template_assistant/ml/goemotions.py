from __future__ import annotations

from typing import Any

_classifier: Any | None = None


def get_classifier() -> Any:
    """Return the lazily-loaded GoEmotions pipeline singleton."""
    global _classifier
    if _classifier is None:
        import torchvision  # noqa: F401 — transformers vision modules expect this

        from transformers import pipeline

        _classifier = pipeline(
            "text-classification",
            model="SamLowe/roberta-base-go_emotions",
            top_k=None,
        )
    return _classifier


def reset_classifier_for_tests() -> None:
    """Reset singleton — test helper only."""
    global _classifier
    _classifier = None


def scores_from_pipeline_result(result: list[dict[str, float | str]]) -> dict[str, float]:
    """Convert pipeline output to label→score dict."""
    return {str(item["label"]): float(item["score"]) for item in result}
