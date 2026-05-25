from __future__ import annotations

GOEMOTIONS_LABELS: frozenset[str] = frozenset(
    {
        "admiration",
        "amusement",
        "anger",
        "annoyance",
        "approval",
        "caring",
        "confusion",
        "curiosity",
        "desire",
        "disappointment",
        "disapproval",
        "disgust",
        "embarrassment",
        "excitement",
        "fear",
        "gratitude",
        "grief",
        "joy",
        "love",
        "nervousness",
        "neutral",
        "optimism",
        "pride",
        "realization",
        "relief",
        "remorse",
        "sadness",
        "surprise",
    }
)

TONE_PROFILES: dict[str, dict[str, float]] = {
    "more reassuring": {
        "relief": 0.8,
        "caring": 0.7,
        "fear": 0.1,
        "nervousness": 0.1,
    },
    "more urgent": {"desire": 0.8, "nervousness": 0.6},
    "warmer": {"joy": 0.8, "love": 0.7, "gratitude": 0.7},
    "more professional": {"approval": 0.7, "amusement": 0.1, "excitement": 0.1},
    "more encouraging": {"admiration": 0.8, "optimism": 0.8, "joy": 0.6},
}


def lookup_tone_profile(intent: str) -> dict[str, float] | None:
    """Return target emotion weights for a canonical intent phrase, or None."""
    normalized = intent.strip().lower()
    return TONE_PROFILES.get(normalized)
