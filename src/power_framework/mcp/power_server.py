#!/usr/bin/env python3
"""
P.O.W.E.R. MCP Server.

Exposes MCP tools for AI agent interaction with the knowledge vault:
- lint_vault: Health check for metadata, links, and orphans
- generate_index: Compile hierarchical catalog (index.md + _index.md files)
- read_sub_index: Read a specific category sub-index on-demand
- ingest_note: Create a new note with validated OKF frontmatter
- search_vault: Full-text search across vault notes
- synthesize_session: Auto-ingest session knowledge artifact
- rot_audit: ROT (Redundant, Outdated, Trivial) analysis
- archive_notes: Move stale/expired notes to 04_Archive
- suggest_related: Auto-discover knowledge graph connections

Uses power_core for all business logic, ensuring consistency.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

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

logger = logging.getLogger(__name__)

mcp = FastMCP("power")

_write_limiter = RateLimiter(max_calls=10, period=60.0)
_index_limiter = RateLimiter(max_calls=5, period=60.0)


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
    if not _index_limiter.is_allowed("generate_index"):
        remaining = _index_limiter.remaining("generate_index")
        return f"Rate limit exceeded. Try again later. ({remaining} requests remaining in window)"

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
    if not _write_limiter.is_allowed("ingest"):
        remaining = _write_limiter.remaining("ingest")
        return f"Rate limit exceeded. Try again later. ({remaining} requests remaining in window)"

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
def search_vault_tool(
    query: str,
    max_results: int = 20,
    search_mode: str = "fts",
    vault_path: str | None = None,
) -> str:
    """Search across all vault notes. Returns ranked results with relevance scores and context snippets. Supports 'fts' (BM25, default), 'vector' (TF cosine), and 'hybrid' (RRF fusion) modes."""
    path = _get_vault_path(vault_path)

    if not query.strip():
        return "Search query cannot be empty."

    results = search_vault(path, query, max_results=max_results, mode=search_mode)
    return format_search_results(results, query, mode=search_mode)


@mcp.tool()
def synthesize_session(
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
        return f"Rate limit exceeded. Try again later. ({remaining} requests remaining in window)"

    path = _get_vault_path(vault_path)
    tags = tags or []
    related = related or []

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
        tags=tags,
        related=related,
        owner=owner,
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


@mcp.tool()
def rot_audit(vault_path: str | None = None, extended: bool = False) -> str:
    """Run the P.O.W.E.R. ROT audit: find Redundant, Outdated, and Trivial notes across the vault. Use extended=True for A2 scoring (content dedup, link rot, freshness, usage)."""
    path = _get_vault_path(vault_path)
    return run_rot_report(path, extended=extended)


@mcp.tool()
def archive_notes(dry_run: bool = True, vault_path: str | None = None) -> str:
    """Move stale/expired notes to 04_Archive. Use dry_run=True (default) to preview first."""
    path = _get_vault_path(vault_path)
    return archive_stale_notes(path, dry_run=dry_run)


@mcp.tool()
def suggest_related_tool(
    target_path: str | None = None,
    max_results: int = 5,
    vault_path: str | None = None,
) -> str:
    """Auto-suggest related notes based on keyword and tag overlap. Optionally scope to a specific note by path."""
    path = _get_vault_path(vault_path)
    suggestions = suggest_related(
        path,
        target_path=target_path,
        max_results=max_results,
    )
    return format_relation_suggestions(suggestions, path)


@mcp.tool()
def heal_frontmatter_tool(
    dry_run: bool = True,
    vault_path: str | None = None,
) -> str:
    """Scan and heal missing/invalid frontmatter fields across vault notes. Use dry_run=True (default) to preview first."""
    path = _get_vault_path(vault_path)
    return heal_vault(path, dry_run=dry_run)


@mcp.tool()
def check_markdown_tool(
    vault_path: str | None = None,
) -> str:
    """Check markdown quality issues across the vault: trailing whitespace, list markers, header jumps, code language."""
    path = _get_vault_path(vault_path)
    total_issues = 0
    lines = ["=== Markdown Quality Check Report ===", f"Vault: {path}", ""]
    issue_types: dict[str, int] = {}

    for filepath in path.rglob("*.md"):
        rel = filepath.relative_to(path)
        if any(p in (".git", "05_Templates", ".system_generated") for p in rel.parts):
            continue
        if filepath.name in ("index.md", "log.md", "_index.md"):
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


def run() -> None:
    """Start the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
