"""Tests for vault linter."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_framework.core.linter import LintResult, run_lint_report, run_lint_vault


class TestRunLintVault:
    """Tests for vault linting."""

    def test_healthy_vault(self, sample_vault: Path):
        result = run_lint_vault(sample_vault)
        assert result.total_notes == 5
        assert len(result.untyped_files) == 0
        assert len(result.broken_links) == 0

    def test_detects_no_frontmatter(self, vault_with_issues: Path):
        result = run_lint_vault(vault_with_issues)
        assert len(result.untyped_files) > 0
        untyped_paths = [rp for rp, _ in result.untyped_files]
        assert any("NoFrontmatter.md" in rp for rp in untyped_paths)

    def test_detects_missing_type(self, vault_with_issues: Path):
        result = run_lint_vault(vault_with_issues)
        untyped_paths = [rp for rp, _ in result.untyped_files]
        assert any("NoType.md" in rp for rp in untyped_paths)

    def test_detects_broken_links(self, vault_with_issues: Path):
        result = run_lint_vault(vault_with_issues)
        assert len(result.broken_links) > 0
        broken_sources = [rp for rp, _ in result.broken_links]
        assert any("BrokenLink.md" in rp for rp in broken_sources)

    def test_detects_orphans(self, vault_with_issues: Path):
        result = run_lint_vault(vault_with_issues)
        assert len(result.orphans) > 0
        assert any("Orphan.md" in rp for rp in result.orphans)

    def test_total_notes_count(self, vault_with_issues: Path):
        result = run_lint_vault(vault_with_issues)
        assert result.total_notes == 5

    def test_daily_logs_excluded_from_orphans(self, sample_vault: Path):
        result = run_lint_vault(sample_vault)
        orphan_paths = result.orphans
        assert not any("06_Daily_Logs" in rp for rp in orphan_paths)

    def test_detects_stale_notes(self, vault_with_issues: Path):
        result = run_lint_vault(vault_with_issues)
        assert len(result.stale_notes) > 0
        stale_paths = [rp for rp, _ in result.stale_notes]
        assert any("StaleNote.md" in rp for rp in stale_paths)
        assert any("Expired on" in reason for _, reason in result.stale_notes)

    def test_no_stale_in_healthy_vault(self, sample_vault: Path):
        result = run_lint_vault(sample_vault)
        assert len(result.stale_notes) == 0


class TestLintResult:
    """Tests for LintResult container."""

    def test_no_issues(self):
        result = LintResult()
        result.total_notes = 5
        assert not result.has_issues

    def test_has_untyped(self):
        result = LintResult()
        result.untyped_files.append(("test.md", "No frontmatter"))
        assert result.has_issues

    def test_has_broken(self):
        result = LintResult()
        result.broken_links.append(("test.md", "missing"))
        assert result.has_issues

    def test_has_orphans(self):
        result = LintResult()
        result.orphans.append("orphan.md")
        assert result.has_issues

    def test_has_stale(self):
        result = LintResult()
        result.stale_notes.append(("stale.md", "Expired on 2020-01-01"))
        assert result.has_issues


class TestLintReport:
    """Tests for formatted lint report."""

    def test_healthy_report(self, sample_vault: Path):
        report = run_lint_report(sample_vault)
        assert "Health Lint Report" in report
        assert "healthy" in report.lower() or "Zero errors" in report

    def test_issues_report(self, vault_with_issues: Path):
        report = run_lint_report(vault_with_issues)
        assert "Missing/Invalid OKF Metadata" in report
        assert "Broken links" in report
        assert "Orphan notes" in report
        assert "Stale / expired notes" in report

    def test_report_contains_vault_path(self, sample_vault: Path):
        report = run_lint_report(sample_vault)
        assert str(sample_vault) in report
