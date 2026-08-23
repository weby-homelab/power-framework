"""Unit and adversarial security tests for safe Markdown rendering and XSS neutralization."""

from __future__ import annotations

from power_framework.web.view_models.markdown_render import render_markdown


def test_basic_markdown_rendering() -> None:
    """Test standard Markdown constructs render correctly."""
    md = "# Hello World\n\nThis is **bold** and *italic* text."
    html = render_markdown(md)
    assert "<h1>Hello World</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_wikilinks_processing() -> None:
    """Test converting Obsidian wikilinks to safe HTML anchor tags."""
    md = "Check [[Project_Alpha]] and [[Resource_Beta|My Beta]]."
    html = render_markdown(md)
    assert '<a href="/notes/read?path=Project_Alpha" class="wikilink">Project_Alpha</a>' in html
    assert '<a href="/notes/read?path=Resource_Beta" class="wikilink">My Beta</a>' in html


def test_adversarial_xss_prevention() -> None:
    """Ensure stored XSS payloads (script tags, inline handlers, javascript URIs) are stripped."""
    # Script injection
    xss_script = "# Title\n<script>alert('XSS')</script>"
    clean = render_markdown(xss_script)
    assert "<script>" not in clean
    assert "alert('XSS')" in clean or clean == "<h1>Title</h1>"

    # Onerror injection
    xss_onerror = '<img src="invalid.jpg" onerror="alert(1)">'
    clean_onerror = render_markdown(xss_onerror)
    assert "onerror" not in clean_onerror

    # Javascript URI in link
    xss_js_link = '<a href="javascript:alert(document.cookie)">Click me</a>'
    clean_link = render_markdown(xss_js_link)
    assert "javascript:" not in clean_link

    # Data URI script injection
    xss_data = '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">Click</a>'
    clean_data = render_markdown(xss_data)
    assert "data:text/html" not in clean_data
