"""
Tests for entity extraction and relation suggestions.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from power_framework.core.models import NoteFile, OKFMetadata, TypedRelation
from power_framework.core.relations import (
    KnowledgeGraph,
    RelationSuggestion,
    _compute_overlap_score,
    _extract_keywords,
    format_relation_suggestions,
    suggest_related,
)


class TestExtractKeywords:
    """Tests for keyword extraction."""

    def test_extracts_meaningful_words(self):
        words = _extract_keywords("Docker container deployment setup")
        assert "docker" in words
        assert "container" in words
        assert "deployment" in words

    def test_filters_stop_words(self):
        words = _extract_keywords("this is a test with the and for")
        assert len(words) <= 2  # 'test' and maybe 'with'

    def test_empty_text(self):
        assert _extract_keywords("") == set()

    def test_unicode_support(self):
        words = _extract_keywords("розгортання контейнера докер")
        assert "розгортання" in words or "контейнера" in words


class TestComputeOverlapScore:
    """Tests for relation score computation."""

    def test_identical_keywords(self):
        kw = {"docker", "deploy", "container"}
        score = _compute_overlap_score(kw, kw, ["dev"], ["dev"])
        assert score > 0.5

    def test_no_overlap(self):
        score = _compute_overlap_score({"abc"}, {"xyz"}, [], [])
        assert score == 0.0

    def test_tag_boost(self):
        kw_a = {"docker"}
        kw_b = {"kubernetes"}
        score_with_tags = _compute_overlap_score(kw_a, kw_b, ["dev"], ["dev"])
        score_no_tags = _compute_overlap_score(kw_a, kw_b, [], [])
        assert score_with_tags > score_no_tags


class TestSuggestRelated:
    """Tests for relation suggestion on vaults."""

    def test_healthy_vault(self, sample_vault: Path):
        suggestions = suggest_related(sample_vault, max_results=10)
        # The sample vault has notes with "Test" in title — they may overlap
        assert isinstance(suggestions, list)

    def test_specific_target(self, sample_vault: Path):
        suggestions = suggest_related(
            sample_vault,
            target_path="03_Resources/TestResource.md",
            max_results=5,
        )
        assert isinstance(suggestions, list)

    def test_no_target_for_nonexistent(self, sample_vault: Path):
        suggestions = suggest_related(
            sample_vault,
            target_path="nonexistent.md",
            max_results=5,
        )
        assert suggestions == []

    def test_empty_vault(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        suggestions = suggest_related(empty)
        assert suggestions == []

    def test_max_results(self, sample_vault: Path):
        suggestions = suggest_related(sample_vault, max_results=2)
        assert len(suggestions) <= 2


class TestRelationSuggestion:
    """Tests for RelationSuggestion class."""

    def test_creation(self):
        rs = RelationSuggestion(
            source_path="a.md",
            target_path="b.md",
            score=0.75,
            reason="Overlap",
        )
        assert rs.source_path == "a.md"
        assert rs.target_path == "b.md"
        assert rs.score == 0.75
        assert rs.reason == "Overlap"


class TestKnowledgeGraphIntegrity:
    def test_from_notes_quarantines_missing_relation_target(self):
        source = NoteFile(
            abs_path="/vault/source.md",
            rel_path="01_Projects/source.md",
            metadata=OKFMetadata(
                type="Project",
                title="Source",
                description="Source note",
                timestamp=datetime(2026, 1, 1),
                related=[TypedRelation(path="01_Projects/missing.md")],
            ),
        )
        target = NoteFile(
            abs_path="/vault/target.md",
            rel_path="01_Projects/target.md",
            metadata=OKFMetadata(
                type="Project",
                title="Target",
                description="Target note",
                timestamp=datetime(2026, 1, 1),
            ),
        )

        graph = KnowledgeGraph.from_notes([source, target])

        assert graph._nodes == {"01_Projects/source.md", "01_Projects/target.md"}
        assert graph._edges == []
        assert graph.quarantined_edges == [
            ("01_Projects/source.md", "01_Projects/missing.md", "related_to", 1.0)
        ]


class TestFormatRelationSuggestions:
    """Tests for formatted output."""

    def test_empty(self):
        report = format_relation_suggestions([], Path("/test"))
        assert "No relation suggestions" in report

    def test_with_suggestions(self):
        suggestions = [
            RelationSuggestion("a.md", "b.md", 0.8, "Strong overlap"),
        ]
        report = format_relation_suggestions(suggestions, Path("/test"))
        assert "a.md" in report
        assert "b.md" in report
        assert "80%" in report
