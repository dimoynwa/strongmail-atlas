from __future__ import annotations

import trafilatura

_FOOTER_MARKERS = (
    "Copyright ©",
    "Skrill Limited is registered",
    "We use cookies",
)


def _strip_footer_text(text: str) -> str:
    """Remove boilerplate footer content starting at known marker strings."""
    for marker in _FOOTER_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text.replace("\n", " ").replace("\r", " ").replace("\t", " ").replace("|", " ").strip()


def extract_plain_text(html: str) -> str:
    """Extract readable plain text from HTML, stripping boilerplate."""
    if not html:
        return ""

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    text = extracted or ""
    return _strip_footer_text(text)
