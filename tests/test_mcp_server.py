"""
Tests for P.O.W.E.R. MCP Server tool calls using FastMCP functions directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_framework.mcp.power_server import (
    generate_index,
    ingest_note,
    lint_vault,
    read_sub_index,
    search_vault_tool,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_read_sub_index_existing_category(sample_vault: Path) -> None:
    result = read_sub_index(category="01_Projects", vault_path=str(sample_vault))
    assert "Test Project" in result


def test_read_sub_index_invalid_category(sample_vault: Path) -> None:
    result = read_sub_index(category="99_Invalid", vault_path=str(sample_vault))
    assert "Invalid category" in result


def test_read_sub_index_nonexistent_folder(tmp_path: Path) -> None:
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    result = read_sub_index(category="01_Projects", vault_path=str(vault))
    assert "Category folder not found" in result


def test_search_vault_finds_notes(sample_vault: Path) -> None:
    result = search_vault_tool(query="Test", vault_path=str(sample_vault))
    assert "Test" in result
    assert "Found" in result


def test_search_vault_empty_query(sample_vault: Path) -> None:
    result = search_vault_tool(query="", vault_path=str(sample_vault))
    assert "empty" in result.lower()


def test_search_vault_no_matches(sample_vault: Path) -> None:
    result = search_vault_tool(query="XyzzyNonExistent12345", vault_path=str(sample_vault))
    assert "No results" in result


def test_lint_vault_on_sample(sample_vault: Path) -> None:
    result = lint_vault(vault_path=str(sample_vault))
    assert "P.O.W.E.R. Health Lint Report" in result


def test_generate_index_tool(sample_vault: Path) -> None:
    result = generate_index(vault_path=str(sample_vault))
    assert "hierarchical index" in result
    assert (sample_vault / "index.md").exists()


def test_ingest_note_tool(sample_vault: Path) -> None:
    # Prepare a log.md since ingest_note appends to it if it exists
    log_file = sample_vault / "log.md"
    log_file.write_text("Change Log\n", encoding="utf-8")

    result = ingest_note(
        name="01_Projects/NewMcpNote.md",
        note_type="Project",
        title="New MCP Note",
        description="Created via MCP server tool",
        content="Hello world",
        vault_path=str(sample_vault),
    )
    assert "successfully ingested" in result

    note_path = sample_vault / "01_Projects" / "NewMcpNote.md"
    assert note_path.exists()

    content = note_path.read_text(encoding="utf-8")
    assert 'title: "New MCP Note"' in content

    # Test error when already exists
    result_fail = ingest_note(
        name="01_Projects/NewMcpNote.md",
        note_type="Project",
        title="New MCP Note",
        description="Created via MCP server tool",
        content="Hello world",
        vault_path=str(sample_vault),
    )
    assert "Error: Note already exists" in result_fail

