"""Tests for ROT scoring (content dedup, freshness, link rot, usage tracking)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_framework.core.rot_scoring import (
    ContentDedupDetector,
    FreshnessScorer,
    UsageTracker,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestContentDedupDetector:
    def test_detects_similar_content(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()

        note_a = vault / "01_Projects" / "note_a.md"
        note_a.write_text(
            '---\ntype: Project\ntitle: "Note A"\n'
            'description: "First note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "This is the body content of note A. It has many words that should be similar "
            "to note B because they share the same topic and vocabulary across the text."
        )

        note_b = vault / "01_Projects" / "note_b.md"
        note_b.write_text(
            '---\ntype: Project\ntitle: "Note B"\n'
            'description: "Second note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "This is the body content of note B. It has many words that should be similar "
            "to note A because they share the same topic and vocabulary across the text."
        )

        detector = ContentDedupDetector(threshold=0.5)
        pairs = detector.detect(vault)
        assert len(pairs) >= 1
        assert any("note_a" in p[0] or "note_a" in p[1] for p in pairs)

    def test_different_content_not_deduped(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()

        note_a = vault / "01_Projects" / "note_a.md"
        note_a.write_text(
            '---\ntype: Project\ntitle: "Note A"\n'
            'description: "First note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "Python programming language is used for web development and data science."
        )

        note_b = vault / "01_Projects" / "note_b.md"
        note_b.write_text(
            '---\ntype: Project\ntitle: "Note B"\n'
            'description: "Second note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "Quantum physics explores the behavior of matter at the atomic and subatomic level."
        )

        detector = ContentDedupDetector(threshold=0.75)
        pairs = detector.detect(vault)
        assert len(pairs) == 0


class TestFreshnessScorer:
    def test_recent_note_is_fresh(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "06_Daily_Logs").mkdir()

        note = vault / "06_Daily_Logs" / "recent.md"
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        note.write_text(
            '---\ntype: Daily Log\ntitle: "Recent Note"\n'
            'description: "Fresh note"\n'
            f"timestamp: {now}\n---\n\nFresh content."
        )

        scorer = FreshnessScorer()
        scores = scorer.score_all(vault)
        assert len(scores) == 1
        rel_path = str(note.relative_to(vault))
        assert scores[rel_path] > 0.8  # freshly created, should be very fresh

    def test_old_daily_log_is_stale(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "06_Daily_Logs").mkdir()

        note = vault / "06_Daily_Logs" / "old.md"
        note.write_text(
            '---\ntype: Daily Log\ntitle: "Old Note"\n'
            'description: "Stale note"\n'
            "timestamp: 2025-01-01T00:00:00\n---\n\nOld content."
        )

        scorer = FreshnessScorer()
        scores = scorer.score_all(vault)
        rel_path = str(note.relative_to(vault))
        assert scores[rel_path] < 0.3  # >18 months old, daily log half-life 30d

    def test_resource_ages_slower(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "03_Resources").mkdir()

        note = vault / "03_Resources" / "resource.md"
        note.write_text(
            '---\ntype: Resource\ntitle: "Old Resource"\n'
            'description: "A resource"\n'
            "timestamp: 2025-06-01T00:00:00\n---\n\nContent."
        )

        scorer = FreshnessScorer()
        scores = scorer.score_all(vault)
        rel_path = str(note.relative_to(vault))
        # Resource half-life is 365d, ~13 months old
        assert 0.3 < scores[rel_path] < 1.0


class TestUsageTracker:
    def test_track_and_count(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path)
        tracker.track_access("note_a.md")
        tracker.track_access("note_a.md")
        tracker.track_access("note_b.md")

        assert tracker.get_count("note_a.md") == 2
        assert tracker.get_count("note_b.md") == 1
        assert tracker.get_count("nonexistent.md") == 0

    def test_get_all_counts(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path)
        tracker.track_access("a.md")
        tracker.track_access("a.md")
        tracker.track_access("b.md")

        counts = tracker.get_all_counts()
        assert counts["a.md"] == 2
        assert counts["b.md"] == 1
        assert len(counts) == 2

    def test_get_all_usage(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path)
        tracker.track_access("a.md")
        tracker.track_access("b.md")
        tracker.track_access("b.md")

        usage = tracker.get_all_usage()
        assert usage["a.md"]["access_count"] == 1
        assert usage["b.md"]["access_count"] == 2
        assert "last_accessed" in usage["a.md"]
