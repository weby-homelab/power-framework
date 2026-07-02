"""Tests for vault indexer."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_core.indexer import (
    generate_index_content,
    generate_main_index_content,
    generate_sub_index_content,
    run_generate_hierarchical_index,
    run_generate_index,
    run_generate_sub_index,
    scan_folder_notes,
    scan_vault_notes,
)


class TestScanVaultNotes:
    """Tests for vault scanning (flat, legacy)."""

    def test_scan_valid_vault(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        assert "Project" in concepts
        assert "Area" in concepts
        assert "Resource" in concepts
        assert "Daily Log" in concepts

    def test_scan_counts(self, sample_vault: Path):
        concepts = scan_vault_notes(sample_vault)
        total = sum(len(v) for v in concepts.values())
        assert total == 5

    def test_scan_excludes_templates(self, sample_vault: Path):
        (sample_vault / "05_Templates").mkdir()
        template = sample_vault / "05_Templates" / "Template.md"
        template.write_text(
            "---\ntype: Project\ntitle: Template\ndescription: Should be excluded\ntimestamp: 2026-01-01T00:00:00\n---\n"
        )
        concepts = scan_vault_notes(sample_vault)
        total = sum(len(v) for v in concepts.values())
        assert total == 5

    def test_scan_empty_vault(self, tmp_path: Path):
        vault = tmp_path / "empty_vault"
        vault.mkdir()
        concepts = scan_vault_notes(vault)
        assert concepts == {}


class TestScanFolderNotes:
    """Tests for hierarchical folder-based scanning."""

    def test_scan_groups_by_folder(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        assert "01_Projects" in folder_notes
        assert "02_Areas" in folder_notes
        assert "03_Resources" in folder_notes
        assert "06_Daily_Logs" in folder_notes

    def test_scan_folder_note_count(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        assert len(folder_notes["01_Projects"]) == 2
        assert len(folder_notes["02_Areas"]) == 1
        assert len(folder_notes["03_Resources"]) == 1
        assert len(folder_notes["06_Daily_Logs"]) == 1

    def test_scan_nested_notes(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        project_notes = folder_notes["01_Projects"]
        titles = [n["title"] for n in project_notes]
        assert "Test Project" in titles
        assert "Weby-QRank Architecture" in titles

    def test_scan_note_info_structure(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        note = folder_notes["01_Projects"][0]
        assert "rel_path" in note
        assert "title" in note
        assert "description" in note
        assert "note_type" in note
        assert "tags" in note
        assert "timestamp" in note
        assert "filename" in note

    def test_scan_excludes_index_files(self, sample_vault: Path):
        (sample_vault / "01_Projects" / "_index.md").write_text("# Sub Index")
        folder_notes = scan_folder_notes(sample_vault)
        for notes in folder_notes.values():
            for note in notes:
                assert note["filename"] != "_index.md"
                assert note["filename"] != "index.md"


class TestGenerateIndexContent:
    """Tests for flat index content generation (legacy)."""

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


class TestGenerateMainIndexContent:
    """Tests for hierarchical main index generation."""

    def test_contains_navigation_table(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_main_index_content(folder_notes)
        assert "| Category | Notes | Sub-Index |" in content

    def test_contains_sub_index_links(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_main_index_content(folder_notes)
        assert "01_Projects/_index.md" in content
        assert "02_Areas/_index.md" in content
        assert "03_Resources/_index.md" in content

    def test_contains_note_counts(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_main_index_content(folder_notes)
        assert "| 01 Projects | 2 |" in content
        assert "| 02 Areas | 1 |" in content

    def test_contains_agent_protocol(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_main_index_content(folder_notes)
        assert "## Agent Protocol" in content
        assert "Read this file" in content
        assert "Read the sub-index" in content

    def test_contains_frontmatter(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_main_index_content(folder_notes)
        assert content.startswith("---")
        assert "type: System Guide" in content


class TestGenerateSubIndexContent:
    """Tests for per-folder sub-index generation."""

    def test_generates_detailed_entries(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_sub_index_content("01_Projects", folder_notes["01_Projects"])
        assert "## Test Project" in content
        assert "## Weby-QRank Architecture" in content

    def test_contains_note_metadata(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_sub_index_content("01_Projects", folder_notes["01_Projects"])
        assert "**Path:**" in content
        assert "**Type:**" in content
        assert "**Description:**" in content
        assert "**Tags:**" in content
        assert "**Updated:**" in content

    def test_contains_frontmatter(self, sample_vault: Path):
        folder_notes = scan_folder_notes(sample_vault)
        content = generate_sub_index_content("01_Projects", folder_notes["01_Projects"])
        assert content.startswith("---")
        assert "type: System Guide" in content

    def test_empty_folder_generates_clean_index(self):
        content = generate_sub_index_content("00_Inbox", [])
        assert content.startswith("---")
        assert "00 Inbox" in content
        assert "## " not in content.split("---")[2]


class TestRunGenerateIndex:
    """Tests for flat index generation (legacy)."""

    def test_creates_index_file(self, sample_vault: Path):
        index_path = sample_vault / "index.md"
        assert not index_path.exists()

        result = run_generate_index(sample_vault)

        assert index_path.exists()
        assert "5 concepts" in result

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


class TestRunGenerateSubIndex:
    """Tests for per-folder sub-index generation."""

    def test_creates_sub_index_file(self, sample_vault: Path):
        sub_index_path = sample_vault / "01_Projects" / "_index.md"
        assert not sub_index_path.exists()

        result = run_generate_sub_index(sample_vault, "01_Projects")

        assert sub_index_path.exists()
        assert "2 entries" in result

    def test_sub_index_content_valid(self, sample_vault: Path):
        run_generate_sub_index(sample_vault, "01_Projects")
        sub_index_path = sample_vault / "01_Projects" / "_index.md"
        content = sub_index_path.read_text(encoding="utf-8")
        assert "Test Project" in content
        assert "Weby-QRank Architecture" in content


class TestRunGenerateHierarchicalIndex:
    """Tests for full hierarchical index generation."""

    def test_creates_main_index(self, sample_vault: Path):
        main_index = sample_vault / "index.md"
        assert not main_index.exists()

        result = run_generate_hierarchical_index(sample_vault)

        assert main_index.exists()
        assert "5 total notes" in result

    def test_creates_sub_indexes(self, sample_vault: Path):
        run_generate_hierarchical_index(sample_vault)

        assert (sample_vault / "01_Projects" / "_index.md").exists()
        assert (sample_vault / "02_Areas" / "_index.md").exists()
        assert (sample_vault / "03_Resources" / "_index.md").exists()
        assert (sample_vault / "06_Daily_Logs" / "_index.md").exists()

    def test_main_index_links_to_sub_indexes(self, sample_vault: Path):
        run_generate_hierarchical_index(sample_vault)
        main_index = sample_vault / "index.md"
        content = main_index.read_text(encoding="utf-8")
        assert "01_Projects/_index.md" in content
        assert "02_Areas/_index.md" in content

    def test_sub_index_contains_all_notes(self, sample_vault: Path):
        run_generate_hierarchical_index(sample_vault)
        sub_index = sample_vault / "01_Projects" / "_index.md"
        content = sub_index.read_text(encoding="utf-8")
        assert "Test Project" in content
        assert "Weby-QRank Architecture" in content

    def test_overwrites_existing_indexes(self, sample_vault: Path):
        main_index = sample_vault / "index.md"
        main_index.write_text("Old main content")

        sub_index = sample_vault / "01_Projects" / "_index.md"
        sub_index.parent.mkdir(parents=True, exist_ok=True)
        sub_index.write_text("Old sub content")

        run_generate_hierarchical_index(sample_vault)

        main_content = main_index.read_text(encoding="utf-8")
        assert "Old main content" not in main_content
        assert "Navigation Map" in main_content

        sub_content = sub_index.read_text(encoding="utf-8")
        assert "Old sub content" not in sub_content
