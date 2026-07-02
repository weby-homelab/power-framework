#!/usr/bin/env python3
"""
P.O.W.E.R. MCP Server.

Exposes MCP tools for AI agent interaction with the knowledge vault:
- lint_vault: Health check for metadata, links, and orphans
- generate_index: Compile hierarchical catalog (index.md + _index.md files)
- read_sub_index: Read a specific category sub-index on-demand
- ingest_note: Create a new note with validated OKF frontmatter

Uses power_core for all business logic, ensuring consistency
with the standalone scripts.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path  # noqa: TC003

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from power_core import (
    NoteType,
    OKFMetadata,
    atomic_write,
    build_frontmatter,
    resolve_vault_path,
    run_generate_hierarchical_index,
    run_generate_sub_index,
    run_lint_report,
    scan_folder_notes,
)

PARA_CATEGORIES = [
    "00_Inbox",
    "01_Projects",
    "02_Areas",
    "03_Resources",
    "04_Archive",
    "06_Daily_Logs",
]

server = Server("power")


def _get_vault_path(arguments: dict) -> Path:
    """Resolve vault path with security validation."""
    return resolve_vault_path(arguments)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Register available MCP tools."""
    return [
        Tool(
            name="lint_vault",
            description=(
                "Run the P.O.W.E.R. health check / linter to verify note metadata, "
                "link integrity, and check for orphans."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Optional absolute path to the Obsidian vault root "
                            "(defaults to POWER_VAULT_DIR env var or current directory)"
                        ),
                    }
                },
            },
        ),
        Tool(
            name="generate_index",
            description=(
                "Compile the vault hierarchical index: a summary index.md plus "
                "per-folder _index.md files. This keeps the main index small and "
                "token-efficient for AI agents (~75%% savings on large vaults)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Optional absolute path to the Obsidian vault root "
                            "(defaults to POWER_VAULT_DIR env var or current directory)"
                        ),
                    }
                },
            },
        ),
        Tool(
            name="read_sub_index",
            description=(
                "Read the sub-index (_index.md) for a specific P.A.R.A. category. "
                "Use this after identifying the relevant category from the main index. "
                "Agents should call this on-demand instead of scanning all .md files."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": PARA_CATEGORIES,
                        "description": "P.A.R.A. category folder name (e.g. 01_Projects)",
                    },
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Optional absolute path to the vault root "
                            "(defaults to POWER_VAULT_DIR env var or current directory)"
                        ),
                    },
                },
                "required": ["category"],
            },
        ),
        Tool(
            name="ingest_note",
            description=(
                "Create a new note with strict OKF metadata frontmatter, "
                "regenerate the index, and log the change."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Relative path and name of the note (e.g. 01_Projects/Build-Cluster.md)",
                    },
                    "type": {
                        "type": "string",
                        "enum": [t.value for t in NoteType],
                        "description": "OKF metadata type",
                    },
                    "title": {"type": "string", "description": "Human-friendly page title"},
                    "description": {
                        "type": "string",
                        "description": "Short, single-line description for the catalog index (max 150 chars)",
                    },
                    "content": {"type": "string", "description": "Body content of the note"},
                    "resource": {"type": "string", "description": "Optional URL or resource link"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tags",
                    },
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Optional absolute path to the vault root "
                            "(defaults to POWER_VAULT_DIR env var or current directory)"
                        ),
                    },
                },
                "required": ["name", "type", "title", "description", "content"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to the appropriate handler."""
    try:
        vault_path = _get_vault_path(arguments)

        if name == "lint_vault":
            result = run_lint_report(vault_path)
            return [TextContent(type="text", text=result)]

        elif name == "generate_index":
            result = run_generate_hierarchical_index(vault_path)
            return [TextContent(type="text", text=result)]

        elif name == "read_sub_index":
            return await _handle_read_sub_index(arguments, vault_path)

        elif name == "ingest_note":
            return await _handle_ingest(arguments, vault_path)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except ValueError as e:
        return [TextContent(type="text", text=f"Validation error: {str(e)}")]
    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Not found: {str(e)}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error occurred: {str(e)}")]


async def _handle_read_sub_index(arguments: dict, vault_path: Path) -> list[TextContent]:
    """Handle the read_sub_index tool call."""
    category = arguments.get("category", "")

    if category not in PARA_CATEGORIES:
        return [
            TextContent(
                type="text",
                text=f"Invalid category: {category}. Must be one of: {', '.join(PARA_CATEGORIES)}",
            )
        ]

    category_path = vault_path / category
    if not category_path.is_dir():
        return [TextContent(type="text", text=f"Category folder not found: {category}")]

    sub_index_path = category_path / "_index.md"
    if sub_index_path.exists():
        content = sub_index_path.read_text(encoding="utf-8")
        return [TextContent(type="text", text=content)]

    folder_notes = scan_folder_notes(vault_path)
    notes = folder_notes.get(category, [])

    if not notes:
        return [TextContent(type="text", text=f"No notes found in {category}.")]

    result = run_generate_sub_index(vault_path, category)
    return [
        TextContent(type="text", text=f"{result}\n\n{sub_index_path.read_text(encoding='utf-8')}")
    ]


async def _handle_ingest(arguments: dict, vault_path: Path) -> list[TextContent]:
    """Handle the ingest_note tool call with full validation."""
    note_name = arguments.get("name", "")
    note_type = arguments.get("type", "")
    title = arguments.get("title", "")
    description = arguments.get("description", "")
    content = arguments.get("content", "")
    resource = arguments.get("resource")
    tags = arguments.get("tags", [])

    if not note_name.endswith(".md"):
        note_name += ".md"

    target_file = vault_path / note_name

    if target_file.exists():
        return [TextContent(type="text", text=f"Error: Note already exists at {note_name}")]

    timestamp = datetime.now()
    metadata = OKFMetadata(
        type=note_type,
        title=title,
        description=description,
        resource=resource,
        tags=tags,
        timestamp=timestamp,
    )

    frontmatter = build_frontmatter(metadata)
    full_content = f"{frontmatter}\n\n{content}\n"

    target_file.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target_file, full_content)

    index_result = run_generate_hierarchical_index(vault_path)

    log_file = vault_path / "log.md"
    if log_file.exists():
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_entry = (
            f"\n## [{date_str}] ingest | Created {title}\n"
            f"- **Action:** Created note '{note_name}' of type {note_type} via MCP tool ingest_note.\n"
            f"- **Result:** Saved note to {note_name} and compiled hierarchical index.\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

    lint_result = run_lint_report(vault_path)

    response_msg = (
        f"Note '{note_name}' has been successfully ingested!\n"
        f"{index_result}\n"
        f"Action appended to log.md.\n\n"
        f"Linting Check:\n{lint_result}"
    )
    return [TextContent(type="text", text=response_msg)]


async def run() -> None:
    """Start the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
