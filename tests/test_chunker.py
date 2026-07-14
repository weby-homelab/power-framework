"""Tests for SemanticChunker (Anthropic Contextual Retrieval)."""

from __future__ import annotations

from power_framework.core.chunker import SemanticChunker, _strip_frontmatter


class TestStripFrontmatter:
    """Tests for frontmatter removal."""

    def test_strips_frontmatter(self):
        content = "---\ntitle: Test\n---\n\n# Body\n\nContent."
        result = _strip_frontmatter(content)
        assert "Body" in result
        assert "---" not in result

    def test_no_frontmatter(self):
        content = "# Just content\n\nNo frontmatter."
        assert _strip_frontmatter(content) == content

    def test_empty_content(self):
        assert _strip_frontmatter("") == ""


class TestSemanticChunkerInit:
    """Tests for SemanticChunker initialization."""

    def test_default_mode(self):
        chunker = SemanticChunker()
        assert chunker.mode == "headers"

    def test_custom_mode(self):
        chunker = SemanticChunker(mode="paragraphs", chunk_size=256)
        assert chunker.mode == "paragraphs"
        assert chunker.chunk_size == 256


class TestChunkByHeaders:
    """Tests for header-based chunking."""

    def test_single_section(self):
        chunker = SemanticChunker(mode="headers")
        md = "## Section One\n\nContent here."
        result = chunker.chunk(md, title="Doc", description="A doc")
        assert len(result) == 1
        assert "[Document: Doc | Description: A doc]" in result[0]
        assert "Section One" in result[0]

    def test_multiple_h2_sections(self):
        chunker = SemanticChunker(mode="headers")
        md = "## First\n\nContent A\n\n## Second\n\nContent B"
        result = chunker.chunk(md, title="Test", description="Test")
        assert len(result) == 2
        assert "First" in result[0]
        assert "Second" in result[1]
        assert all("[Document: Test | Description: Test]" in c for c in result)

    def test_h2_and_h3_mixed(self):
        chunker = SemanticChunker(mode="headers")
        md = "## Level 2\n\nBody.\n\n### Level 3\n\nDetail."
        result = chunker.chunk(md, title="X", description="Y")
        assert len(result) == 2

    def test_preamble_before_first_header(self):
        chunker = SemanticChunker(mode="headers")
        md = "Some intro text.\n\n## Section\n\nBody."
        result = chunker.chunk(md, title="T", description="D")
        assert len(result) >= 1
        assert any("intro" in c for c in result)

    def test_no_headers(self):
        chunker = SemanticChunker(mode="headers")
        md = "Just a plain paragraph with no markdown headers."
        result = chunker.chunk(md, title="Plain", description="No headers")
        assert len(result) == 1
        assert "plain paragraph" in result[0]

    def test_empty_content(self):
        chunker = SemanticChunker(mode="headers")
        result = chunker.chunk("", title="Empty", description="")
        assert result == []


class TestChunkByParagraphs:
    """Tests for paragraph-based chunking."""

    def test_multiple_paragraphs(self):
        chunker = SemanticChunker(mode="paragraphs")
        md = "Para one.\n\nPara two.\n\nPara three."
        result = chunker.chunk(md, title="P", description="D")
        assert len(result) == 3
        assert "Para one" in result[0]
        assert "Para two" in result[1]
        assert "Para three" in result[2]

    def test_single_paragraph(self):
        chunker = SemanticChunker(mode="paragraphs")
        result = chunker.chunk("Single block.", title="S", description="D")
        assert len(result) == 1

    def test_with_frontmatter(self):
        chunker = SemanticChunker(mode="paragraphs")
        md = "---\ntitle: Test\n---\n\nFirst para.\n\nSecond para."
        result = chunker.chunk(md, title="FM", description="Has FM")
        assert len(result) == 2

    def test_context_prefix_present(self):
        chunker = SemanticChunker(mode="paragraphs")
        result = chunker.chunk("Hello.", title="Greeting", description="A hello")
        assert result[0].startswith("[Document: Greeting | Description: A hello]")

    def test_empty_paragraphs(self):
        chunker = SemanticChunker(mode="paragraphs")
        result = chunker.chunk("", title="E", description="E")
        assert result == []


class TestChunkFixed:
    """Tests for fixed-size character chunking."""

    def test_small_content(self):
        chunker = SemanticChunker(mode="fixed", chunk_size=100)
        result = chunker.chunk("Short.", title="S", description="D")
        assert len(result) == 1

    def test_splits_large_content(self):
        chunker = SemanticChunker(mode="fixed", chunk_size=10, chunk_overlap=0)
        text = "A" * 25
        result = chunker.chunk(text, title="L", description="Long")
        assert len(result) >= 2

    def test_with_overlap(self):
        chunker = SemanticChunker(mode="fixed", chunk_size=15, chunk_overlap=5)
        text = "A" * 35
        result = chunker.chunk(text, title="O", description="Overlap")
        assert len(result) >= 2

    def test_context_prefix_on_each(self):
        chunker = SemanticChunker(mode="fixed", chunk_size=10)
        text = "A" * 25
        result = chunker.chunk(text, title="Pre", description="Fix")
        assert all(c.startswith("[Document: Pre | Description: Fix]") for c in result)

    def test_empty_fixed(self):
        chunker = SemanticChunker(mode="fixed")
        result = chunker.chunk("", title="E", description="E")
        assert result == []


class TestChunkerOutputQuality:
    """Tests that chunker produces meaningful contextualized output."""

    def test_chunk_prefix_contains_metadata(self):
        chunker = SemanticChunker()
        md = "## Section\n\nContent."
        result = chunker.chunk(md, title="My Note", description="A test note")
        assert all(
            "[Document: My Note | Description: A test note]" in c for c in result
        )

    def test_chunks_are_non_empty(self):
        chunker = SemanticChunker(mode="headers")
        md = "## A\n\nBody\n\n## B\n\nBody"
        result = chunker.chunk(md, title="T", description="D")
        assert all(c for c in result)

    def test_whitespace_only_skipped(self):
        chunker = SemanticChunker(mode="headers")
        result = chunker.chunk("   \n\n  ", title="W", description="S")
        assert result == []

    def test_context_prefix_always_includes_both_fields(self):
        chunker = SemanticChunker()
        result = chunker.chunk("Content.", title="T", description="D")
        assert "Document: T" in result[0]
        assert "Description: D" in result[0]

    def test_different_modes_produce_same_prefix_format(self):
        md = "## H\n\nP1\n\n## H2\n\nP2"
        h_result = SemanticChunker(mode="headers").chunk(md, title="X", description="Y")
        p_result = SemanticChunker(mode="paragraphs").chunk(
            md, title="X", description="Y"
        )
        assert all(c.startswith("[Document: X | Description: Y]") for c in h_result)
        assert all(c.startswith("[Document: X | Description: Y]") for c in p_result)
