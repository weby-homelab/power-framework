"""Tests for frontmatter healer."""

from __future__ import annotations

from pathlib import Path

from power_framework.core.healer import (
    _extract_first_paragraph,
    _infer_title_from_filename,
    heal_frontmatter,
    heal_vault,
)


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
