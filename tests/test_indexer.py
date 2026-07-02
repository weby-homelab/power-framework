"""Tests for vault indexer."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_core.indexer import (
    generate_hierarchical_index,
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


class TestHierarchicalIndex:
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

    def test_hierarchical_mode_creates_files(self, sample_vault: Path):
        result = run_generate_index(sample_vault, mode="hierarchical")

        assert sample_vault / "index.md"
        assert "hierarchical" in result.lower()
        assert "4 concepts" in result

    def test_hierarchical_writes_sub_index_files(self, sample_vault: Path):
        run_generate_index(sample_vault, mode="hierarchical")

        # Check that sub-index files were actually written
        project_index = sample_vault / "01_Projects" / "_index.md"
        assert project_index.exists()
        content = project_index.read_text(encoding="utf-8")
        assert "Test Project" in content

    def test_hierarchical_main_smaller_than_flat(self, sample_vault: Path):
        """Hierarchical main should be smaller than flat at scale (10+ notes per type)."""
        # Add more notes to make the comparison meaningful
        for i in range(15):
            note = sample_vault / "01_Projects" / f"BulkProject_{i:03d}.md"
            note.write_text(
                f'---\ntype: Project\ntitle: "Bulk Project {i}"\ndescription: "A bulk project note for testing scale"\ntimestamp: 2026-01-01T00:00:00\n---\n\n# Bulk Project {i}\n'
            )

        concepts = scan_vault_notes(sample_vault)

        flat_content = generate_index_content(concepts)
        hier_outputs = generate_hierarchical_index(sample_vault, concepts)
        main_content = hier_outputs["index.md"]

        # Main hierarchical index should be significantly smaller than flat
        assert len(main_content) < len(flat_content)

    def test_flat_mode_is_default(self, sample_vault: Path):
        result = run_generate_index(sample_vault)
        assert "Generated index.md" in result

        result_hier = run_generate_index(sample_vault, mode="hierarchical")
        assert "hierarchical" in result_hier.lower()

    def test_hierarchical_all_folders_have_index(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        outputs = generate_hierarchical_index(sample_vault, concepts)

        # Each folder with notes should have a _index.md
        sub_indexes = [k for k in outputs if k.endswith("/_index.md")]
        # We have notes in 01_Projects, 02_Areas, 03_Resources, 06_Daily_Logs
        assert len(sub_indexes) >= 4
