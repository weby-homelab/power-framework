"""Tests for vault indexer."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

import pytest

from power_framework.core.indexer import (
    _generate_catalog_pages,
    generate_index_content,
    generate_main_index_content,
    generate_sub_index_content,
    run_generate_hierarchical_index,
    run_generate_index,
    run_generate_sub_index,
    scan_folder_notes,
    scan_folder_notes_incremental,
    scan_root_daily_logs,
    scan_vault_notes,
    truncate_for_catalog,
)


def _write_note(path: Path, title: str, description: str = "Test description") -> None:
    """Write a minimal valid note for catalog integration fixtures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: Project\n"
        f"title: '{title}'\n"
        f"description: '{description}'\n"
        "timestamp: 2026-01-01T00:00:00\n"
        "---\n\n"
        f"# {title}\n",
        encoding="utf-8",
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

    def test_indexes_protocols_and_root_daily_logs(self, tmp_path: Path):
        protocols = tmp_path / "PROTOCOLS"
        protocols.mkdir()
        (protocols / "Home.md").write_text(
            '---\ntype: System Guide\ntitle: "Home"\ndescription: "Vault home"\n'
            "timestamp: 2026-07-21T00:00:00Z\n---\n\n# Home\n",
            encoding="utf-8",
        )
        (tmp_path / "2026-07-21_session.md").write_text(
            '---\ntype: Daily Log\ntitle: "Session"\ndescription: "Root session"\n'
            "timestamp: 2026-07-21T00:00:00Z\n---\n\n# Session\n",
            encoding="utf-8",
        )

        folder_notes = scan_folder_notes(tmp_path)
        root_logs = scan_root_daily_logs(tmp_path)
        content = generate_main_index_content(folder_notes, root_logs)

        assert "| PROTOCOLS | 1 |" in content
        assert "2026-07-21_session.md" in content

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

    def test_nested_catalog_link_is_explicitly_relative(self):
        note = {
            "rel_path": "03_Resources/wiki/techniques/Space Note.md",
            "title": "Space Note",
            "description": "A note",
            "note_type": "Resource",
            "tags": [],
            "timestamp": "2026-01-01",
            "filename": "Space Note.md",
            "owner": "",
            "status": "",
            "expiry": "",
            "related": [],
        }
        content = generate_sub_index_content("03_Resources/wiki/techniques", [note])

        assert "`03_Resources/wiki/techniques/Space Note.md`" not in content
        assert "[03_Resources/wiki/techniques/Space Note.md](<./Space Note.md>)" in content
        assert "x-generated-by: power" in content


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

    def test_reports_invalid_notes_in_index_summary(self, tmp_path: Path):
        projects = tmp_path / "01_Projects"
        projects.mkdir()
        (projects / "Invalid.md").write_text(
            "---\n"
            "type: Project\n"
            'title: "Invalid"\n'
            'description: "Invalid resource URL"\n'
            'resource: "not-a-url"\n'
            "timestamp: 2026-07-21T00:00:00Z\n"
            "---\n\n# Invalid\n",
            encoding="utf-8",
        )

        result = run_generate_hierarchical_index(tmp_path)

        assert "WARNING: skipped invalid notes (1)" in result
        assert "01_Projects/Invalid.md: Invalid OKF metadata" in result

    def test_incremental_scan_reuses_unchanged_metadata(self, sample_vault: Path, monkeypatch):
        first, first_invalid, first_count = scan_folder_notes_incremental(sample_vault)
        assert first_invalid == []
        assert first_count == 5

        from power_framework.core import indexer

        original_read = indexer.read_file_content

        def reject_unchanged_read(path: Path) -> str:
            if path.name == "TestProject.md":
                raise AssertionError("unchanged note was read again")
            return original_read(path)

        monkeypatch.setattr(indexer, "read_file_content", reject_unchanged_read)
        second, second_invalid, second_count = scan_folder_notes_incremental(sample_vault)

        assert second_invalid == []
        assert second_count == first_count
        assert second == first

    def test_creates_sub_indexes(self, sample_vault: Path):
        run_generate_hierarchical_index(sample_vault)

        assert (sample_vault / "01_Projects" / "_index.md").exists()
        assert (sample_vault / "02_Areas" / "_index.md").exists()
        assert (sample_vault / "03_Resources" / "_index.md").exists()
        assert (sample_vault / "06_Daily_Logs" / "_index.md").exists()

    def test_recursive_catalogs_resolve_duplicate_nested_names(self, tmp_path: Path):
        _write_note(tmp_path / "01_Projects" / "Top.md", "Top")
        _write_note(tmp_path / "01_Projects" / "nested" / "Same.md", "Nested Same")
        _write_note(tmp_path / "01_Projects" / "nested" / "deep" / "Same.md", "Deep Same")

        run_generate_hierarchical_index(tmp_path)

        from power_framework.core.linter import run_lint_vault

        report = run_lint_vault(tmp_path)
        assert report.orphans == []
        assert report.broken_links == []
        assert report.ambiguous_links == []
        assert (tmp_path / "01_Projects" / "nested" / "deep" / "_index.md").exists()
        parent = (tmp_path / "01_Projects" / "_index.md").read_text(encoding="utf-8")
        assert "<./nested/_index.md>" in parent

    def test_catalog_pages_obey_budget_and_partition_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from power_framework.core import indexer

        monkeypatch.setattr(indexer, "INDEX_MAX_BYTES", 2048)
        for index in range(30):
            _write_note(
                tmp_path / "01_Projects" / f"Note {index:03}.md",
                f"Note {index:03}",
                "x" * 120,
            )

        run_generate_hierarchical_index(tmp_path)
        pages = sorted((tmp_path / "01_Projects").glob("_index*.md"))
        assert len(pages) > 1
        assert all(len(page.read_bytes()) <= 2048 for page in pages)
        assert sum(page.read_text(encoding="utf-8").count("- **Path:**") for page in pages) == 30

        from power_framework.core.linter import run_lint_vault

        report = run_lint_vault(tmp_path)
        assert report.orphans == []
        assert report.broken_links == []

        stale_page = tmp_path / "01_Projects" / "_index-99.md"
        stale_page.write_text(pages[0].read_text(encoding="utf-8"), encoding="utf-8")
        run_generate_hierarchical_index(tmp_path)
        assert not stale_page.exists()

    def test_renderer_migrates_legacy_cached_catalog(self, tmp_path: Path):
        from power_framework.core.vault_storage import vault_cache_dir

        _write_note(tmp_path / "01_Projects" / "Legacy.md", "Legacy")
        run_generate_hierarchical_index(tmp_path)
        catalog = tmp_path / "01_Projects" / "_index.md"
        catalog.write_text(
            "---\n"
            "type: System Guide\n"
            'title: "01 Projects Sub-Index"\n'
            'description: "Detailed catalog of all notes in 01 Projects"\n'
            "---\n\n"
            "legacy `01_Projects/Legacy.md` catalog\n",
            encoding="utf-8",
        )
        cache_path = vault_cache_dir(tmp_path) / "hierarchical-index-cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["renderer_version"] = 1
        cache_path.write_text(json.dumps(cache), encoding="utf-8")

        run_generate_hierarchical_index(tmp_path)

        content = catalog.read_text(encoding="utf-8")
        assert "x-generated-by: power" in content
        assert "<./Legacy.md>" in content
        assert "`01_Projects/Legacy.md`" not in content

    def test_failed_render_invalidates_incremental_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from power_framework.core import indexer

        note = tmp_path / "01_Projects" / "Note.md"
        _write_note(note, "Note")
        run_generate_hierarchical_index(tmp_path)
        note.write_text(note.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")

        original_generate = indexer._generate_catalog_pages

        def fail_once(*args, **kwargs):
            raise RuntimeError("synthetic catalog failure")

        monkeypatch.setattr(indexer, "_generate_catalog_pages", fail_once)
        with pytest.raises(RuntimeError, match="synthetic catalog failure"):
            run_generate_hierarchical_index(tmp_path)

        rendered_folders: list[str] = []

        def record_render(*args, **kwargs):
            rendered_folders.append(args[0])
            return original_generate(*args, **kwargs)

        monkeypatch.setattr(indexer, "_generate_catalog_pages", record_render)
        run_generate_hierarchical_index(tmp_path)
        assert "01_Projects" in rendered_folders

    def test_deleted_nested_directory_removes_owned_catalog(self, tmp_path: Path):
        note_path = tmp_path / "01_Projects" / "nested" / "Gone.md"
        _write_note(note_path, "Gone")
        run_generate_hierarchical_index(tmp_path)
        nested_index = note_path.parent / "_index.md"
        assert nested_index.exists()

        note_path.unlink()
        run_generate_hierarchical_index(tmp_path)

        assert not nested_index.exists()
        parent = (tmp_path / "01_Projects" / "_index.md").read_text(encoding="utf-8")
        assert "nested/_index.md" not in parent
        note_path.parent.rmdir()

    def test_foreign_nested_catalog_is_preserved_and_reported(self, tmp_path: Path):
        note_path = tmp_path / "01_Projects" / "nested" / "Foreign.md"
        _write_note(note_path, "Foreign")
        foreign_index = note_path.parent / "_index.md"
        foreign_index.write_text("# Hand-maintained catalog\n", encoding="utf-8")

        result = run_generate_hierarchical_index(tmp_path)

        assert foreign_index.read_text(encoding="utf-8") == "# Hand-maintained catalog\n"
        assert "WARNING: catalog conflicts preserved" in result

    def test_foreign_top_level_catalog_is_preserved_and_reported(self, tmp_path: Path):
        _write_note(tmp_path / "01_Projects" / "Note.md", "Note")
        foreign_index = tmp_path / "01_Projects" / "_index.md"
        foreign_index.write_text("# Hand-maintained top-level catalog\n", encoding="utf-8")

        result = run_generate_hierarchical_index(tmp_path)

        assert foreign_index.read_text(encoding="utf-8") == "# Hand-maintained top-level catalog\n"
        assert "WARNING: catalog conflicts preserved" in result
        assert "01_Projects/_index.md NOT WRITTEN" in result

    def test_non_numeric_index_name_remains_a_note(self, tmp_path: Path):
        _write_note(tmp_path / "01_Projects" / "_index-foo.md", "Reserved-looking note")

        result = run_generate_hierarchical_index(tmp_path)

        assert "1 total notes" in result
        assert (tmp_path / "01_Projects" / "_index.md").exists()
        assert "Reserved-looking note" in (tmp_path / "01_Projects" / "_index.md").read_text(
            encoding="utf-8"
        )

    def test_large_catalog_renderer_profile_is_bounded(self):
        notes = [
            {
                "rel_path": f"03_Resources/wiki/batch/Note {index:05}.md",
                "title": f"Note {index:05}",
                "description": "description " * 10,
                "note_type": "Resource",
                "tags": [],
                "timestamp": "2026-01-01",
                "filename": f"Note {index:05}.md",
                "owner": "",
                "status": "",
                "expiry": "",
                "related": [],
            }
            for index in range(10_000)
        ]

        pages = _generate_catalog_pages("03_Resources/wiki/batch", notes)

        assert pages
        assert all(len(content.encode("utf-8")) <= 32 * 1024 for content in pages.values())
        assert sum(content.count("- **Path:**") for content in pages.values()) == 10_000

    def test_variable_width_catalog_stays_bounded(self):
        # The uniform-size profile above never lands a page within the width of
        # one navigation link, so it stays green while the bound is short. Real
        # vaults have variable titles; sweeping the limit shifts where pages
        # break and reaches the boundary deterministically.
        notes = [
            {
                "rel_path": f"03_Resources/wiki/batch/Note {index}.md",
                "title": "N" * (1 + index % 37),
                "description": "d" * (1 + index % 53),
                "note_type": "Resource",
                "tags": [],
                "timestamp": "2026-01-01",
                "filename": f"Note {index}.md",
                "owner": "",
                "status": "",
                "expiry": "",
                "related": [],
            }
            for index in range(400)
        ]

        for max_bytes in range(2048, 2048 + 96):
            pages = _generate_catalog_pages("03_Resources/wiki/batch", notes, max_bytes=max_bytes)
            oversized = {
                name: len(content.encode("utf-8"))
                for name, content in pages.items()
                if len(content.encode("utf-8")) > max_bytes
            }
            assert not oversized, f"max_bytes={max_bytes} produced {oversized}"

    def test_10k_variable_width_catalog_stays_bounded(self):
        notes = [
            {
                "rel_path": f"03_Resources/wiki/batch/Note {index}.md",
                "title": "N" * (1 + index % 37),
                "description": "d" * (1 + index % 53),
                "note_type": "Resource",
                "tags": [],
                "timestamp": "2026-01-01",
                "filename": f"Note {index}.md",
                "owner": "",
                "status": "",
                "expiry": "",
                "related": [],
            }
            for index in range(10_000)
        ]

        pages = _generate_catalog_pages("03_Resources/wiki/batch", notes)

        assert pages
        assert all(len(content.encode("utf-8")) <= 32 * 1024 for content in pages.values())
        assert sum(content.count("- **Path:**") for content in pages.values()) == 10_000

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

    def test_unchanged_run_skips_sub_index_rendering(self, sample_vault: Path, monkeypatch):
        run_generate_hierarchical_index(sample_vault)

        from power_framework.core import indexer

        original_generate = indexer._generate_catalog_pages
        rendered_folders: list[str] = []

        def record_render(*args, **kwargs):
            folder = args[0]
            rendered_folders.append(folder)
            return original_generate(*args, **kwargs)

        monkeypatch.setattr(indexer, "_generate_catalog_pages", record_render)
        run_generate_hierarchical_index(sample_vault)
        assert rendered_folders == []

        note_path = sample_vault / "01_Projects" / "TestProject.md"
        note_path.write_text(
            note_path.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8"
        )
        run_generate_hierarchical_index(sample_vault)
        assert "01_Projects" in rendered_folders

    def test_overwrites_existing_indexes(self, sample_vault: Path):
        main_index = sample_vault / "index.md"
        main_index.write_text("Old main content")

        sub_index = sample_vault / "01_Projects" / "_index.md"
        sub_index.parent.mkdir(parents=True, exist_ok=True)
        sub_index.write_text(
            "---\n"
            "type: System Guide\n"
            'title: "01 Projects Sub-Index"\n'
            'description: "Detailed catalog of all notes in 01 Projects"\n'
            "---\n\n"
            "Old sub content",
            encoding="utf-8",
        )

        run_generate_hierarchical_index(sample_vault)

        main_content = main_index.read_text(encoding="utf-8")
        assert "Old main content" not in main_content
        assert "Navigation Map" in main_content

        sub_content = sub_index.read_text(encoding="utf-8")
        assert "Old sub content" not in sub_content


class TestTruncateForCatalog:
    """WTF #4 remediation: long descriptions are stored in full, truncated only
    at catalog (index.md / _index.md) render time."""

    def test_short_description_unchanged(self):
        assert truncate_for_catalog("short") == "short"

    def test_empty_description(self):
        assert truncate_for_catalog("") == ""

    def test_long_description_truncated_with_ellipsis(self):
        from power_framework.core.models import MAX_DESCRIPTION_LENGTH

        long_desc = "A" * (MAX_DESCRIPTION_LENGTH + 50)
        truncated = truncate_for_catalog(long_desc)
        assert len(truncated) == MAX_DESCRIPTION_LENGTH
        assert truncated.endswith("...")
        assert truncated[:-3] == "A" * (MAX_DESCRIPTION_LENGTH - 3)

    def test_custom_max_length(self):
        assert len(truncate_for_catalog("A" * 200, max_length=100)) == 100

    def test_long_description_preserved_in_note_but_truncated_in_catalog(self, sample_vault: Path):
        """Integration: a note with a >150 char description is stored verbatim,
        but the rendered _index.md truncates it to MAX_DESCRIPTION_LENGTH."""
        from power_framework.core.models import MAX_DESCRIPTION_LENGTH

        long_desc = "B" * (MAX_DESCRIPTION_LENGTH + 50)
        note = sample_vault / "01_Projects" / "LongDesc.md"
        note.write_text(
            f"---\ntype: Project\ntitle: Long Desc\n"
            f'description: "{long_desc}"\n'
            f"timestamp: 2026-01-01T00:00:00\n---\n\nBody.\n"
        )
        run_generate_hierarchical_index(sample_vault)
        sub_index = sample_vault / "01_Projects" / "_index.md"
        content = sub_index.read_text(encoding="utf-8")
        # Catalog row is truncated to MAX_DESCRIPTION_LENGTH (with ellipsis).
        assert f"**Description:** {'B' * (MAX_DESCRIPTION_LENGTH - 3)}..." in content
        assert len(long_desc) not in [len(line) for line in content.splitlines()]
