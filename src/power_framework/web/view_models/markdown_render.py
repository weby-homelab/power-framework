"""Safe Markdown rendering and HTML sanitization for the Web UI."""

from __future__ import annotations

import re
from typing import cast

import bleach  # type: ignore[import-untyped]
import markdown  # type: ignore[import-untyped]

ALLOWED_TAGS = [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "b",
    "i",
    "strong",
    "em",
    "tt",
    "code",
    "pre",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "a",
    "span",
    "hr",
    "br",
    "img",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "class", "target", "rel"],
    "img": ["src", "alt", "title", "class", "width", "height"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["align"],
    "td": ["align"],
    "span": ["class"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")


def process_wikilinks(text: str) -> str:
    """Transform [[Target]] or [[Target|Alias]] into safe local HTML links."""

    def _replace(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        section = match.group(2)
        alias = match.group(3) or target
        url = f"/notes/read?path={target}"
        if section:
            url += f"#{section.strip()}"
        return f'<a href="{url}" class="wikilink">{alias.strip()}</a>'

    return _WIKILINK_PATTERN.sub(_replace, text)


def render_markdown(raw_content: str) -> str:
    """Render Markdown to safe, sanitized HTML."""
    if not raw_content:
        return ""

    # Transform wikilinks before markdown parsing
    processed = process_wikilinks(raw_content)

    # Convert to HTML
    raw_html = markdown.markdown(
        processed,
        extensions=["fenced_code", "tables", "toc"],
    )

    # Sanitize with Bleach to completely eradicate XSS vectors
    return cast(
        "str",
        bleach.clean(
            raw_html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            strip=True,
        ),
    )


__all__ = ["ALLOWED_ATTRIBUTES", "ALLOWED_PROTOCOLS", "ALLOWED_TAGS", "render_markdown"]
