from template_assistant.utils.text import extract_plain_text


def test_normal_html_returns_plain_text():
    html = "<html><body><p>Hello world, this is paragraph one.</p></body></html>"
    text = extract_plain_text(html)
    assert "Hello world" in text


def test_image_only_html_returns_empty_string():
    html = "<html><body><img src='logo.png' alt='logo'></body></html>"
    assert extract_plain_text(html) == ""


def test_empty_input_returns_empty_string():
    assert extract_plain_text("") == ""


def test_short_html_returns_short_string():
    html = "<html><body><p>Hi</p></body></html>"
    text = extract_plain_text(html)
    assert len(text) < 50


def test_footer_markers_are_stripped():
    html = """
    <html><body>
      <p>Your password was created successfully.</p>
      <p>Copyright © 2026 Skrill Limited. All rights reserved.</p>
      <p>We use cookies to improve your experience.</p>
    </body></html>
    """
    text = extract_plain_text(html)
    assert "Your password was created successfully." in text
    assert "Copyright" not in text
    assert "We use cookies" not in text


def test_strip_footer_text_helper():
    from template_assistant.utils.text import _strip_footer_text

    text = "Main body content.\nregistered in England and Wales\nExtra footer."
    assert _strip_footer_text(text) == "Main body content."


def test_newlines_are_preserved_in_footer_strip():
    from template_assistant.utils.text import _strip_footer_text

    assert _strip_footer_text("Line one\nLine two") == "Line one\nLine two"
