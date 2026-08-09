"""The read-only runtime capability contract shared by agents and tooling."""

from __future__ import annotations

import ast
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

CAPABILITIES_SCHEMA_VERSION = 1


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _cli_commands() -> list[str]:
    """Read top-level argparse registrations without importing the CLI."""
    source = ast.parse(_read_source(_package_root() / "core" / "cli.py"))
    commands: list[str] = []
    for node in ast.walk(source):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "add_parser"
            and isinstance(function.value, ast.Name)
            and function.value.id == "subparsers"
        ):
            continue
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            commands.append(node.args[0].value)
    return commands


def _literal_dict(node: ast.AST) -> dict[str, Any]:
    """Read a literal decorator mapping without importing the MCP server."""
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return {}
    return value if isinstance(value, dict) else {}


def _mcp_tool_contracts() -> list[dict[str, Any]]:
    """Read FastMCP tool contracts without importing FastMCP or the server."""
    source = ast.parse(_read_source(_package_root() / "mcp" / "power_server.py"))
    contracts: list[dict[str, Any]] = []
    for node in ast.walk(source):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute):
                tool_call = decorator
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                tool_call = decorator.func
            else:
                continue
            if not (
                tool_call.attr == "tool"
                and isinstance(tool_call.value, ast.Name)
                and tool_call.value.id == "mcp"
            ):
                continue
            annotations: dict[str, Any] = {}
            risk: dict[str, Any] = {}
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if keyword.arg == "annotations":
                        annotations = _literal_dict(keyword.value)
                    elif keyword.arg == "meta":
                        meta = _literal_dict(keyword.value)
                        risk_value = meta.get("power.risk")
                        if isinstance(risk_value, dict):
                            risk = risk_value
            contracts.append(
                {
                    "name": node.name,
                    "annotations": annotations,
                    "risk": risk,
                }
            )
            break
    return contracts


def _mcp_tools() -> list[str]:
    """Return tool names while preserving the public manifest shape."""
    return [contract["name"] for contract in _mcp_tool_contracts()]


def _environment_variables() -> list[str]:
    """Collect environment names read by the package's executable code."""
    package_root = _package_root()
    names: set[str] = set()
    for path in sorted(package_root.rglob("*.py")):
        try:
            source = ast.parse(_read_source(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(source):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not (
                isinstance(function, ast.Attribute)
                and function.attr == "getenv"
                and isinstance(function.value, ast.Name)
                and function.value.id == "os"
            ):
                continue
            if node.args and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str) and (
                    value.startswith(("POWER_", "HF_", "FASTEMBED_", "OLLAMA_"))
                    or value == "XDG_CACHE_HOME"
                ):
                    names.add(value)
    return sorted(names)


def _version() -> str:
    try:
        return distribution_version("power-framework")
    except PackageNotFoundError:
        return "unknown"


def manifest() -> dict[str, Any]:
    """Return the deterministic, read-only capability manifest.

    The function intentionally performs no model loading, network access,
    vault identity creation, cache directory creation, or database access.
    """
    from .embeddings import BGE_M3_ONNX_REPO, BGE_M3_ONNX_REVISION, EMBED_PROVIDER
    from .reranker import (
        BGE_RERANKER_ONNX_REPO,
        BGE_RERANKER_ONNX_REVISION,
        DEFAULT_RERANKER_MODEL,
    )
    from .searcher import (
        CANONICAL_SEARCH_MODES,
        DEFAULT_SEARCH_MODE,
        SEARCH_MODE_ALIASES,
        SEARCH_MODE_REGISTRY,
    )
    from .utils import get_cache_dir

    cache_root = get_cache_dir(create=False)
    registry = [
        {
            "mode": mode,
            "candidate_sources": list(spec.candidate_sources),
            "fusion": spec.fusion,
            "reranker": spec.reranker,
            "requires_dense_index": spec.requires_dense_index,
        }
        for mode, spec in sorted(SEARCH_MODE_REGISTRY.items())
    ]
    return {
        "schema_version": CAPABILITIES_SCHEMA_VERSION,
        "source": "power_framework.core.capabilities",
        "version": _version(),
        "interfaces": {
            "cli_commands": _cli_commands(),
            "mcp_tools": _mcp_tools(),
            "mcp_tool_contracts": _mcp_tool_contracts(),
        },
        "search": {
            "default_mode": DEFAULT_SEARCH_MODE,
            "canonical_modes": sorted(CANONICAL_SEARCH_MODES),
            "aliases": dict(sorted(SEARCH_MODE_ALIASES.items())),
            "registry": registry,
        },
        "models": {
            "embedder": EMBED_PROVIDER,
            "embedding_model": f"{BGE_M3_ONNX_REPO}@{BGE_M3_ONNX_REVISION}",
            "reranker": DEFAULT_RERANKER_MODEL,
            "reranker_model": f"{BGE_RERANKER_ONNX_REPO}@{BGE_RERANKER_ONNX_REVISION}",
        },
        "storage": {
            "cache_root": str(cache_root),
            "database_path_template": str(cache_root / "vaults/<vault-uuid>/search.db"),
            "database_override_env": "POWER_SEARCH_DB",
        },
        "environment": {"variables": _environment_variables()},
        "read_only": True,
        "network_access": False,
    }
