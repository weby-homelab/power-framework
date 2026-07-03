"""
Tests for P.O.W.E.R. MCP Server tool calls using FastMCP functions directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_framework.mcp.power_server import (
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
