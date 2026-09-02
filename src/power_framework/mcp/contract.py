"""Content-free metadata for the native POWER MCP stdio contract."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from typing import Any

from power_framework.core.integrations import packaged_skill_tree

MCP_PREFERRED_PROTOCOL = "2026-07-28"
MCP_TRANSPORT = "stdio"
MCP_LEGACY_COMPATIBILITY = True
MCP_VAULT_ENVIRONMENT = "POWER_VAULT_DIR"


def _json_value(value: Any) -> Any:
    """Return a JSON-compatible SDK value without retaining model objects."""
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, mode="json", exclude_none=True)
    return value


def canonical_tool_catalog(tools: list[Any]) -> list[dict[str, Any]]:
    """Return the stable, content-free representation of live MCP tools."""
    catalog: list[dict[str, Any]] = []
    for tool in tools:
        meta = _json_value(getattr(tool, "meta", None))
        risk = meta.get("power.risk") if isinstance(meta, dict) else None
        catalog.append(
            {
                "name": getattr(tool, "name", None),
                "input_schema": _json_value(getattr(tool, "input_schema", None)),
                "output_schema": _json_value(getattr(tool, "output_schema", None)),
                "annotations": _json_value(getattr(tool, "annotations", None)),
                "power_risk": risk,
            }
        )
    return sorted(catalog, key=lambda entry: str(entry["name"]))


def tool_catalog_fingerprint(tools: list[Any]) -> dict[str, Any]:
    """Hash the full live catalog using canonical JSON without host-specific data."""
    catalog = canonical_tool_catalog(tools)
    encoded = json.dumps(
        catalog,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "tool_count": len(catalog),
        "tool_catalog_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def mcp_discovery_contract(tools: list[Any]) -> dict[str, Any]:
    """Build read-only MCP facts suitable for ``get_server_info``."""
    try:
        sdk_version = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None
    return {
        "sdk_version": sdk_version,
        "transport": MCP_TRANSPORT,
        "preferred_protocol": MCP_PREFERRED_PROTOCOL,
        "legacy_compatibility": MCP_LEGACY_COMPATIBILITY,
        "configured_vault_boundary": MCP_VAULT_ENVIRONMENT,
        "read_only_by_default": True,
        "network_access_by_default": False,
        **tool_catalog_fingerprint(tools),
    }


def agent_integration_descriptor(tools: list[Any]) -> dict[str, Any]:
    """Describe the portable MCP and Agent Skills contract without private paths."""
    catalog = tool_catalog_fingerprint(tools)
    skill = packaged_skill_tree()
    return {
        "schema": "power.agent-integration.v1",
        "runtime": {
            "entry_point": "power-mcp",
            "transport": MCP_TRANSPORT,
        },
        "environment": {"required": [MCP_VAULT_ENVIRONMENT]},
        "mcp": {
            "preferred_protocol": MCP_PREFERRED_PROTOCOL,
            "legacy_compatibility": MCP_LEGACY_COMPATIBILITY,
            "tool_count": catalog["tool_count"],
            "catalog_sha256": catalog["tool_catalog_sha256"],
        },
        "skill": {
            "name": "power",
            "canonical_tree_sha256": skill.sha256,
        },
    }
