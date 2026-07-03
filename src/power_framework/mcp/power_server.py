#!/usr/bin/env python3
"""
P.O.W.E.R. MCP Server.

Exposes MCP tools for AI agent interaction with the knowledge vault:
- lint_vault: Health check for metadata, links, and orphans
- generate_index: Compile hierarchical catalog (index.md + _index.md files)
- read_sub_index: Read a specific category sub-index on-demand
- ingest_note: Create a new note with validated OKF frontmatter
- search_vault: Full-text search across vault notes

Uses power_core for all business logic, ensuring consistency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from pathlib import Path

from power_framework.core import (
    PARA_FOLDERS,
    NoteType,
    OKFMetadata,
    atomic_write,
    build_frontmatter,
    format_search_results,
    resolve_vault_path,
    run_generate_hierarchical_index,
    run_generate_sub_index,
    run_lint_report,
    scan_folder_notes,
    search_vault,
)

mcp = FastMCP("power")


def _get_vault_path(vault_path: str | None = None) -> Path:
    """Resolve vault path with security validation."""
    args = {"vault_path": vault_path} if vault_path else {}
    return resolve_vault_path(args)


@mcp.tool()
def lint_vault(vault_path: str | None = None) -> str:
    """Run the P.O.W.E.R. health check / linter to verify note metadata, link integrity, and check for orphans."""
    path = _get_vault_path(vault_path)
    return run_lint_report(path)


@mcp.tool()
def generate_index(vault_path: str | None = None) -> str:
    """Compile the vault hierarchical index: a summary index.md plus per-folder _index.md files."""
    path = _get_vault_path(vault_path)
    return run_generate_hierarchical_index(path)


@mcp.tool()
def read_sub_index(category: str, vault_path: str | None = None) -> str:
    """Read the sub-index (_index.md) for a specific P.A.R.A. category. Use this after identifying the relevant category from the main index."""
    path = _get_vault_path(vault_path)

    if category not in PARA_FOLDERS:
        return f"Invalid category: {category}. Must be one of: {', '.join(PARA_FOLDERS)}"

    category_path = path / category
    if not category_path.is_dir():
        return f"Category folder not found: {category}"

    sub_index_path = category_path / "_index.md"
    if sub_index_path.exists():
        return sub_index_path.read_text(encoding="utf-8")

    folder_notes = scan_folder_notes(path)
    notes = folder_notes.get(category, [])

    if not notes:
        return f"No notes found in {category}."

    result = run_generate_sub_index(path, category)
    return f"{result}\n\n{sub_index_path.read_text(encoding='utf-8')}"


@mcp.tool()
def ingest_note(
    name: str,
    note_type: str,
    title: str,
    description: str,
    content: str,
    resource: str | None = None,
    tags: list[str] | None = None,
    vault_path: str | None = None,
) -> str:
    """Create a new note with strict OKF metadata frontmatter, regenerate the index, and log the change."""
    path = _get_vault_path(vault_path)
    tags = tags or []

    if not name.endswith(".md"):
        name += ".md"

    target_file = path / name

    if target_file.exists():
        return f"Error: Note already exists at {name}"

    timestamp = datetime.now(timezone.utc)
    metadata = OKFMetadata(
        type=NoteType(note_type),
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

    index_result = run_generate_hierarchical_index(path)

    log_file = path / "log.md"
    if log_file.exists():
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_entry = (
            f"\n## [{date_str}] ingest | Created {title}\n"
            f"- **Action:** Created note '{name}' of type {note_type} via MCP tool ingest_note.\n"
            f"- **Result:** Saved note to {name} and compiled hierarchical index.\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

    lint_result = run_lint_report(path)

    return (
        f"Note '{name}' has been successfully ingested!\n"
        f"{index_result}\n"
        f"Action appended to log.md.\n\n"
        f"Linting Check:\n{lint_result}"
    )


@mcp.tool()
def search_vault_tool(query: str, max_results: int = 20, vault_path: str | None = None) -> str:
    """Full-text search across all vault notes. Returns ranked results with relevance scores and context snippets."""
    path = _get_vault_path(vault_path)

    if not query.strip():
        return "Search query cannot be empty."

    results = search_vault(path, query, max_results=max_results)
    return format_search_results(results, query)


def run() -> None:
    """Start the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
