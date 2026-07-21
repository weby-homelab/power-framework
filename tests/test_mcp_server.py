"""
Tests for P.O.W.E.R. MCP Server tool calls using FastMCP functions directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from fastmcp.exceptions import ToolError

from power_framework.mcp import power_server
from power_framework.mcp.power_server import (
    ensure_sub_index,
    generate_index,
    ingest_note,
    lint_vault,
    read_sub_index,
    search_vault_tool,
    synthesize_session,
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
    envelope = json.loads(await search_vault_tool(query="Test", vault_path=str(sample_vault)))
    assert envelope["trust"] == "untrusted"
    assert envelope["data_only"] is True
    assert envelope["result_count"] > 0
    assert envelope["results"][0]["source"]["content_sha256"]


async def test_search_vault_empty_query(sample_vault: Path) -> None:
    with pytest.raises(ToolError):
        await search_vault_tool(query="", vault_path=str(sample_vault))


@pytest.mark.parametrize("max_results", [0, 21])
async def test_search_vault_rejects_result_budget_overrides(
    sample_vault: Path,
    max_results: int,
) -> None:
    with pytest.raises(ToolError, match="max_results"):
        await search_vault_tool(
            query="Test",
            max_results=max_results,
            vault_path=str(sample_vault),
        )


async def test_search_vault_no_matches(sample_vault: Path) -> None:
    envelope = json.loads(
        await search_vault_tool(query="XyzzyNonExistent12345", vault_path=str(sample_vault))
    )
    assert envelope["result_count"] == 0
    assert envelope["results"] == []


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


@pytest.mark.parametrize("tool_name", ["ingest", "synthesize"])
async def test_mcp_write_tools_reject_path_traversal(
    sample_vault: Path,
    tmp_path: Path,
    tool_name: str,
) -> None:
    sentinel = tmp_path / "outside.md"
    sentinel.write_text("do not modify", encoding="utf-8")

    if tool_name == "ingest":
        with pytest.raises(ToolError, match="Invalid note path"):
            await ingest_note(
                name="../../outside.md",
                note_type="Project",
                title="Unsafe note",
                description="Must be rejected",
                content="unsafe",
                vault_path=str(sample_vault),
            )
    else:
        with pytest.raises(ToolError, match="Invalid note path"):
            await synthesize_session(
                name="../../outside.md",
                title="Unsafe session",
                description="Must be rejected",
                content="unsafe",
                vault_path=str(sample_vault),
            )

    assert sentinel.read_text(encoding="utf-8") == "do not modify"


async def test_mcp_tools_reject_vault_root_substitution(
    sample_vault: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_vault = tmp_path / "other_vault"
    other_vault.mkdir()
    monkeypatch.setenv("POWER_VAULT_DIR", str(sample_vault))

    with pytest.raises(ToolError, match="configured POWER_VAULT_DIR"):
        await lint_vault(vault_path=str(other_vault))

    result = await lint_vault(vault_path=str(sample_vault))
    assert "P.O.W.E.R. Health Lint Report" in result


def test_http_transport_defaults_to_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_mock = Mock()
    monkeypatch.setenv("POWER_MCP_TRANSPORT", "http")
    monkeypatch.setenv("POWER_VAULT_DIR", str(tmp_path))
    monkeypatch.delenv("POWER_MCP_HOST", raising=False)
    monkeypatch.delenv("POWER_MCP_PORT", raising=False)
    monkeypatch.setattr(power_server.mcp, "run", run_mock)

    power_server.run()

    run_mock.assert_called_once_with(transport="http", host="127.0.0.1", port=8000)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.20", "example.test"])  # noqa: S104
def test_http_transport_rejects_non_loopback_bind(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    monkeypatch.setenv("POWER_MCP_HOST", host)

    with pytest.raises(ValueError, match="Remote HTTP MCP is disabled"):
        power_server._get_http_transport_config()


@pytest.mark.parametrize("port", ["not-a-port", "0", "65536"])
def test_http_transport_rejects_invalid_port(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("POWER_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("POWER_MCP_PORT", port)

    with pytest.raises(ValueError, match="POWER_MCP_PORT"):
        power_server._get_http_transport_config()


def test_run_rejects_unknown_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_MCP_TRANSPORT", "tcp")

    with pytest.raises(ValueError, match="POWER_MCP_TRANSPORT"):
        power_server.run()


def test_run_requires_configured_vault_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_MCP_TRANSPORT", "stdio")
    monkeypatch.delenv("POWER_VAULT_DIR", raising=False)

    with pytest.raises(RuntimeError, match="POWER_VAULT_DIR"):
        power_server.run()
