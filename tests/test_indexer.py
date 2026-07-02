"""Tests for vault indexer."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_core.indexer import (
    generate_hierarchical_index,
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


class TestGenerateHierarchicalIndex:
    """Tests for hierarchical index generation."""

    def test_generates_main_and_sub_indexes(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        assert "index.md" in outputs
        assert any(k.endswith("/_index.md") for k in outputs)

    def test_main_index_is_summary_only(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        main_content = outputs["index.md"]
        # Main should have section headers with counts, not individual entries
        assert "## Projects (1 notes)" in main_content
        assert "## Areas (1 notes)" in main_content
        # Main should NOT have individual note links (those go in sub-indexes)
        assert "TestProject.md" not in main_content

    def test_sub_index_contains_entries(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        # Find the Projects sub-index
        project_index = outputs.get("01_Projects/_index.md", "")
        assert "Test Project" in project_index
        assert "01_Projects/TestProject.md" in project_index

    def test_sub_index_has_frontmatter(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        for path, content in outputs.items():
            if path.endswith("/_index.md"):
                assert content.startswith("---")
                assert "type: System Guide" in content

    def test_all_folders_have_index(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        # Each folder with notes should have a _index.md
        sub_indexes = [k for k in outputs if k.endswith("/_index.md")]
        # We have notes in 01_Projects, 02_Areas, 03_Resources, 06_Daily_Logs
        assert len(sub_indexes) >= 4

    def test_main_index_has_frontmatter(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        main_content = outputs["index.md"]
        assert main_content.startswith("---")
        assert "type: System Guide" in main_content
        assert "Hierarchical registry" in main_content


class TestRunGenerateIndex:
    """Tests for full hierarchical index generation."""

    def test_creates_index_file(self, sample_vault: Path):
        index_path = sample_vault / "index.md"
        assert not index_path.exists()

        result = run_generate_index(sample_vault)

        assert index_path.exists()
        assert "hierarchical" in result.lower()
        assert "4 concepts" in result

    def test_creates_sub_index_files(self, sample_vault: Path):
        run_generate_index(sample_vault)

        # Check that sub-index files were actually written
        project_index = sample_vault / "01_Projects" / "_index.md"
        assert project_index.exists()
        content = project_index.read_text(encoding="utf-8")
        assert "Test Project" in content

    def test_overwrites_existing_index(self, sample_vault: Path):
        index_path = sample_vault / "index.md"
        index_path.write_text("Old content")

        run_generate_index(sample_vault)

        content = index_path.read_text(encoding="utf-8")
        assert "Old content" not in content
        # In hierarchical mode, main index has section headers, not individual entries
        assert "## Projects" in content
        assert "01_Projects/_index.md" in content

    def test_index_content_valid(self, sample_vault: Path):
        run_generate_index(sample_vault)
        index_path = sample_vault / "index.md"
        content = index_path.read_text(encoding="utf-8")
        assert "## Projects" in content
        assert "## Areas" in content
        assert "## Resources" in content
