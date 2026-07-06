"""
Tests for ROT (Redundant, Outdated, Trivial) audit and auto-archive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path  # noqa: TC003

from power_framework.core.linter import (
    ROTResult,
    _get_body_content,
    _title_similarity,
    archive_stale_notes,
    run_rot_audit,
    run_rot_report,
)


class TestROTResult:
    """Tests for ROTResult container."""

    def test_no_issues(self):
        result = ROTResult()
        assert not result.has_issues
        assert result.total_issues == 0

    def test_has_redundant(self):
        result = ROTResult()
        result.redundant.append(("a.md", "b.md", 0.8))
        assert result.has_issues
        assert result.total_issues == 1

    def test_has_outdated(self):
        result = ROTResult()
        result.outdated.append(("old.md", "Expired"))
        assert result.has_issues

    def test_has_trivial(self):
        result = ROTResult()
        result.trivial.append(("small.md", 10))
        assert result.has_issues


class TestTitleSimilarity:
    """Tests for Jaccard title similarity."""

    def test_identical(self):
        assert _title_similarity("Hello World", "Hello World") == 1.0

    def test_partial_overlap(self):
        sim = _title_similarity("Docker Setup Guide", "Docker Configuration Guide")
        assert 0.3 < sim < 0.9

    def test_no_overlap(self):
        assert _title_similarity("Alpha Beta", "Gamma Delta") == 0.0

    def test_empty_titles(self):
        assert _title_similarity("", "") == 0.0


class TestGetBodyContent:
    """Tests for body content extraction."""

    def test_with_frontmatter(self):
        raw = "---\ntitle: Test\n---\n\n# Body\nContent here."
        assert _get_body_content(raw) == "# Body\nContent here."

    def test_without_frontmatter(self):
        raw = "# No Frontmatter"
        assert _get_body_content(raw) == "# No Frontmatter"


class TestRunRotAudit:
    """Tests for ROT audit on vaults."""

    def test_healthy_vault_has_only_trivial(self, sample_vault: Path):
        result = run_rot_audit(sample_vault)
        # Sample vault notes have very short body content (<50 chars)
        assert len(result.trivial) >= 3
        assert len(result.outdated) == 0
        assert len(result.redundant) == 0

    def test_detects_stale_notes(self, vault_with_issues: Path):
        result = run_rot_audit(vault_with_issues)
        assert len(result.outdated) > 0
        stale_paths = [rp for rp, _ in result.outdated]
        assert any("StaleNote" in rp for rp in stale_paths)

    def test_detects_trivial_note(self, tmp_path: Path):
        vault = tmp_path / "trivial_vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()
        tiny = vault / "01_Projects" / "TinyNote.md"
        tiny.write_text(
            "---\n"
            "type: Project\n"
            'title: "Tiny Note"\n'
            'description: "A very short note"\n'
            f"timestamp: {datetime.now(timezone.utc).isoformat()}\n"
            "---\n\n# Hi\n",
        )
        result = run_rot_audit(vault)
        assert len(result.trivial) >= 1
        tiny_paths = [rp for rp, _ in result.trivial]
        assert any("TinyNote" in rp for rp in tiny_paths)


class TestArchiveStaleNotes:
    """Tests for auto-archiving stale notes."""

    def test_dry_run_does_not_move(self, vault_with_issues: Path):
        archive_dir = vault_with_issues / "04_Archive"
        assert not archive_dir.exists()
        result = archive_stale_notes(vault_with_issues, dry_run=True)
        assert not archive_dir.exists()
        assert "DRY RUN" in result
        assert "StaleNote" in result

    def test_live_move_stale_note(self, vault_with_issues: Path):
        archive_dir = vault_with_issues / "04_Archive"
        assert not archive_dir.exists()
        archive_stale_notes(vault_with_issues, dry_run=False)
        assert archive_dir.exists()
        assert (archive_dir / "StaleNote.md").exists()
        assert not (vault_with_issues / "03_Resources" / "StaleNote.md").exists()

    def test_no_stale_in_healthy(self, sample_vault: Path):
        archive_dir = sample_vault / "04_Archive"
        result = archive_stale_notes(sample_vault, dry_run=False)
        assert "No stale notes found" in result
        assert not archive_dir.exists()


class TestRotReport:
    """Tests for ROT report formatting."""

    def test_healthy_report(self, sample_vault: Path):
        report = run_rot_report(sample_vault)
        assert "ROT Audit" in report
        assert "TRIVIAL" in report

    def test_issues_report(self, vault_with_issues: Path):
        report = run_rot_report(vault_with_issues)
        assert "ROT Audit" in report
        assert "OUTDATED" in report
