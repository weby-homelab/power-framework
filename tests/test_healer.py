"""Tests for frontmatter healer."""

from __future__ import annotations

from pathlib import Path

from power_framework.core import healer as healer_module
from power_framework.core.healer import (
    _extract_first_paragraph,
    _infer_title_from_filename,
    heal_frontmatter,
    heal_vault,
    propagate_rename,
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


class TestHealBackslashEscapes:
    r"""Frontmatter is user data and may legitimately contain backslashes.

    Recognized fields are routed through ``_escape_yaml``, which doubles the
    backslash, so they never triggered this. Unrecognized fields go through
    ``yaml.safe_dump`` and keep a single backslash; the resulting frontmatter
    was then passed to ``re.sub`` as a *string* replacement, where ``\P``
    (AutoCAD MTEXT) is an unknown group escape and raises ``re.error``.
    """

    def test_mtext_escape_in_custom_field_does_not_raise(self, tmp_path: Path):
        note = tmp_path / "cable_table.md"
        note.write_text(
            "---\n"
            "smoke: 'MTEXT guard: (cd:ParseDecimal \"{\\fArial|b0;7.5\\P}\")'\n"
            "timestamp: 2026-01-01T00:00:00\n"
            "---\n\nBody text here.\n",
            encoding="utf-8",
        )
        healed, changes = heal_frontmatter(note.read_text(encoding="utf-8"), note)
        assert changes
        assert "fArial" in healed

    def test_windows_path_in_custom_field_does_not_raise(self, tmp_path: Path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\n"
            "source_dir: 'C:\\Users\\Public\\vault'\n"
            "timestamp: 2026-01-01T00:00:00\n"
            "---\n\nBody text here.\n",
            encoding="utf-8",
        )
        healed, changes = heal_frontmatter(note.read_text(encoding="utf-8"), note)
        assert changes
        assert "Users" in healed

    def test_propagate_rename_survives_backslash_frontmatter(self, tmp_path: Path):
        """`power rename` rewrites frontmatter through the same code path."""
        vault = tmp_path / "vault"
        (vault / "02_Areas").mkdir(parents=True)
        note = vault / "02_Areas" / "referrer.md"
        note.write_text(
            "---\n"
            "type: Area\n"
            'title: "Referrer"\n'
            'description: "Points at the renamed note"\n'
            "source_dir: 'C:\\Users\\Public\\vault'\n"
            "related:\n"
            '  - path: "03_Resources/old_name.md"\n'
            "    relation: depends_on\n"
            "timestamp: 2026-01-01T00:00:00\n"
            "---\n\nBody text here.\n",
            encoding="utf-8",
        )
        updated, _log = propagate_rename(
            vault, "03_Resources/old_name.md", "03_Resources/new_name.md", dry_run=False
        )
        assert updated == 1
        assert "03_Resources/new_name.md" in note.read_text(encoding="utf-8")

    def test_one_unhealable_note_does_not_abort_the_vault(self, tmp_path: Path, monkeypatch):
        """A single failing note must cost one note, not the whole run."""
        vault = tmp_path / "vault"
        (vault / "01_Projects").mkdir(parents=True)
        for name in ("a_note.md", "poison.md", "z_note.md"):
            (vault / "01_Projects" / name).write_text(
                '---\ndescription: "Desc"\ntimestamp: 2026-01-01T00:00:00\n---\n\nBody text.',
                encoding="utf-8",
            )

        real_heal = healer_module.heal_frontmatter

        def explode(content, filepath, vault_dir=None):
            if filepath.name == "poison.md":
                raise ValueError("simulated per-note failure")
            return real_heal(content, filepath, vault_dir)

        monkeypatch.setattr(healer_module, "heal_frontmatter", explode)
        report = heal_vault(vault, dry_run=False)

        assert "Notes healed: 2" in report
        assert "Notes failed: 1" in report
        assert "poison.md" in report
        assert "type: Project" in (vault / "01_Projects" / "z_note.md").read_text(encoding="utf-8")
