"""Static guardrails for the MCP adapter/application boundary."""

from __future__ import annotations

import ast
from pathlib import Path

MCP_SOURCE = Path(__file__).parents[1] / "src" / "power_framework" / "mcp" / "power_server.py"
FORBIDDEN_LOW_LEVEL_NAMES = {
    "archive_stale_notes",
    "commit_note_change",
    "heal_vault",
    "run_generate_hierarchical_index",
    "run_generate_sub_index",
    "run_vault_mutation",
    "sync_vault_atomically",
    "synthesize_session_ingest",
}
MUTATING_TOOLS = {
    "generate_index": "generate_index",
    "sync_vault": "sync_vault",
    "ensure_sub_index": "ensure_sub_index",
    "ingest_note": "ingest_note",
    "synthesize_session": "synthesize_session",
    "archive_notes": "archive_notes",
    "heal_frontmatter_tool": "heal_frontmatter",
}


def test_mcp_mutations_do_not_import_or_call_core_implementation_details() -> None:
    """Mutation orchestration belongs to ApplicationService, never the MCP adapter."""
    source = MCP_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MCP_SOURCE))

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not imported & FORBIDDEN_LOW_LEVEL_NAMES
    assert not called & FORBIDDEN_LOW_LEVEL_NAMES

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    for tool_name, method_name in MUTATING_TOOLS.items():
        calls = [
            node
            for node in ast.walk(functions[tool_name])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method_name
        ]
        assert calls, f"{tool_name} must delegate to ApplicationService.{method_name}"
