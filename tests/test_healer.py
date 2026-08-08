"""Tests for frontmatter healer."""

from __future__ import annotations

from pathlib import Path

import pytest

import power_framework.core.healer as healer_module
from power_framework.core.cli import _cmd_heal
from power_framework.core.healer import (
    _extract_first_paragraph,
    _infer_title_from_filename,
    heal_frontmatter,
    heal_vault,
    heal_vault_report,
)
from power_framework.core.parser import parse_frontmatter, validate_metadata


class TestInferTitleFromFilename:
    def test_snake_case(self):
        assert _infer_title_from_filename(Path("test_note.md")) == "Test Note"

    def test_kebab_case(self):
        assert _infer_title_from_filename(Path("my-project-guide.md")) == "My Project Guide"

    def test_date_prefix(self):
        assert _infer_title_from_filename(Path("2026-01-01_daily_log.md")) == "Daily Log"

    def test_already_title(self):
        assert _infer_title_from_filename(Path("HelloWorld.md")) == "Helloworld"

    def test_single_word(self):
        assert _infer_title_from_filename(Path("readme.md")) == "Readme"


class TestExtractFirstParagraph:
    def test_basic(self):
        content = "---\ntitle: Test\n---\n\n# Header\n\nThis is the first paragraph."
        assert _extract_first_paragraph(content) == "This is the first paragraph."

    def test_ignores_header(self):
        content = "---\ntitle: Test\n---\n\n# Header\n\n## Sub\n\nReal content here."
        assert _extract_first_paragraph(content) == "Real content here."

    def test_no_frontmatter(self):
        content = "Just text without frontmatter."
        assert _extract_first_paragraph(content) == "Just text without frontmatter."

    def test_empty(self):
        assert _extract_first_paragraph("") == ""


class TestHealFrontmatter:
    def test_no_changes_needed(self, valid_note_content: str, tmp_path: Path):
        fp = tmp_path / "test.md"
        _, changes = heal_frontmatter(valid_note_content, fp)
        assert changes == []

    def test_adds_missing_title(self, tmp_path: Path):
        fp = tmp_path / "my_awesome_note.md"
        content = '---\ntype: Project\ndescription: "A test"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody text.'
        healed, changes = heal_frontmatter(content, fp)
        assert "Added missing title: 'My Awesome Note'" in changes
        assert "My Awesome Note" in healed

    def test_adds_missing_description(self, tmp_path: Path):
        fp = tmp_path / "test.md"
        content = '---\ntype: Project\ntitle: "Test"\ntimestamp: 2026-01-01T00:00:00\n---\n\n# Header\n\nFirst real paragraph here.'
        healed, changes = heal_frontmatter(content, fp)
        assert any("Added missing description" in c for c in changes)
        assert "First real paragraph here" in healed

    def test_adds_missing_timestamp(self, tmp_path: Path):
        fp = tmp_path / "test.md"
        content = '---\ntype: Project\ntitle: "Test"\ndescription: "Desc"\n---\n\nBody.'
        _, changes = heal_frontmatter(content, fp, None)
        assert "Added missing timestamp" in changes

    def test_infers_type_from_folder(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()
        fp = vault / "01_Projects" / "note.md"
        fp.write_text(
            '---\ntitle: "Test"\ndescription: "Desc"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody.'
        )
        content = fp.read_text()
        healed, changes = heal_frontmatter(content, fp, vault)
        assert "Added missing type: Project" in changes
        assert "type: Project" in healed

    def test_fixes_type_casing(self, tmp_path: Path):
        fp = tmp_path / "test.md"
        content = '---\ntype: project\ntitle: "Test"\ndescription: "Desc"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody.'
        healed, changes = heal_frontmatter(content, fp)
        assert any("Fixed type casing" in c for c in changes)
        assert "type: Project" in healed

    def test_preserves_existing_fields(self, tmp_path: Path):
        fp = tmp_path / "test.md"
        content = '---\ntype: Project\ntitle: "Test"\ndescription: "Desc"\nresource: "https://example.com"\ntags: [a, b]\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody.'
        healed, changes = heal_frontmatter(content, fp)
        assert changes == []
        assert 'resource: "https://example.com"' in healed
        assert "tags: [a, b]" in healed

    def test_no_frontmatter_at_all(self, tmp_path: Path):
        fp = tmp_path / "no_frontmatter_note.md"
        content = "Just a plain markdown file."
        healed, changes = heal_frontmatter(content, fp)
        assert len(changes) > 0
        assert "No frontmatter found" in changes[0]
        assert "---" in healed


class TestHealVault:
    def test_dry_run_reports_but_does_not_modify(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()
        note = vault / "01_Projects" / "my_note.md"
        note.write_text(
            '---\ndescription: "Desc"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody text here.'
        )
        report = heal_vault(vault, dry_run=True)
        assert "DRY RUN" in report
        assert "Changes" in report
        # File should not be modified
        content = note.read_text()
        assert "type: Project" not in content

    def test_live_heals_and_backs_up(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()
        note = vault / "01_Projects" / "my_note.md"
        note.write_text(
            '---\ndescription: "Desc"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody text here.'
        )
        report = heal_vault(vault, dry_run=False)
        assert "LIVE" in report
        content = note.read_text()
        assert "type: Project" in content


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mtext", r'MTEXT guard: (cd:ParseDecimal "{\fArial|b0;7.5\P}")'),
        ("windows_path", r"C:\Users\Public\vault"),
        ("latex", r"\\frac{a}{b} and \\text{literal}"),
    ],
    ids=["mtext", "windows-path", "latex"],
)
def test_generated_frontmatter_preserves_backslashes(
    tmp_path: Path,
    field: str,
    value: str,
):
    """Generated YAML must not be interpreted as a regular-expression template."""
    note = tmp_path / f"{field}.md"
    content = (
        f"---\ncustom_{field}: '{value}'\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody text here.\n"
    )

    healed, changes = heal_frontmatter(content, note)

    assert changes
    assert parse_frontmatter(healed)[f"custom_{field}"] == value


def test_healer_quarantines_blocking_foreign_fields_before_cosmetic_fixes(tmp_path: Path):
    note = tmp_path / "foreign.md"
    content = (
        "---\n"
        "type: Resource\n"
        "description: Desc\n"
        "status: verified-external\n"
        "related: [[Назва]]\n"
        "timestamp: 2026-01-01T00:00:00\n"
        "---\n\nBody text.\n"
    )

    healed, changes = heal_frontmatter(content, note)
    data = parse_frontmatter(healed)

    assert changes[0].startswith("Quarantined foreign status")
    assert any(change.startswith("Quarantined foreign related") for change in changes)
    assert "status" not in data
    assert "related" not in data
    assert data["x-status"] == "verified-external"
    assert data["x-related"] == [["Назва"]]
    assert validate_metadata(healed) is not None


def _write_incomplete_note(vault: Path, name: str) -> Path:
    note = vault / "01_Projects" / name
    note.write_text(
        '---\ndescription: "Desc"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody text.',
        encoding="utf-8",
    )
    return note


def test_heal_report_isolates_transform_failures_and_returns_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    good = _write_incomplete_note(vault, "good.md")
    bad = _write_incomplete_note(vault, "bad.md")

    real_heal = healer_module.heal_frontmatter

    def fail_one(content, filepath, vault_dir=None):
        if filepath == bad:
            raise ValueError("simulated transform failure")
        return real_heal(content, filepath, vault_dir)

    monkeypatch.setattr(healer_module, "heal_frontmatter", fail_one)
    report = heal_vault_report(vault, dry_run=False)

    assert report.exit_code == 1
    assert report.scanned == 2
    assert report.healed == 1
    assert [(failure.path, failure.stage) for failure in report.failures] == [
        ("01_Projects/bad.md", "transform")
    ]
    assert "Notes failed: 1" in report.format()
    assert "No notes needed healing" not in report.format()
    assert "type: Project" in good.read_text(encoding="utf-8")
    assert "type: Project" not in bad.read_text(encoding="utf-8")


def test_heal_report_isolates_invalid_frontmatter_as_validation_failure(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    good = _write_incomplete_note(vault, "good.md")
    bad = vault / "01_Projects" / "malformed.md"
    bad.write_text(
        "---\ntype: [not valid\ntimestamp: 2026-01-01\n---\n\nBody.",
        encoding="utf-8",
    )

    report = heal_vault_report(vault, dry_run=False)

    assert report.exit_code == 1
    assert report.healed == 1
    assert [(failure.path, failure.stage) for failure in report.failures] == [
        ("01_Projects/malformed.md", "validation")
    ]
    assert "type: Project" in good.read_text(encoding="utf-8")
    assert bad.read_text(encoding="utf-8").startswith("---\ntype: [not valid")


def test_heal_report_captures_read_failures_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    good = _write_incomplete_note(vault, "good.md")
    bad = _write_incomplete_note(vault, "unreadable.md")

    real_read = healer_module.read_file_content

    def fail_one(filepath):
        if filepath == bad:
            raise UnicodeError("simulated decode failure")
        return real_read(filepath)

    monkeypatch.setattr(healer_module, "read_file_content", fail_one)
    report = heal_vault_report(vault, dry_run=False)

    assert report.exit_code == 1
    assert report.failures[0].stage == "read"
    assert report.failures[0].path == "01_Projects/unreadable.md"
    assert "type: Project" in good.read_text(encoding="utf-8")
    assert "type: Project" not in bad.read_text(encoding="utf-8")


def test_write_failure_leaves_original_note_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    note = _write_incomplete_note(vault, "write-failure.md")
    original = note.read_text(encoding="utf-8")

    def refuse_write(*_args, **_kwargs):
        raise ValueError("simulated atomic write failure")

    monkeypatch.setattr(healer_module, "atomic_write", refuse_write)
    report = heal_vault_report(vault, dry_run=False)

    assert report.exit_code == 1
    assert report.healed == 0
    assert report.failures[0].stage == "write"
    assert note.read_text(encoding="utf-8") == original
    assert "No notes needed healing" not in report.format()


def test_cli_heal_returns_nonzero_for_partial_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    note = _write_incomplete_note(vault, "broken.md")

    def fail_transform(*_args, **_kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(healer_module, "heal_frontmatter", fail_transform)
    exit_code = _cmd_heal(
        type("Args", (), {"path": str(vault), "no_dry_run": True, "limit": None})()
    )

    assert exit_code == 1
    assert "type: Project" not in note.read_text(encoding="utf-8")
