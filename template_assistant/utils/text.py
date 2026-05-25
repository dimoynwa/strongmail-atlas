"""
template_assistant/utils/text.py

Plain-text extraction from StrongMail HTML email templates.

Replaces trafilatura with a direct HTMLParser subclass.  Trafilatura's
article-extraction heuristics discard short paragraphs in table cells,
which are the primary content unit in StrongMail templates.  This
implementation collects every visible text node without filtering.
"""

from html.parser import HTMLParser
import re


class _TextExtractor(HTMLParser):
    """Collect all visible text from an HTML document.

    Skips <script>, <style>, and <head> blocks.  Flushes the current
    line buffer to a new line on every block-level tag boundary so that
    content from adjacent table cells does not run together.
    Suppresses all HTML comments including MSO conditional comments.
    """

    _SKIP_TAGS = {"script", "style", "head"}
    _BLOCK_TAGS = {
        "p", "br", "tr", "td", "th", "div", "li",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._lines: list[str] = []
        self._current: list[str] = []
        self._skip_depth: int = 0

    def _flush(self) -> None:
        """Flush the current word buffer as a completed line."""
        text = " ".join(self._current).strip()
        if text:
            self._lines.append(text)
        self._current = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
        elif t in self._BLOCK_TAGS and self._skip_depth == 0:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif t in self._BLOCK_TAGS and self._skip_depth == 0:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            s = data.strip()
            if s:
                self._current.append(s)

    def handle_comment(self, data: str) -> None:
        # Suppress all HTML comments including <!--[if mso]> conditionals.
        pass

    def get_text(self) -> str:
        """Return extracted text with collapsed blank lines."""
        self._flush()
        text = "\n".join(self._lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# Footer boilerplate stop-markers.
#
# _strip_footer_text scans lines top-to-bottom and stops at the first
# line containing any of these strings, discarding it and everything
# after it.  Order is irrelevant — the scan stops at whichever appears
# first in the document.
#
# "About" catches the footer navigation bar present in modern Skrill
# templates (About | Support | Security | Privacy | Terms), which
# always precedes the copyright block.
#
# "View In Browser" and "View this email in" are intentionally excluded:
# they appear as the first line of extracted text in some templates and
# would cause the entire output to be discarded.
_FOOTER_MARKERS: list[str] = [
    "About",
    "Copyright \u00a9",    # &copy; decoded by convert_charrefs=True
    "Copyright ©",          # literal © in source HTML
    "registered in England and Wales",
    "We use cookies and similar technology",
    "To ensure that Skrill emails reach your inbox",
    "NFY_",
]

# Lines that consist entirely of noise — never prose.
# Matches:
#   - Bare hex colour codes:  #592357, #fff, #1dcece
#   - Zero-width / whitespace-only strings
#   - Lines that are only punctuation characters: |  &  ;  ,  .  -
_NOISE_RE = re.compile(
    r"^("
    r"#[0-9A-Fa-f]{3,8}"
    r"|[\u200b\u200c\u200d\s]+"
    r"|[|&;,.\-]+\s*"
    r")$"
)


def _strip_footer_text(text: str) -> str:
    """Remove known boilerplate lines from extracted email text.

    Scans lines sequentially.  Stops and discards from the first line
    that matches a footer marker.  Also removes noise-only lines
    (bare colour codes, zero-width chars, lone punctuation) throughout.
    """
    lines = text.splitlines()
    clean: list[str] = []
    for line in lines:
        if any(marker in line for marker in _FOOTER_MARKERS):
            break
        if not _NOISE_RE.match(line):
            clean.append(line)
    return "\n".join(clean).strip()


def extract_plain_text(html: str) -> str:
    """Extract all human-readable text from an HTML email template.

    Uses plain tag-stripping rather than an article extractor.
    Email templates contain no boilerplate in the article-extraction
    sense — every sentence is intentional content that must be
    preserved for tone analysis.

    Must be called on fully resolved HTML.  Unresolved ##TOKEN##
    placeholders will appear literally in the output and should be
    resolved before calling this function.

    Args:
        html: Fully resolved HTML string of the email template.

    Returns:
        Plain text suitable for passing to the GoEmotions classifier.
        Footer boilerplate and noise lines are removed.  Returns an
        empty string if html is empty or None.
    """
    if not html:
        return ""
    extractor = _TextExtractor()
    extractor.feed(html)
    text = extractor.get_text()
    return _strip_footer_text(text)
