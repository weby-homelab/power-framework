"""Golden configuration and workflow tests for documented MCP clients."""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from power_framework.core.capabilities import manifest
from tests.mcp_test_client import stdio_session

REPO_ROOT = Path(__file__).resolve().parents[1]
ONBOARDING_DOC = REPO_ROOT / "docs" / "mcp-client-onboarding.md"
ONBOARDING_DOC_UA = REPO_ROOT / "docs" / "mcp-client-onboarding.ua.md"
_CONFIG_PATTERN = re.compile(
    r"<!--\s*power-client-config:(?P<name>[a-z-]+)\s*-->"
    r"(?:(?!<!--).)*?"
    r"```(?P<language>json|toml)\s*\n(?P<body>.*?)```",
    re.DOTALL,
)
_EXPECTED_CLIENTS = {"claude-desktop", "gemini-cli", "codex", "opencode"}


def _documented_configs(document_path: Path = ONBOARDING_DOC) -> dict[str, dict[str, Any]]:
    """Parse the four marked examples instead of duplicating their contents."""
    document = document_path.read_text(encoding="utf-8")
    matches = _CONFIG_PATTERN.findall(document)
    assert {name for name, _language, _body in matches} == _EXPECTED_CLIENTS
    configs: dict[str, dict[str, Any]] = {}
    for name, language, body in matches:
        parsed = json.loads(body) if language == "json" else tomllib.loads(body)
        assert isinstance(parsed, dict)
        configs[name] = parsed
    return configs


def _stdio_parts(name: str, config: dict[str, Any]) -> tuple[str, list[str], dict[str, str]]:
    """Normalize each host's native configuration to a stdio launch tuple."""
    if name in {"claude-desktop", "gemini-cli"}:
        server = config["mcpServers"]["power"]
        assert isinstance(server, dict)
        return server["command"], server["args"], server["env"]
    if name == "codex":
        server = config["mcp_servers"]["power"]
        assert isinstance(server, dict)
        return server["command"], server["args"], server["env"]
    server = config["mcp"]["power"]
    assert isinstance(server, dict)
    assert server["type"] == "local"
    return server["command"][0], server["command"][1:], server["environment"]


def test_documented_client_shapes_are_native_and_consistent() -> None:
    configs = _documented_configs()

    for name, config in configs.items():
        command, args, environment = _stdio_parts(name, config)
        assert command == "/absolute/path/to/power-mcp"
        assert args == []
        assert environment == {"POWER_VAULT_DIR": "/absolute/path/to/vault"}
        assert "POWER_VAULT_PATH" not in json.dumps(config)


def test_ukrainian_onboarding_keeps_the_same_client_shapes() -> None:
    assert _documented_configs(ONBOARDING_DOC_UA) == _documented_configs()


@pytest.mark.parametrize("client_name", sorted(_EXPECTED_CLIENTS))
async def test_each_documented_shape_reaches_golden_stdio_workflow(
    client_name: str, sample_vault: Path
) -> None:
    """Exercise discovery, read-only context, and proposal-without-write per shape."""
    command, _args, _documented_environment = _stdio_parts(
        client_name, _documented_configs()[client_name]
    )
    assert command == "/absolute/path/to/power-mcp"

    process_environment = os.environ.copy()
    process_environment.update(
        {
            "POWER_VAULT_DIR": str(sample_vault),
            "POWER_MCP_TRANSPORT": "stdio",
        }
    )
    config = {
        "mcpServers": {
            "power": {
                "command": sys.executable,
                # The test process uses the compatibility module entrypoint so
                # it remains runnable from the source checkout; docs use the
                # installed public power-mcp launcher above.
                "args": ["-m", "power_framework.mcp"],
                "env": process_environment,
            }
        }
    }

    async with stdio_session(config, mode="legacy") as client:
        tools = (await client.list_tools()).tools
        assert [tool.name for tool in tools] == manifest()["interfaces"]["mcp_tools"]
        assert (await client.list_resources()).resources == []
        assert (await client.list_resource_templates()).resource_templates == []
        assert (await client.list_prompts()).prompts == []
        assert all(tool.output_schema and tool.annotations for tool in tools)

        await client.call_tool("get_memory_context", {"query": "golden onboarding"})
        proposal_result = await client.call_tool(
            "propose_memory_change",
            {
                "path": "01_Projects/golden-onboarding.md",
                "content": (
                    "---\n"
                    "type: Project\n"
                    'title: "Golden onboarding"\n'
                    'description: "Durable proposal only"\n'
                    "timestamp: 2026-08-10T00:00:00Z\n"
                    "---\n\nproposal only\n"
                ),
            },
        )
        assert proposal_result

    assert not (sample_vault / "01_Projects" / "golden-onboarding.md").exists()
    assert not (sample_vault / ".power" / "memory-history.jsonl").exists()
    assert list((sample_vault / ".power" / "proposals").glob("*.json"))
