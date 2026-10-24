"""Plain-text helpers.

Purpose
    Zenodo stores descriptions as HTML fragments (``<p>…</p>``). ODIS search
    indexes ``schema:description`` as text, so the HTML is converted to plain
    text with paragraph breaks preserved.

Invariants
    * No tags survive; entities are unescaped; whitespace inside a paragraph
      is collapsed to single spaces; paragraphs are separated by a blank line.
    * Pure functions, standard library only.

Assumptions
    * Input is well-formed enough for ``html.parser``; stray tags degrade
      gracefully (they are dropped, their text kept).
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "blockquote", "pre", "hr"}
_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - HTMLParser signature
        if tag in _BLOCK_TAGS:
            self.parts.append("\n\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """Convert an HTML fragment (or plain text) to normalised plain text."""
    if not value:
        return ""
    if _TAG_RE.search(value) is None and "&" not in value:
        return collapse_paragraphs(value)
    extractor = _TextExtractor()
    extractor.feed(value)
    extractor.close()
    return collapse_paragraphs(unescape("".join(extractor.parts)))


def collapse_paragraphs(value: str) -> str:
    """Collapse runs of whitespace within paragraphs; keep paragraph breaks."""
    paragraphs = re.split(r"\n\s*\n", value.replace("\r", ""))
    cleaned = [" ".join(p.split()) for p in paragraphs]
    return "\n\n".join(p for p in cleaned if p)


def one_line(value: str | None) -> str:
    """Whitespace-collapsed single line (for names and keywords)."""
    return " ".join((value or "").split())
