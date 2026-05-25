from template_assistant.tone_profiles import GOEMOTIONS_LABELS, TONE_PROFILES, lookup_tone_profile


def test_every_profile_is_non_empty():
    for intent, profile in TONE_PROFILES.items():
        assert isinstance(profile, dict)
        assert profile


def test_profile_labels_are_valid_goemotions_labels():
    for profile in TONE_PROFILES.values():
        for label in profile:
            assert label in GOEMOTIONS_LABELS


def test_unknown_intent_returns_none():
    assert lookup_tone_profile("more mysterious") is None
