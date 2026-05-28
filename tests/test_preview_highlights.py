from api.services.preview import _apply_highlights


def test_apply_highlights_wraps_first_occurrence_only() -> None:
    html = "<p>Skrill welcome to Skrill</p>"
    result = _apply_highlights(html, {"BRAND": "Skrill"})
    assert result.count("<span style=") == 1
    assert "welcome to Skrill" in result


def test_apply_highlights_handles_braces_in_value() -> None:
    html = "<p>Save {amount} today</p>"
    result = _apply_highlights(html, {"AMOUNT": "{amount}"})
    assert "{amount}" in result
    assert result.count("<span style=") == 1


def test_apply_highlights_escapes_html_in_span_content() -> None:
    html = "<p>5 < 10</p>"
    result = _apply_highlights(html, {"COMPARE": "5 < 10"})
    assert "5 &lt; 10</span>" in result
