"""Tests for vault linter."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_framework.core.ignore import in_kb_scope, is_ignored
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

    def test_protocol_path_link_resolves(self, tmp_path: Path):
        protocols = tmp_path / "PROTOCOLS"
        projects = tmp_path / "01_Projects"
        protocols.mkdir()
        projects.mkdir()
        (protocols / "Home.md").write_text(
            '---\ntype: System Guide\ntitle: "Home"\ndescription: "Vault home"\n'
            "timestamp: 2026-07-21T00:00:00Z\n---\n\n# Home\n"
        )
        (projects / "Project.md").write_text(
            '---\ntype: Project\ntitle: "Project"\ndescription: "Project note"\n'
            "timestamp: 2026-07-21T00:00:00Z\n---\n\n[[PROTOCOLS/Home|Home]]\n"
        )

        result = run_lint_vault(tmp_path)

        assert result.total_notes == 2
        assert result.broken_links == []

    def test_archive_and_root_daily_log_are_not_orphans(self, tmp_path: Path):
        archive = tmp_path / "04_Archive"
        archive.mkdir()
        (archive / "Old.md").write_text(
            '---\ntype: Archive\ntitle: "Old"\ndescription: "Archived note"\n'
            "timestamp: 2026-07-21T00:00:00Z\n---\n\n# Old\n"
        )
        (tmp_path / "2026-07-21_session.md").write_text(
            '---\ntype: Daily Log\ntitle: "Session"\ndescription: "Root daily log"\n'
            "timestamp: 2026-07-21T00:00:00Z\n---\n\n# Session\n"
        )

        result = run_lint_vault(tmp_path)

        assert result.orphans == []

    def test_archived_status_is_not_orphan(self, tmp_path: Path):
        projects = tmp_path / "01_Projects"
        projects.mkdir()
        (projects / "Completed.md").write_text(
            '---\ntype: Project\ntitle: "Completed"\ndescription: "Completed project"\n'
            "status: archived\ntimestamp: 2026-07-21T00:00:00Z\n---\n\n# Completed\n"
        )

        result = run_lint_vault(tmp_path)

        assert result.orphans == []


class TestOkfScope:
    """Foreign files outside the OKF knowledge base must not raise metadata warnings."""

    def test_para_and_brain_in_scope(self):
        assert in_kb_scope("01_Projects/Foo.md")
        assert in_kb_scope("brain/01_Projects/Foo.md")
        assert in_kb_scope("PROTOCOLS/Home.md")
        assert in_kb_scope("06_Daily_Logs/2026-01-01.md")

    def test_root_daily_log_in_scope(self):
        assert in_kb_scope("2026-07-11_note.md")

    def test_system_index_files_not_in_scope(self):
        assert not in_kb_scope("index.md")
        assert not in_kb_scope("log.md")
        assert not in_kb_scope("_index.md")

    def test_foreign_repo_out_of_scope(self):
        assert not in_kb_scope("projects/Foo/README.md")
        assert not in_kb_scope("node_modules/lib/docs/guide.md")

    def test_root_repo_meta_out_of_scope(self):
        assert not in_kb_scope("GEMINI.md")
        assert not in_kb_scope("LACA.md")

    def test_foreign_md_not_flagged(self, sample_vault: Path):
        # A markdown file inside a foreign source repo must not be linted for OKF metadata.
        foreign = sample_vault / "projects" / "SomeRepo"
        (foreign / "docs").mkdir(parents=True)
        (foreign / "README.md").write_text("# Some Repo\n\nNo frontmatter here.\n")
        (foreign / "docs" / "guide.md").write_text("# Guide\n\nNo frontmatter either.\n")
        # Subdir of a legitimate PARA note is still OKF (has frontmatter elsewhere) ...
        nested = sample_vault / "01_Projects" / "Weby-QRank" / "sub"
        nested.mkdir(parents=True)
        (nested / "no_frontmatter_here.md").write_text("# Nested\n\nNo frontmatter.\n")
        result = run_lint_vault(sample_vault)
        flagged = [rp for rp, _ in result.untyped_files]
        assert not any("projects/SomeRepo" in rp for rp in flagged)
        # ... but a genuine OKF note missing frontmatter is still caught
        assert any("no_frontmatter_here.md" in rp for rp in flagged)

    def test_node_modules_doc_not_flagged(self, sample_vault: Path):
        vendored = sample_vault / "node_modules" / "@scope" / "pkg" / "README.md"
        vendored.parent.mkdir(parents=True)
        vendored.write_text("# Vendored\n\nNo frontmatter.\n")
        result = run_lint_vault(sample_vault)
        flagged = [rp for rp, _ in result.untyped_files]
        assert not any("node_modules" in rp for rp in flagged)


class TestPowerignore:
    """The optional .powerignore file (gitignore syntax) excludes files from linting."""

    def test_is_ignored_missing_returns_false(self, tmp_path: Path):
        assert not is_ignored(tmp_path, "somefile.md")

    def test_powerignore_excludes_matching_paths(self, tmp_path: Path):
        (tmp_path / ".powerignore").write_text("vendor/\ndocs/\n")
        assert is_ignored(tmp_path, "vendor/lib/x.md")
        assert is_ignored(tmp_path, "docs/guide.md")
        assert not is_ignored(tmp_path, "01_Projects/Foo.md")

    def test_powerignore_applied_by_linter(self, sample_vault: Path):
        (sample_vault / ".powerignore").write_text("projects/\n")
        foreign = sample_vault / "projects" / "Repo" / "NOTE.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("# Repo note\n\nNo frontmatter.\n")
        result = run_lint_vault(sample_vault)
        flagged = [rp for rp, _ in result.untyped_files]
        assert not any("projects/Repo" in rp for rp in flagged)


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
