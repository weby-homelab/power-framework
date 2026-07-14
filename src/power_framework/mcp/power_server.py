#!/usr/bin/env python3
"""
P.O.W.E.R. MCP Server (FastMCP 3.x).

Exposes MCP tools for AI agent interaction with the knowledge vault:
- lint_vault: Health check for metadata, links, and orphans
- generate_index: Compile hierarchical catalog (index.md + _index.md files)
- read_sub_index: Read a specific category sub-index on-demand (read-only)
- ensure_sub_index: Generate and read a category sub-index (write path)
- ingest_note: Create a new note with validated OKF frontmatter
- search_vault_tool: Full-text search across vault notes
- synthesize_session: Auto-ingest session knowledge artifact
- rot_audit: ROT (Redundant, Outdated, Trivial) analysis
- archive_notes: Move stale/expired notes to 04_Archive
- suggest_related_tool: Auto-discover knowledge graph connections
- heal_frontmatter_tool: Auto-fix missing/invalid frontmatter
- check_markdown_tool: Markdown quality audit

Supports stdio transport (local) and HTTP transport (Docker, with /health endpoint).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware

if TYPE_CHECKING:
    from pathlib import Path

from power_framework.core import (
    PARA_FOLDERS,
    NoteType,
    OKFMetadata,
    RateLimiter,
    archive_stale_notes,
    atomic_write,
    build_frontmatter,
    format_relation_suggestions,
    format_search_results,
    heal_vault,
    read_file_content,
    resolve_vault_path,
    run_generate_hierarchical_index,
    run_generate_sub_index,
    run_lint_report,
    run_rot_report,
    scan_folder_notes,
    search_vault,
    suggest_related,
)
from power_framework.core import (
    check_all as check_markdown,
)
from power_framework.core.constants import SKIP_FILES, SYSTEM_SKIP_PARTS
from power_framework.core.ignore import should_skip

logger = logging.getLogger(__name__)

mcp = FastMCP("power", mask_error_details=True)
mcp.add_middleware(
    ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    )
)

_write_limiter = RateLimiter(max_calls=10, period=60.0)
_index_limiter = RateLimiter(max_calls=5, period=60.0)


def _get_vault_path(vault_path: str | None = None) -> Path:
    """Resolve vault path with security validation."""
    args = {"vault_path": vault_path} if vault_path else {}
    return resolve_vault_path(args)


@mcp.tool
async def lint_vault(vault_path: str | None = None) -> str:
    """Run the P.O.W.E.R. health check / linter to verify note metadata, link integrity, and check for orphans."""
    path = _get_vault_path(vault_path)
    return await asyncio.to_thread(run_lint_report, path)


@mcp.tool
async def generate_index(vault_path: str | None = None) -> str:
    """Compile the vault hierarchical index: a summary index.md plus per-folder _index.md files."""
    if not _index_limiter.is_allowed("generate_index"):
        remaining = _index_limiter.remaining("generate_index")
        raise ToolError(
            f"Rate limit exceeded. Try again later. ({remaining} requests remaining in window)"
        )

    path = _get_vault_path(vault_path)
    return await asyncio.to_thread(run_generate_hierarchical_index, path)


@mcp.tool
async def read_sub_index(category: str, vault_path: str | None = None) -> str:
    """Read the sub-index (_index.md) for a specific P.A.R.A. category. Use this after identifying the relevant category from the main index. Read-only — does not generate files."""
    path = _get_vault_path(vault_path)

    if category not in PARA_FOLDERS:
        raise ToolError(f"Invalid category: {category}. Must be one of: {', '.join(PARA_FOLDERS)}")

    category_path = path / category
    if not category_path.is_dir():
        raise ToolError(f"Category folder not found: {category}")

    sub_index_path = category_path / "_index.md"
    if sub_index_path.exists():
        return sub_index_path.read_text(encoding="utf-8")

    return f"No _index.md found for {category}. Use ensure_sub_index to generate it."


@mcp.tool
async def ensure_sub_index(category: str, vault_path: str | None = None) -> str:
    """Generate and read a sub-index (_index.md) for a P.A.R.A. category. Use this when _index.md is missing and you need to generate it."""
    path = _get_vault_path(vault_path)

    if category not in PARA_FOLDERS:
        raise ToolError(f"Invalid category: {category}. Must be one of: {', '.join(PARA_FOLDERS)}")

    category_path = path / category
    if not category_path.is_dir():
        raise ToolError(f"Category folder not found: {category}")

    folder_notes = await asyncio.to_thread(scan_folder_notes, path)
    notes = folder_notes.get(category, [])

    if not notes:
        return f"No notes found in {category}."

    def _gen_and_read() -> str:
        result = run_generate_sub_index(path, category)
        sub_path = category_path / "_index.md"
        return f"{result}\n\n{sub_path.read_text(encoding='utf-8')}"

    return await asyncio.to_thread(_gen_and_read)


@mcp.tool
async def ingest_note(
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
    if not _write_limiter.is_allowed("ingest"):
        remaining = _write_limiter.remaining("ingest")
        raise ToolError(
            f"Rate limit exceeded. Try again later. ({remaining} requests remaining in window)"
        )

    path = _get_vault_path(vault_path)
    tags = tags or []

    if not name.endswith(".md"):
        name += ".md"

    target_file = path / name

    if target_file.exists():
        raise ToolError(f"Note already exists at {name}")

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

    def _write_and_index() -> str:
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

    return await asyncio.to_thread(_write_and_index)


@mcp.tool
async def search_vault_tool(
    query: str,
    max_results: int = 20,
    search_mode: str = "fts",
    vault_path: str | None = None,
) -> str:
    """Search across all vault notes. Returns ranked results with relevance scores and context snippets. Supports 'fts' (BM25, default), 'vector' (TF cosine), and 'hybrid' (RRF fusion) modes."""
    path = _get_vault_path(vault_path)

    if not query.strip():
        raise ToolError("Search query cannot be empty.")

    def _do_search() -> str:
        results = search_vault(path, query, max_results=max_results, mode=search_mode)
        return format_search_results(results, query, mode=search_mode)

    return await asyncio.to_thread(_do_search)


@mcp.tool
async def synthesize_session(
    name: str,
    title: str,
    description: str,
    content: str,
    note_type: str = "Daily Log",
    tags: list[str] | None = None,
    related: list[str] | None = None,
    owner: str | None = None,
    vault_path: str | None = None,
) -> str:
    """
    Create a new session synthesis note with auto-classified OKF frontmatter,
    Graph RAG related links, and full index/log maintenance.

    This implements the Agent Auto-Ingest Feedback Loop — every significant
    session automatically generates a persistent knowledge artifact with
    governance metadata.
    """
    if not _write_limiter.is_allowed("synthesize"):
        remaining = _write_limiter.remaining("synthesize")
        raise ToolError(
            f"Rate limit exceeded. Try again later. ({remaining} requests remaining in window)"
        )

    path = _get_vault_path(vault_path)
    tags = tags or []
    related = related or []

    if not name.endswith(".md"):
        name += ".md"

    target_file = path / name
    if target_file.exists():
        raise ToolError(f"Note already exists at {name}")

    timestamp = datetime.now(timezone.utc)
    metadata = OKFMetadata(
        type=NoteType(note_type),
        title=title,
        description=description,
        tags=tags,
        related=related,
        owner=owner,
        timestamp=timestamp,
    )

    frontmatter = build_frontmatter(metadata)
    full_content = f"{frontmatter}\n\n{content}\n"

    def _write_and_index() -> str:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target_file, full_content)
        index_result = run_generate_hierarchical_index(path)

        log_file = path / "log.md"
        if log_file.exists():
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_entry = (
                f"\n## [{date_str}] synthesize | {title}\n"
                f"- **Action:** Created session note '{name}' of type {note_type}.\n"
                f"- **Related:** {', '.join(related) if related else 'none'}\n"
                f"- **Owner:** {owner or 'unassigned'}\n"
                f"- **Result:** Saved to {name} and compiled hierarchical index.\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)

        lint_result = run_lint_report(path)
        return (
            f"Session note '{name}' has been synthesized and ingested!\n"
            f"{index_result}\n"
            f"Action appended to log.md.\n\n"
            f"Linting Check:\n{lint_result}"
        )

    return await asyncio.to_thread(_write_and_index)


@mcp.tool
async def rot_audit(vault_path: str | None = None, extended: bool = False) -> str:
    """Run the P.O.W.E.R. ROT audit: find Redundant, Outdated, and Trivial notes across the vault. Use extended=True for A2 scoring (content dedup, link rot, freshness, usage)."""
    path = _get_vault_path(vault_path)
    return await asyncio.to_thread(run_rot_report, path, extended=extended)


@mcp.tool
async def archive_notes(dry_run: bool = True, vault_path: str | None = None) -> str:
    """Move stale/expired notes to 04_Archive. Use dry_run=True (default) to preview first."""
    path = _get_vault_path(vault_path)
    return await asyncio.to_thread(archive_stale_notes, path, dry_run=dry_run)


@mcp.tool
async def suggest_related_tool(
    target_path: str | None = None,
    max_results: int = 5,
    vault_path: str | None = None,
) -> str:
    """Auto-suggest related notes based on keyword and tag overlap. Optionally scope to a specific note by path."""
    path = _get_vault_path(vault_path)

    def _do_suggest() -> str:
        suggestions = suggest_related(
            path,
            target_path=target_path,
            max_results=max_results,
        )
        return format_relation_suggestions(suggestions, path)

    return await asyncio.to_thread(_do_suggest)


@mcp.tool
async def heal_frontmatter_tool(
    dry_run: bool = True,
    vault_path: str | None = None,
) -> str:
    """Scan and heal missing/invalid frontmatter fields across vault notes. Use dry_run=True (default) to preview first."""
    path = _get_vault_path(vault_path)
    return await asyncio.to_thread(heal_vault, path, dry_run=dry_run)


@mcp.tool
async def check_markdown_tool(
    vault_path: str | None = None,
) -> str:
    """Check markdown quality issues across the vault: trailing whitespace, list markers, header jumps, code language."""
    path = _get_vault_path(vault_path)

    def _do_check() -> str:
        total_issues = 0
        lines = ["=== Markdown Quality Check Report ===", f"Vault: {path}", ""]
        issue_types: dict[str, int] = {}

        for filepath in path.rglob("*.md"):
            rel = filepath.relative_to(path)
            if should_skip(path, str(rel)):
                continue
            if filepath.name in SKIP_FILES:
                continue

            try:
                content = read_file_content(filepath)
            except Exception as exc:
                logger.debug("Cannot read %s: %s", filepath, exc)
                continue

            issues = check_markdown(content)
            if issues:
                total_issues += len(issues)
                lines.append(f"{rel}:")
                for issue in issues:
                    t = issue["type"]
                    issue_types[t] = issue_types.get(t, 0) + 1
                    lines.append(f"  L{issue['line']}: [{t}] {issue['context']}")

        if total_issues == 0:
            lines.append("No markdown quality issues found.")
        else:
            lines.append("")
            lines.append("Summary by issue type:")
            for t, count in sorted(issue_types.items()):
                lines.append(f"  {t}: {count}")
            lines.append(f"\nTotal issues found: {total_issues}")

        return "\n".join(lines)

    return await asyncio.to_thread(_do_check)


def run() -> None:
    """Start the MCP server. Transport is determined by POWER_MCP_TRANSPORT env var.

    Defaults to stdio for local use. Set POWER_MCP_TRANSPORT=http for Docker/HTTP mode.
    """
    transport = os.getenv("POWER_MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="http", host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
