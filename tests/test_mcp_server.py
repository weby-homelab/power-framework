"""
Tests for P.O.W.E.R. MCP Server tool calls using FastMCP functions directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp.exceptions import ToolError

from power_framework.mcp.power_server import (
    ensure_sub_index,
    generate_index,
    ingest_note,
    lint_vault,
    read_sub_index,
    search_vault_tool,
)

if TYPE_CHECKING:
    from pathlib import Path


async def test_read_sub_index_existing_category(sample_vault: Path) -> None:
    await ensure_sub_index(category="01_Projects", vault_path=str(sample_vault))
    result = await read_sub_index(category="01_Projects", vault_path=str(sample_vault))
    assert "Test Project" in result


async def test_read_sub_index_invalid_category(sample_vault: Path) -> None:
    with pytest.raises(ToolError):
        await read_sub_index(category="99_Invalid", vault_path=str(sample_vault))


async def test_read_sub_index_nonexistent_folder(tmp_path: Path) -> None:
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    with pytest.raises(ToolError):
        await read_sub_index(category="01_Projects", vault_path=str(vault))


async def test_search_vault_finds_notes(sample_vault: Path) -> None:
    result = await search_vault_tool(query="Test", vault_path=str(sample_vault))
    assert "Test" in result
    assert "Found" in result


async def test_search_vault_empty_query(sample_vault: Path) -> None:
    with pytest.raises(ToolError):
        await search_vault_tool(query="", vault_path=str(sample_vault))


async def test_search_vault_no_matches(sample_vault: Path) -> None:
    result = await search_vault_tool(query="XyzzyNonExistent12345", vault_path=str(sample_vault))
    assert "No results" in result


async def test_lint_vault_on_sample(sample_vault: Path) -> None:
    result = await lint_vault(vault_path=str(sample_vault))
    assert "P.O.W.E.R. Health Lint Report" in result


async def test_generate_index_tool(sample_vault: Path) -> None:
    result = await generate_index(vault_path=str(sample_vault))
    assert "hierarchical index" in result
    assert (sample_vault / "index.md").exists()


async def test_ingest_note_tool(sample_vault: Path) -> None:
    log_file = sample_vault / "log.md"
    log_file.write_text("Change Log\n", encoding="utf-8")

    result = await ingest_note(
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

    with pytest.raises(ToolError):
        await ingest_note(
            name="01_Projects/NewMcpNote.md",
            note_type="Project",
            title="New MCP Note",
            description="Created via MCP server tool",
            content="Hello world",
            vault_path=str(sample_vault),
        )
