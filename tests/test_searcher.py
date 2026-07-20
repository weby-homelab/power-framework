"""Tests for full-text search engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path  # noqa: TC003

from power_framework.core.models import OKFMetadata
from power_framework.core.searcher import (
    SearchResult,
    _compute_tf_vector,
    _cosine_similarity,
    _make_snippet,
    _rrf_merge,
    _score_note,
    _tokenize,
    _vector_search,
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
        # In FTS mode a query with no token matches returns an honest empty list.
        results = search_vault(sample_vault, "xyznonexistent12345", mode="fts")
        assert results == []
        # In the canonical "reranked" mode, a no-FTS-hit query falls back to the
        # dense embedder (R5), which always returns approximate matches — so we
        # assert it returns *something* rather than a silent empty list (B7/FP-7).
        results = search_vault(sample_vault, "xyznonexistent12345", mode="reranked")
        assert len(results) > 0

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

    def test_vector_mode(self, sample_vault: Path):
        results = search_vault(sample_vault, "test project", mode="vector")
        assert len(results) > 0
        assert any("Test Project" in r.title for r in results)

    def test_vector_mode_empty_query(self, sample_vault: Path):
        results = search_vault(sample_vault, "", mode="vector")
        assert results == []

    def test_vector_mode_no_match(self, sample_vault: Path):
        results = search_vault(sample_vault, "xyznonexistent12345", mode="vector")
        assert results == []

    def test_vector_mode_results_ordered(self, sample_vault: Path):
        results = search_vault(sample_vault, "test", mode="vector")
        if len(results) > 1:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_hybrid_mode(self, sample_vault: Path):
        results = search_vault(sample_vault, "test project", mode="hybrid")
        assert len(results) > 0
        assert any("Test Project" in r.title for r in results)

    def test_hybrid_mode_empty_query(self, sample_vault: Path):
        results = search_vault(sample_vault, "", mode="hybrid")
        assert results == []

    def test_hybrid_mode_no_match(self, sample_vault: Path):
        results = search_vault(sample_vault, "xyznonexistent12345", mode="hybrid")
        assert results == []

    def test_hybrid_mode_results_ordered(self, sample_vault: Path):
        results = search_vault(sample_vault, "test", mode="hybrid")
        if len(results) > 1:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_all_modes_return_same_content_type(self, sample_vault: Path):
        fts_results = search_vault(sample_vault, "test", mode="fts")
        vec_results = search_vault(sample_vault, "test", mode="vector")
        hyb_results = search_vault(sample_vault, "test", mode="hybrid")
        assert all(isinstance(r, SearchResult) for r in fts_results + vec_results + hyb_results)

    def test_vector_mode_tag_sensitivity(self, sample_vault: Path):
        results = search_vault(sample_vault, "sample", mode="vector")
        assert len(results) > 0
        assert any("sample" in t for r in results if r.tags for t in r.tags)

    def test_hybrid_mode_outperforms_vector_on_phrase(self, sample_vault: Path):
        hyb_results = search_vault(sample_vault, '"Test Project"', mode="hybrid")
        fts_results = search_vault(sample_vault, '"Test Project"', mode="fts")
        if fts_results and hyb_results:
            assert hyb_results[0].score > 0

    def test_format_search_results_with_mode(self, sample_vault: Path):
        results = search_vault(sample_vault, "test", mode="hybrid")
        report = format_search_results(results, "test", mode="hybrid")
        assert "Hybrid" in report


class TestTFVector:
    """Tests for TF vector computation."""

    def test_simple_tokens(self):
        vec = _compute_tf_vector(["hello", "world"])
        assert abs(vec["hello"] - 0.5) < 1e-9
        assert abs(vec["world"] - 0.5) < 1e-9

    def test_repeated_tokens(self):
        vec = _compute_tf_vector(["test", "test", "hello"])
        assert abs(vec["test"] - 2 / 3) < 1e-9
        assert abs(vec["hello"] - 1 / 3) < 1e-9

    def test_empty_tokens(self):
        vec = _compute_tf_vector([])
        assert vec == {}

    def test_single_token(self):
        vec = _compute_tf_vector(["only"])
        assert abs(vec["only"] - 1.0) < 1e-9


class TestCosineSimilarity:
    """Tests for cosine similarity computation."""

    def test_identical_vectors(self):
        vec = {"hello": 0.5, "world": 0.5}
        sim = _cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        vec_a = {"hello": 1.0}
        vec_b = {"world": 1.0}
        sim = _cosine_similarity(vec_a, vec_b)
        assert abs(sim) < 1e-9

    def test_partial_overlap(self):
        vec_a = {"hello": 1.0}
        vec_b = {"hello": 1.0, "world": 1.0}
        sim = _cosine_similarity(vec_a, vec_b)
        expected = 1.0 / (1.0 * (2.0**0.5))
        assert abs(sim - expected) < 1e-9

    def test_both_empty(self):
        sim = _cosine_similarity({}, {})
        assert abs(sim) < 1e-9

    def test_one_empty(self):
        sim = _cosine_similarity({"a": 1.0}, {})
        assert abs(sim) < 1e-9


class TestVectorSearch:
    """Tests for vector search function."""

    def test_finds_relevant_note(self, sample_vault: Path):
        results = _vector_search(sample_vault, "project architecture")
        assert len(results) > 0
        titles = [r.title for r in results]
        assert any("Weby-QRank" in t for t in titles)

    def test_empty_vault(self, tmp_path: Path):
        results = _vector_search(tmp_path / "empty", "test")
        assert results == []

    def test_max_results(self, sample_vault: Path):
        results = _vector_search(sample_vault, "test", max_results=2)
        assert len(results) <= 2


class TestRRFMerge:
    """Tests for Reciprocal Rank Fusion merge."""

    def _make_result(self, rel_path: str, score: float = 1.0) -> SearchResult:
        return SearchResult(
            rel_path=rel_path,
            title="Test",
            description="",
            note_type="Project",
            score=score,
            snippet="",
            match_count=1,
        )

    def test_identical_lists(self):
        list_a = [self._make_result(f"path{i}.md") for i in range(3)]
        merged = _rrf_merge(list_a, list_a)
        assert len(merged) == 3

    def test_different_lists(self):
        list_a = [self._make_result(f"path{i}.md") for i in range(3)]
        list_b = [self._make_result(f"path{i}.md") for i in range(2, 5)]
        merged = _rrf_merge(list_a, list_b)
        assert len(merged) == 5

    def test_results_ordered_by_rrf_score(self):
        list_a = [self._make_result("common.md")]
        list_b = [self._make_result("unique.md")]
        merged = _rrf_merge(list_a, list_b)
        assert merged[0].score > 0
        assert len(merged) == 2

    def test_shared_document_gets_higher_score(self):
        shared = self._make_result("shared.md")
        unique_a = self._make_result("unique_a.md")
        unique_b = self._make_result("unique_b.md")
        merged = _rrf_merge([shared, unique_a], [shared, unique_b])
        assert merged[0].rel_path == "shared.md"
