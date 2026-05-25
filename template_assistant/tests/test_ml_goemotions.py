from unittest.mock import MagicMock

import template_assistant.ml.goemotions as goemotions_module
from template_assistant.ml.goemotions import get_classifier, reset_classifier_for_tests
from template_assistant.tone_profiles import GOEMOTIONS_LABELS


def setup_function():
    reset_classifier_for_tests()


def test_get_classifier_is_singleton():
    reset_classifier_for_tests()
    mock_pipeline = MagicMock(return_value=[{"label": "joy", "score": 0.9}])
    goemotions_module._classifier = mock_pipeline
    first = get_classifier()
    second = get_classifier()
    assert first is second is mock_pipeline


def test_classifier_returns_labelled_scores():
    labels = sorted(GOEMOTIONS_LABELS)
    mock_scores = [{"label": label, "score": 0.1} for label in labels]
    mock_pipeline = MagicMock(return_value=mock_scores)
    reset_classifier_for_tests()
    goemotions_module._classifier = mock_pipeline
    classifier = get_classifier()
    result = classifier("This is a friendly message about your account.")
    assert len(result) == 28
    assert all("label" in item and "score" in item for item in result)
