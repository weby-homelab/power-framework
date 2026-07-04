"""Tests for full-text search engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path  # noqa: TC003

from power_framework.core.models import OKFMetadata
from power_framework.core.searcher import (
    SearchResult,
    _make_snippet,
    _score_note,
    _tokenize,
    format_search_results,
    search_vault,
)


class TestTokenize:
    """Tests for text tokenization."""

    def test_simple_words(self):
        assert _tokenize("hello world") == ["hello", "world"]

    def test_unicode(self):
        assert "пошук" in _tokenize("пошук нотаток")

    def test_punctuation_removed(self):
        tokens = _tokenize("hello, world! test.")
        assert "hello" in tokens
        assert "world" in tokens

    def test_lowercase(self):
        assert _tokenize("Hello World") == ["hello", "world"]


class TestScoreNote:
    """Tests for note scoring against search terms."""

    def _make_meta(self, title="Test", desc="A test note", tags=None):
        return OKFMetadata(
            type="Project",
            title=title,
            description=desc,
            tags=tags or [],
            resource=None,
            timestamp=datetime(2026, 1, 1),
        )

    def test_title_match_high_score(self):
        meta = self._make_meta(title="Docker Guide")
        content = "# Docker Guide\n\nSome content about docker."
        score, count, snippet = _score_note(content, meta, ["docker"])
        assert score > 0
        assert count > 0
        assert snippet

    def test_title_weight_higher_than_body(self):
        title_meta = self._make_meta(title="Python Programming")
        title_content = "# Python Programming\n\nContent."
        title_score, _, _ = _score_note(title_content, title_meta, ["python"])

        body_meta = self._make_meta(title="Other Topic")
        body_content = "# Other Topic\n\nPython is a programming language. Python is great."
        body_score, _, _ = _score_note(body_content, body_meta, ["python"])

        assert title_score > body_score

    def test_tag_match(self):
        meta = self._make_meta(tags=["python", "docker"])
        content = "# Test\n\nContent."
        score, count, _ = _score_note(content, meta, ["python"])
        assert score > 0
        assert count > 0

    def test_no_match_returns_zero(self):
        meta = self._make_meta()
        content = "# Test\n\nNothing about the query here."
        score, count, snippet = _score_note(content, meta, ["nonexistent"])
        assert score == 0
        assert count == 0
        assert snippet == ""


class TestMakeSnippet:
    """Tests for snippet extraction."""

    def test_basic_snippet(self):
        snippet = _make_snippet("The quick brown fox jumps over the lazy dog.", ["fox"])
        assert "fox" in snippet

    def test_returns_content_when_no_match(self):
        snippet = _make_snippet("Some content here.", ["nothing"])
        assert snippet

    def test_snippet_trimmed(self):
        long = "Hello " * 100
        snippet = _make_snippet(long, ["hello"])
        assert len(snippet) <= 125


class TestFormatSearchResults:
    """Tests for search results formatting."""

    def test_empty_results(self):
        result = format_search_results([], "test")
        assert "No results" in result

    def test_single_result(self):
        results = [
            SearchResult(
                rel_path="01_Projects/test.md",
                title="Test Note",
                description="A test",
                note_type="Project",
                score=10.0,
                snippet="test content",
                match_count=2,
                tags=["test"],
            )
        ]
        output = format_search_results(results, "test")
        assert "Test Note" in output
        assert "1." in output


class TestSearchVault:
    """Tests for full vault search (using fixtures)."""

    def test_search_on_empty_vault(self, tmp_path: Path):
        empty = tmp_path / "empty_vault"
        empty.mkdir()
        results = search_vault(empty, "test")
        assert results == []

    def test_search_finds_match(self, sample_vault: Path):
        results = search_vault(sample_vault, "test project")
        assert len(results) > 0
        assert any("Test Project" in r.title for r in results)

    def test_search_by_tag(self, sample_vault: Path):
        results = search_vault(sample_vault, "sample")
        assert len(results) > 0
        assert any("sample" in t for r in results if r.tags for t in r.tags)

    def test_search_by_type_metadata(self, sample_vault: Path):
        results = search_vault(sample_vault, "resource note")
        assert len(results) > 0
        assert any("Resource" in r.note_type for r in results)
        results = search_vault(sample_vault, "")
        assert results == []

    def test_search_nonexistent_query(self, sample_vault: Path):
        results = search_vault(sample_vault, "xyznonexistent12345")
        assert results == []

    def test_max_results(self, sample_vault: Path):
        results = search_vault(sample_vault, "test", max_results=1)
        assert len(results) <= 1

    def test_results_ordered_by_score(self, sample_vault: Path):
        results = search_vault(sample_vault, "test")
        if len(results) > 1:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_quoted_phrase_search(self, sample_vault: Path):
        results = search_vault(sample_vault, '"Test Project"')
        assert len(results) > 0
        assert any("Test Project" in r.title for r in results)

    def test_search_vault_fallback_on_sqlite_error(self, sample_vault: Path):
        import sqlite3
        from unittest.mock import patch
        with patch("sqlite3.connect", side_effect=sqlite3.Error("Mocked SQLite Error")):

            results = search_vault(sample_vault, "Test")
            assert len(results) > 0
            assert any("Test" in r.title for r in results)

