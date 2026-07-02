"""Tests for vault indexer."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_core.indexer import (
    generate_index_content,
    run_generate_index,
    scan_vault_notes,
)


class TestScanVaultNotes:
    """Tests for vault scanning."""

    def test_scan_valid_vault(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        assert "Project" in concepts
        assert "Area" in concepts
        assert "Resource" in concepts
        assert "Daily Log" in concepts

    def test_scan_counts(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        total = sum(len(v) for v in concepts.values())
        assert total == 4

    def test_scan_excludes_templates(self, sample_vault: Path):
        (sample_vault / "05_Templates").mkdir()
        template = sample_vault / "05_Templates" / "Template.md"
        template.write_text(
            "---\ntype: Project\ntitle: Template\ndescription: Should be excluded\ntimestamp: 2026-01-01T00:00:00\n---\n"
        )
        concepts = scan_vault_notes(sample_vault)
        total = sum(len(v) for v in concepts.values())
        assert total == 4

    def test_scan_empty_vault(self, tmp_path: Path):
        vault = tmp_path / "empty_vault"
        vault.mkdir()
        concepts = scan_vault_notes(vault)
        assert concepts == {}


class TestGenerateIndexContent:
    """Tests for index content generation."""

    def test_generates_sections(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        content = generate_index_content(concepts)
        assert "## Projects" in content
        assert "## Areas" in content
        assert "## Resources" in content

    def test_contains_frontmatter(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        content = generate_index_content(concepts)
        assert content.startswith("---")
        assert "type: System Guide" in content

    def test_sorted_by_type_order(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        content = generate_index_content(concepts)
        project_pos = content.index("## Projects")
        area_pos = content.index("## Areas")
        resource_pos = content.index("## Resources")
        assert project_pos < area_pos < resource_pos


class TestRunGenerateIndex:
    """Tests for full index generation."""

    def test_creates_index_file(self, sample_vault: Path):
        index_path = sample_vault / "index.md"
        assert not index_path.exists()

        result = run_generate_index(sample_vault)

        assert index_path.exists()
        assert "4 concepts" in result

    def test_index_content_valid(self, sample_vault: Path):
        run_generate_index(sample_vault)
        index_path = sample_vault / "index.md"
        content = index_path.read_text(encoding="utf-8")
        assert "Test Project" in content
        assert "Test Area" in content
        assert "Test Resource" in content

    def test_overwrites_existing_index(self, sample_vault: Path):
        index_path = sample_vault / "index.md"
        index_path.write_text("Old content")

        run_generate_index(sample_vault)

        content = index_path.read_text(encoding="utf-8")
        assert "Old content" not in content
        assert "Test Project" in content
