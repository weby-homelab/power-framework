"""
Tests for P.O.W.E.R. MCP Server tool calls using FastMCP functions directly.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from power_framework.core.capabilities import manifest
from power_framework.core.parser import validate_metadata
from power_framework.mcp import power_server
from power_framework.mcp.power_server import (
    apply_memory_change,
    ensure_sub_index,
    generate_index,
    ingest_note,
    lint_vault,
    propose_memory_change,
    read_memory_history,
    read_sub_index,
    search_vault_tool,
    sync_vault,
    synthesize_session,
    validate_memory_state,
)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _mcp_process_env(vault_path: Path, transport: str, port: int | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "POWER_VAULT_DIR": str(vault_path),
            "POWER_MCP_TRANSPORT": transport,
        }
    )
    if port is not None:
        env["POWER_MCP_HOST"] = "127.0.0.1"
        env["POWER_MCP_PORT"] = str(port)
    return env


async def _assert_wire_contract(client: Client[object]) -> None:
    tools = await client.list_tools()
    resources = await client.list_resources()
    resource_templates = await client.list_resource_templates()
    prompts = await client.list_prompts()

    expected_names = manifest()["interfaces"]["mcp_tools"]
    assert [tool.name for tool in tools] == expected_names
    assert resources == []
    assert resource_templates == []
    assert prompts == []
    assert all(tool.outputSchema for tool in tools)
    assert all(tool.annotations for tool in tools)
    assert all(tool.meta and tool.meta.get("power.risk") for tool in tools)


async def _stop_mcp_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
    if process.stderr is not None:
        await process.stderr.read()


async def _wait_for_http_health(process: asyncio.subprocess.Process, url: str) -> None:
    deadline = asyncio.get_running_loop().time() + 15
    last_error = "server did not become ready"
    async with httpx.AsyncClient(timeout=1) as http_client:
        while asyncio.get_running_loop().time() < deadline:
            if process.returncode is not None:
                stderr = await process.stderr.read() if process.stderr is not None else b""
                raise AssertionError(
                    f"MCP HTTP process exited with {process.returncode}: {stderr.decode(errors='replace')}"
                )
            try:
                response = await http_client.get(url)
                if response.status_code == 200 and response.json() == {"status": "ok"}:
                    return
                last_error = f"health returned {response.status_code}: {response.text}"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
            await asyncio.sleep(0.1)
    raise AssertionError(last_error)


async def test_mcp_tools_publish_standard_and_power_risk_annotations() -> None:
    tools = await power_server.mcp.list_tools()

    assert len(tools) == 18
    by_name = {tool.name: tool for tool in tools}
    assert set(by_name) == set(manifest()["interfaces"]["mcp_tools"])

    archive = by_name["archive_notes"]
    assert archive.annotations is not None
    assert archive.annotations.readOnlyHint is False
    assert archive.annotations.destructiveHint is True
    assert archive.annotations.idempotentHint is False
    assert archive.annotations.openWorldHint is False
    assert archive.meta == {
        "power.risk": {"local_only": True, "egress": "none", "approval": "explicit"}
    }

    search = by_name["search_vault_tool"]
    assert search.annotations is not None
    assert search.annotations.readOnlyHint is True
    assert search.meta["power.risk"]["egress"] == "model_download"

    proposal = by_name["propose_memory_change"]
    assert proposal.annotations is not None
    assert proposal.annotations.readOnlyHint is False
    assert proposal.annotations.destructiveHint is False
    assert proposal.annotations.idempotentHint is True
    assert proposal.meta == {
        "power.risk": {"local_only": True, "egress": "none", "approval": "caller"}
    }


async def test_mcp_wire_discovery_preserves_tool_contract_and_empty_collections() -> None:
    async with Client(power_server.mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        resource_templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
        tools_again = await client.list_tools()

    expected_names = manifest()["interfaces"]["mcp_tools"]
    assert [tool.name for tool in tools] == expected_names
    assert [tool.name for tool in tools_again] == expected_names
    assert [tool.name for tool in tools_again] == [tool.name for tool in tools]
    assert resources == []
    assert resource_templates == []
    assert prompts == []
    assert all(tool.outputSchema for tool in tools)
    assert all(tool.annotations for tool in tools)
    assert all(tool.meta and tool.meta.get("power.risk") for tool in tools)


async def test_mcp_stdio_process_preserves_wire_contract(sample_vault: Path) -> None:
    config = {
        "mcpServers": {
            "power": {
                "command": sys.executable,
                "args": ["-m", "power_framework.mcp"],
                "env": _mcp_process_env(sample_vault, "stdio"),
            }
        }
    }

    async with Client(config) as client:
        await _assert_wire_contract(client)


async def test_mcp_http_process_reports_health_and_preserves_wire_contract(
    sample_vault: Path,
) -> None:
    port = _free_tcp_port()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "power_framework.mcp",
        cwd=str(Path(__file__).parents[1]),
        env=_mcp_process_env(sample_vault, "http", port),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        await _wait_for_http_health(process, f"{base_url}/health")
        async with Client(f"{base_url}/mcp") as client:
            await _assert_wire_contract(client)
    finally:
        await _stop_mcp_process(process)


async def test_http_health_route_reports_vault_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POWER_VAULT_DIR", str(tmp_path))

    transport = httpx.ASGITransport(app=power_server.mcp.http_app(transport="http"))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_http_health_route_fails_closed_without_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POWER_VAULT_DIR", str(tmp_path / "missing-vault"))

    transport = httpx.ASGITransport(app=power_server.mcp.http_app(transport="http"))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


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
    envelope = json.loads(
        await search_vault_tool(query="Test", search_mode="fts", vault_path=str(sample_vault))
    )
    assert envelope["trust"] == "untrusted"
    assert envelope["data_only"] is True
    assert envelope["result_count"] > 0
    assert envelope["temporal_view"] == "current"
    assert envelope["as_of"]
    assert envelope["results"][0]["source"]["content_sha256"]


async def test_transactional_memory_tools_share_approval_and_history(sample_vault: Path) -> None:
    marker = "mcp-closed-mutation-marker"
    proposal = json.loads(
        await propose_memory_change(
            path="01_Projects/FromTransaction.md",
            content='---\ntype: Project\ntitle: "From transaction"\ndescription: "MCP transaction"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n'
            + marker
            + "\n",
            vault_path=str(sample_vault),
        )
    )
    with pytest.raises(ToolError, match="approved"):
        await apply_memory_change(proposal=proposal, approved=False, vault_path=str(sample_vault))
    receipt = json.loads(
        await apply_memory_change(proposal=proposal, approved=True, vault_path=str(sample_vault))
    )
    assert receipt["search_mode"] == "fts"
    search_envelope = json.loads(
        await search_vault_tool(query=marker, search_mode="fts", vault_path=str(sample_vault))
    )
    assert search_envelope["results"][0]["source"]["path"] == ("01_Projects/FromTransaction.md")
    assert json.loads(await read_memory_history(vault_path=str(sample_vault)))[0]["path"]
    assert isinstance(await validate_memory_state(vault_path=str(sample_vault)), bool)


async def test_search_vault_empty_query(sample_vault: Path) -> None:
    with pytest.raises(ToolError):
        await search_vault_tool(query="", vault_path=str(sample_vault))


async def test_search_vault_uses_canonical_default_mode(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_search(_path: Path, _query: str, **kwargs: object):
        captured["mode"] = str(kwargs["mode"])
        return []

    monkeypatch.setattr(power_server, "search_vault", fake_search)

    envelope = json.loads(await search_vault_tool(query="Test", vault_path=str(sample_vault)))

    assert captured["mode"] == "semantic"
    assert envelope["mode"] == "semantic"


async def test_search_vault_keeps_explicit_fts_mode_compatible(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_search(_path: Path, _query: str, **kwargs: object):
        captured["mode"] = str(kwargs["mode"])
        return []

    monkeypatch.setattr(power_server, "search_vault", fake_search)

    envelope = json.loads(
        await search_vault_tool(query="Test", search_mode="fts", vault_path=str(sample_vault))
    )

    assert captured["mode"] == "fts"
    assert envelope["mode"] == "fts"


async def test_search_vault_uses_shared_temporal_contract(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_search(_path: Path, _query: str, **kwargs: object):
        captured["temporal_view"] = str(kwargs["temporal_view"])
        captured["as_of"] = str(kwargs["as_of"])
        return []

    monkeypatch.setattr(power_server, "search_vault", fake_search)
    envelope = json.loads(
        await search_vault_tool(
            query="Test",
            search_mode="fts",
            temporal_view="historical",
            as_of="2026-07-10",
            vault_path=str(sample_vault),
        )
    )

    assert captured == {"temporal_view": "historical", "as_of": "2026-07-10"}
    assert envelope["temporal_view"] == "historical"
    assert envelope["as_of"] == "2026-07-10"


async def test_search_vault_rejects_unknown_mode(sample_vault: Path) -> None:
    with pytest.raises(ToolError, match="Unsupported search mode"):
        await search_vault_tool(
            query="Test",
            search_mode="silent-fallback",
            vault_path=str(sample_vault),
        )


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
        await search_vault_tool(
            query="XyzzyNonExistent12345",
            search_mode="fts",
            vault_path=str(sample_vault),
        )
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
    metadata = validate_metadata(content)
    assert metadata is not None
    assert metadata.okf_version == "0.2"
    assert metadata.memory is not None
    assert metadata.memory.kind == "semantic"
    assert metadata.memory.sources == ["power://mcp/ingest_note"]
    assert metadata.memory.evidence[0].startswith("sha256:")

    with pytest.raises(ToolError):
        await ingest_note(
            name="01_Projects/NewMcpNote.md",
            note_type="Project",
            title="New MCP Note",
            description="Created via MCP server tool",
            content="Hello world",
            vault_path=str(sample_vault),
        )


async def test_mcp_write_search_loop_survives_a_fresh_process(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP-only ingest is immediately visible after the server restarts."""
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    marker = "mcp-fresh-process-acceptance-7f3c"

    await sync_vault(fts_only=True, vault_path=str(sample_vault))
    await ingest_note(
        name="03_Resources/fresh-process-probe",
        note_type="Resource",
        title="Fresh process probe",
        description=f"A restart acceptance note carrying {marker}",
        content=f"# Probe\n\nThe body contains {marker}.\n",
        vault_path=str(sample_vault),
    )

    before = json.loads(
        await search_vault_tool(query=marker, search_mode="fts", vault_path=str(sample_vault))
    )
    assert before["result_count"] == 1

    source_root = Path(__file__).resolve().parents[1] / "src"
    script = (
        "import json, sys\n"
        "from power_framework.core.searcher import search_vault\n"
        "results = search_vault(sys.argv[1], sys.argv[2], mode='fts')\n"
        "print(json.dumps([result.rel_path for result in results]))\n"
    )
    child_env = os.environ.copy()
    child_env.pop("POWER_SEARCH_DB", None)
    child_env["PYTHONPATH"] = os.pathsep.join(
        [str(source_root), child_env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    completed = subprocess.run(  # noqa: S603 - executable and script are fixed by this test.
        [sys.executable, "-c", script, str(sample_vault), marker],
        capture_output=True,
        check=False,
        env=child_env,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "03_Resources/fresh-process-probe.md" in json.loads(completed.stdout)

    with pytest.raises(ToolError, match="Dense index"):
        await search_vault_tool(
            query=marker,
            search_mode="semantic",
            vault_path=str(sample_vault),
        )


async def test_sync_vault_fails_closed_and_can_explicitly_allow_partial(
    sample_vault: Path,
) -> None:
    """Coverage omissions are an explicit MCP error, never an implied success."""
    await sync_vault(fts_only=True, vault_path=str(sample_vault))
    invalid = sample_vault / "03_Resources" / "broken-sync-note.md"
    invalid.write_text("# no OKF frontmatter\n", encoding="utf-8")

    with pytest.raises(ToolError, match=r"failed closed.*broken-sync-note\.md"):
        await sync_vault(fts_only=True, vault_path=str(sample_vault))

    report = await sync_vault(
        fts_only=True,
        allow_partial=True,
        vault_path=str(sample_vault),
    )
    assert "Notes excluded (invalid metadata): 1" in report
    assert "- 03_Resources/broken-sync-note.md: invalid_metadata" in report
    assert "not searchable" in report


async def test_sync_vault_dense_loss_requires_explicit_acceptance(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP must expose the shared dense-loss refusal and explicit opt-in."""
    from power_framework.core import generation_index

    monkeypatch.setattr(power_server._index_limiter, "is_allowed", lambda _: True)
    monkeypatch.setattr(generation_index, "active_dense_chunk_count", lambda _: 3)
    with pytest.raises(ToolError, match=r"Refusing --fts-only.*3 chunks"):
        await sync_vault(fts_only=True, vault_path=str(sample_vault))

    report = await sync_vault(fts_only=True, accept_dense_loss=True, vault_path=str(sample_vault))
    assert "Mode: FTS only" in report


async def test_synthesize_session_serializes_write_and_stores_candidate_triplets(
    sample_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "power-search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db_path))

    result = await synthesize_session(
        name="06_Daily_Logs/McpSynthesis.md",
        title="MCP synthesis",
        description="A synthesis created through the MCP write queue.",
        content="POWER is a knowledge management framework.",
        vault_path=str(sample_vault),
    )

    assert "synthesized and ingested" in result
    assert (sample_vault / "06_Daily_Logs" / "McpSynthesis.md").exists()
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT source_path, relation, status FROM relation_candidates WHERE source_path = ?",
            ("06_Daily_Logs/McpSynthesis.md",),
        ).fetchall()
    assert ("06_Daily_Logs/McpSynthesis.md", "is_a", "candidate") in rows


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
