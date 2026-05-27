# Spec: Replace Trafilatura with Plain Tag-Stripping in `extract_plain_text`

**Spec ID**: 005-extract-plain-text-fix  
**Branch**: `005-extract-plain-text-fix`  
**Date**: May 25, 2026  
**Status**: Draft  
**Related specs**: 003-tone-suggestion-validation (Tone Suggestion Key Validation), 004-tone-suggestion-reachability-pre-filter (Reachability Pre-Filter)

---

## Problem

`extract_plain_text` in `template_assistant/utils/text.py` uses `trafilatura` to
strip HTML before passing text to the GoEmotions classifier. Trafilatura is a web
article extractor designed to remove "boilerplate" from news articles. Applied to
StrongMail email templates, its heuristics incorrectly classify intentional email
content as boilerplate and drop it.

### Observed failures

On the `NFY_PASSWORD_CREATED` template, trafilatura dropped:

> "If you did not authorise this change, please contact the Skrill Help Team."

On the `NFY_SM_REGISTERED` (send money confirmation) template, trafilatura dropped
multiple body paragraphs, retaining only fragments of the content.

In both cases, the dropped content is genuine prose that directly affects GoEmotions
tone scores. Losing it causes the baseline tone evaluation to be inaccurate, which
in turn makes tone suggestions less reliable.

### Root cause

Trafilatura scores text blocks by density and position heuristics tuned for web
articles. Short paragraphs in isolated table cells — the standard StrongMail layout
— score below its keep threshold and are discarded. There is no configuration option
that disables this behaviour without also disabling meaningful extraction.

---

## Solution

Replace the `trafilatura.extract()` call in `extract_plain_text` with a plain
`html.parser.HTMLParser` subclass that collects all text nodes, subject only to:

1. Skipping `<script>`, `<style>`, and `<head>` blocks entirely.
2. Flushing accumulated text to a new line on every block-level tag boundary
   (`<tr>`, `<td>`, `<th>`, `<p>`, `<br>`, `<div>`, `<li>`, headings).
3. Suppressing HTML comments (including MSO conditional comments).
4. Stripping known footer boilerplate lines via `_strip_footer_text`.
5. Dropping noise-only lines (bare hex colour codes, zero-width chars,
   lone punctuation) via `_NOISE_RE`.

No third-party library is required. `html.parser` is stdlib.

---

## Scope

**One file changes:** `template_assistant/utils/text.py`

No other files are modified. The public signature of `extract_plain_text` is
unchanged: `extract_plain_text(html: str) -> str`.

---

## Implementation

Replace the entire contents of `template_assistant/utils/text.py` with the
following implementation. Every component is documented inline.

```python
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
```

---

## Functional Requirements

**FR-021**: `extract_plain_text` MUST preserve every human-readable sentence in
the email body, including short paragraphs in isolated table cells. No content
heuristic or density filter may be applied.

**FR-022**: `extract_plain_text` MUST skip the contents of `<script>`, `<style>`,
and `<head>` blocks entirely. Text inside these tags MUST NOT appear in the output.

**FR-023**: `extract_plain_text` MUST suppress all HTML comments, including MSO
conditional comments of the form `<!--[if mso]>...<![endif]-->`.

**FR-024**: `extract_plain_text` MUST stop and discard all output from the first
footer marker line onward. The footer markers are defined in `_FOOTER_MARKERS`.
The function MUST NOT include copyright blocks, cookie notices, safe-list reminders,
or StrongMail tracking tags (`NFY_*`) in the returned text.

**FR-025**: `extract_plain_text` MUST discard noise-only lines matching `_NOISE_RE`
throughout the document — not only in the footer. This includes bare hex colour
codes (e.g. `#592357`) that appear as raw text nodes between table rows.

**FR-026**: `extract_plain_text` MUST use `convert_charrefs=True` in the
`HTMLParser` constructor so that HTML entities (`&copy;`, `&nbsp;`, `&zwnj;`,
`&#39;`) are decoded before text is collected. The `_FOOTER_MARKERS` list relies
on this for the `Copyright ©` match.

**FR-027**: The public signature of `extract_plain_text` MUST remain
`extract_plain_text(html: str) -> str`. No other public function in
`template_assistant/utils/text.py` may be modified or removed.

**FR-028**: `trafilatura` MUST NOT be imported or called anywhere in
`template_assistant/utils/text.py` after this change.

---

## Boundaries & Constraints

- **One file only**: only `template_assistant/utils/text.py` is modified.
- **No new dependencies**: `html.parser` and `re` are stdlib. Do not add any
  third-party import.
- **`trafilatura` removal**: remove the import. If `trafilatura` appears in
  `requirements.txt` or `pyproject.toml` and is used nowhere else after this
  change, remove it from the dependency list as well — but do not change any
  other source file to do so.
- **Private helpers**: `_TextExtractor`, `_strip_footer_text`, `_FOOTER_MARKERS`,
  and `_NOISE_RE` are module-private. Their names and signatures may not be
  referenced in tests — tests call only `extract_plain_text`.

---

## Test Requirements

Tests live in `template_assistant/tests/test_text.py`.
All tests call `extract_plain_text` directly. No mocking is required —
the function is pure and deterministic.

### T-001 — `NFY_PASSWORD_CREATED` template

**Input**: The fully resolved HTML of the `NFY_PASSWORD_CREATED` template
(classic table-layout design, `<!--[if mso]>` comments absent,
`&copy;` entity in footer).

**Assertions**:

```python
result = extract_plain_text(html)

# Core body sentences must be present
assert "You have successfully created a password for your Skrill account." in result
assert "If you did not authorise this change, please contact the" in result
assert "Skrill Help Team" in result
assert "Best Regards," in result
assert "Skrill" in result

# Footer must be stripped
assert "Copyright" not in result
assert "registered in England and Wales" not in result
assert "We use cookies" not in result
assert "NFY_PASSWORD_CREATED" not in result

# Noise must be stripped (no bare hex codes)
assert "#f4f4f4" not in result
assert "#910590" not in result
```

### T-002 — `NFY_SM_REGISTERED` template

**Input**: The fully resolved HTML of the `NFY_SM_REGISTERED` template
(modern modular design, `<!--[if mso]>` conditional comments present,
footer nav bar with "About | Support | Security | Privacy | Terms",
raw hex colour code `#592357` as a standalone text node between rows).

**Assertions**:

```python
result = extract_plain_text(html)

# Hero section
assert "YOU JUST SENT" in result

# Body copy — both paragraphs must be present
assert "If you didn't do this, or do not recognise any of the above details" in result
assert "please contact us right away" in result
assert "If your payment is processed but the merchant hasn't yet credited it" in result

# Sign-off
assert "Thank you for choosing Skrill" in result

# Footer nav bar must be stripped (first "About" line stops the scan)
assert "About" not in result
assert "Support" not in result
assert "Privacy" not in result

# Footer boilerplate must be stripped
assert "Copyright" not in result
assert "NFY_SM_REGISTERED" not in result

# Raw hex colour code noise must be stripped
assert "#592357" not in result

# MSO conditional comment content must not appear
assert "font-family: sans-serif" not in result
assert "PixelsPerInch" not in result
```

---

## Success Criteria

**SC-001**: Both T-001 and T-002 pass.

**SC-002**: All existing tests in `template_assistant/tests/` continue to pass
without modification.

**SC-003**: `trafilatura` is no longer imported in `template_assistant/utils/text.py`.

**SC-004**: Running `evaluate_tone` on the `NFY_PASSWORD_CREATED` template
returns non-zero scores for emotions such as `approval` and `neutral`. The
previously missing "If you did not authorise this change" sentence is included
in the scored text.

**SC-005**: Running `evaluate_tone` on the `NFY_SM_REGISTERED` template returns
non-zero scores reflecting the body copy ("Thank you for choosing Skrill",
the transaction detail sentences). The `#592357` colour code does not appear
in the text passed to GoEmotions.