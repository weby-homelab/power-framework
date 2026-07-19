"""
P.O.W.E.R. CLI — AI-Native Toolkit for Second Brain.

Usage:
    power init ~/my-vault
    power lint ~/my-vault
    power index ~/my-vault
    power ingest ~/my-vault --type Project --title "My Project" --description "A new project"
"""

from __future__ import annotations

import argparse
import logging
import os
import resource
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .constants import SKIP_FILES
from .healer import heal_vault
from .ignore import should_skip
from .index_worker import set_vault_dir
from .indexer import generate_log_initial, run_generate_hierarchical_index
from .linter import archive_stale_notes, run_lint_report, run_rot_report, run_status_report
from .markdown_checks import check_all as check_markdown_issues
from .models import VAULT_STRUCTURE, NoteType, OKFMetadata
from .parser import build_frontmatter, read_file_content
from .relations import format_relation_suggestions, suggest_related
from .searcher import format_search_results, search_vault
from .utils import __version__, atomic_write

logger = logging.getLogger("power")

TEMPLATE_NOTE = """\
---
type: {type}
title: "{title}"
description: "{description}"
tags: []
timestamp: {timestamp}
---

# {title}

Your content here.
"""


def _resolve_path(path_str: str) -> Path:
    """Resolve a vault path from CLI argument or environment variable."""
    if path_str:
        return Path(path_str).expanduser().resolve()
    env_val = os.getenv("POWER_VAULT_DIR") or os.getenv("POWER_VAULT_PATH")
    if env_val:
        return Path(env_val).resolve()
    return Path.cwd().resolve()


def _cmd_init(args: argparse.Namespace) -> int:
    """Create a new OKF-compliant vault structure."""
    vault_dir = _resolve_path(args.path)

    if vault_dir.exists() and any(vault_dir.iterdir()):
        logger.warning(
            "Directory %s is not empty. Use an empty directory or a new path.", vault_dir
        )
        return 1

    created = []
    for entry in VAULT_STRUCTURE:
        dir_path = vault_dir / entry
        dir_path.mkdir(parents=True, exist_ok=True)
        created.append(f"  {entry}/")

    index_path = vault_dir / "index.md"
    atomic_write(index_path, "")
    created.append("  index.md")

    template_path = vault_dir / "05_Templates" / "default.md"
    content = TEMPLATE_NOTE.format(
        type="Resource",
        title="Template Note",
        description="Default OKF template for new notes",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    atomic_write(template_path, content)
    created.append("  05_Templates/default.md")

    generate_log_initial(vault_dir, 0)
    created.append("  log.md")

    logger.info("Created vault structure at %s", vault_dir)
    for item in created:
        logger.info(item)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  power index %s", args.path)
    logger.info("  power lint  %s", args.path)
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    """Run health lint on the vault."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    report = run_lint_report(vault_dir)
    logger.info(report)
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    """Generate hierarchical index (index.md + _index.md files) from vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    msg = run_generate_hierarchical_index(vault_dir)
    logger.info("Generated hierarchical index:\n%s", msg)
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Create a new note with OKF metadata."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    note_type = args.type
    title = args.title
    description = args.description
    resource = args.resource
    tags = args.tags or []

    type_dir_map = {
        "Project": "01_Projects",
        "Area": "02_Areas",
        "Resource": "03_Resources",
        "Daily Log": "06_Daily_Logs",
        "Archive": "04_Archive",
        "System Guide": "PROTOCOLS",
    }
    target_dir = vault_dir / type_dir_map.get(note_type, "00_Inbox")
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = title.lower().replace(" ", "_").replace("/", "-")
    note_path = target_dir / f"{safe_name}.md"

    if note_path.exists() and not args.overwrite:
        logger.warning("Note already exists: %s", note_path)
        logger.warning("Use --overwrite to replace it.")
        return 1

    metadata = OKFMetadata(
        type=NoteType(note_type),
        title=title,
        description=description,
        resource=resource,
        tags=tags,
        timestamp=datetime.now(timezone.utc),
    )
    fm = build_frontmatter(metadata)
    body = f"{fm}\n\n# {title}\n\n"
    atomic_write(note_path, body)
    logger.info("Created note: %s", note_path.relative_to(vault_dir))
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Search vault notes with configurable mode (fts/vector/hybrid)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    query = args.query
    max_results = args.max_results
    mode = args.mode

    results = search_vault(vault_dir, query, max_results=max_results, mode=mode)
    report = format_search_results(results, query, mode=mode, vault_dir=vault_dir)
    print(report)
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    """Synchronously build the search index for the vault (FTS + embeddings)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    from .searcher import _sync_vault_to_db

    set_vault_dir(vault_dir)
    sync_embeddings = not getattr(args, "fts_only", False)

    # v2.2.0 low-RAM guard: cap the address space so an over-sized embedding
    # batch cannot trigger the kernel OOM-killer and take down the host. This is
    # an OPT-IN backstop (default 0 = disabled) because some backends (e.g.
    # Qwen3-0.6B ONNX) legitimately need >6 GB for their inference arena. Enable
    # it on tight 8 GB hosts via POWER_SYNC_VMEM_LIMIT_MB=6144.
    vmem_limit_mb = int(os.getenv("POWER_SYNC_VMEM_LIMIT_MB", "0"))
    if vmem_limit_mb and sync_embeddings and hasattr(resource, "RLIMIT_AS"):
        try:
            _, hard = resource.getrlimit(resource.RLIMIT_AS)
            new_soft = (
                min(vmem_limit_mb * 1024 * 1024, hard) if hard > 0 else vmem_limit_mb * 1024 * 1024
            )
            resource.setrlimit(resource.RLIMIT_AS, (new_soft, hard))
            logger.info("Applied virtual-memory cap: %d MB", vmem_limit_mb)
        except (ValueError, OSError) as e:  # pragma: no cover
            logger.warning("Could not apply vmem cap: %s", e)

    logger.info(
        "Building %s index for %s ...",
        "semantic" if sync_embeddings else "fts",
        vault_dir,
    )
    force_rebuild = getattr(args, "force", False)
    _sync_vault_to_db(
        vault_dir,
        _open_conn(),
        sync_embeddings=sync_embeddings,
        force_rebuild=force_rebuild,
    )
    logger.info("Index build complete.")
    return 0


def _open_conn() -> sqlite3.Connection:
    from .db import _init_db
    from .searcher import _db_path

    db_path = _db_path()
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    return conn


def _cmd_rot(args: argparse.Namespace) -> int:
    """Run ROT (Redundant, Outdated, Trivial) audit."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    report = run_rot_report(vault_dir, extended=args.extended)
    logger.info(report)
    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    """Move stale/expired notes to 04_Archive."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    result = archive_stale_notes(vault_dir, dry_run=args.dry_run)
    logger.info(result)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show vault status dashboard."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    report = run_status_report(vault_dir)
    print(report)
    return 0


def _cmd_cron(args: argparse.Namespace) -> int:
    """Run automated maintenance: lint + index + rot. Designed for cron/systemd timer."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    logger.info("=== P.O.W.E.R. Cron Maintenance ===")
    logger.info("Vault: %s", vault_dir)
    logger.info("")

    logger.info("--- Step 1: Lint ---")
    lint_report = run_lint_report(vault_dir)
    logger.info(lint_report)
    logger.info("")

    logger.info("--- Step 2: Index ---")
    index_msg = run_generate_hierarchical_index(vault_dir)
    logger.info(index_msg)
    logger.info("")

    logger.info("--- Step 3: ROT Audit ---")
    rot_report = run_rot_report(vault_dir)
    logger.info(rot_report)

    return 0


def _cmd_heal(args: argparse.Namespace) -> int:
    """Heal missing/invalid frontmatter in vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    dry_run = not args.no_dry_run
    limit = getattr(args, "limit", None)

    report = heal_vault(vault_dir, dry_run=dry_run, limit=limit)
    logger.info(report)
    return 0


def _cmd_rename(args: argparse.Namespace) -> int:
    """Rename a vault note and update related paths in other notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    old_rel = args.old
    new_rel = args.new
    dry_run = not args.no_dry_run

    old_file = vault_dir / old_rel
    new_file = vault_dir / new_rel

    if not old_file.exists() or not old_file.is_file():
        logger.error("Source note not found: %s", old_file)
        return 1

    # 1. Rename physically if not dry run
    if not dry_run:
        new_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.rename(old_file, new_file)
            logger.info("Physically renamed %s to %s", old_rel, new_rel)
        except Exception as e:
            logger.error("Failed to rename file physically: %s", e)
            return 1
    else:
        logger.info("[DRY RUN] Would rename %s to %s", old_rel, new_rel)

    # 2. Propagate rename references
    from .healer import propagate_rename

    updated_count, logs = propagate_rename(vault_dir, old_rel, new_rel, dry_run=dry_run)

    if logs:
        logger.info("Updated references:")
        for log in logs:
            logger.info(log)
    else:
        logger.info("No other notes reference this path.")

    logger.info("Rename process completed. Updated notes: %d", updated_count)
    return 0


def _cmd_markdown_check(args: argparse.Namespace) -> int:
    """Check markdown quality (trailing whitespace, list markers, header jumps, code language)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    total_issues = 0
    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, str(rel)):
            continue
        if filepath.name in SKIP_FILES:
            continue

        try:
            content = read_file_content(filepath)
        except Exception as exc:
            logger.debug("Cannot read %s: %s", filepath, exc)
            continue

        issues = check_markdown_issues(content)
        if issues:
            total_issues += len(issues)
            logger.info("%s:", rel)
            for issue in issues:
                logger.info("  L%s: [%s] %s", issue["line"], issue["type"], issue["context"])

    logger.info("\nTotal issues found: %s", total_issues)
    return 0


def _cmd_suggest_related(args: argparse.Namespace) -> int:
    """Auto-suggest related notes via keyword/tag overlap."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    suggestions = suggest_related(
        vault_dir,
        target_path=args.target,
        max_results=args.max_results,
    )
    report = format_relation_suggestions(suggestions, vault_dir)
    logger.info(report)
    return 0


def main() -> None:
    """P.O.W.E.R. CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="power",
        description="AI-Native Toolkit for Second Brain — validate, index, and manage your knowledge base.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"power {__version__}",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose logging (DEBUG level)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_init = subparsers.add_parser("init", help="Create a new OKF-compliant vault structure")
    p_init.add_argument("path", help="Path to the vault directory")
    p_init.set_defaults(func=_cmd_init)

    p_lint = subparsers.add_parser("lint", help="Run health lint on the vault")
    p_lint.add_argument("path", help="Path to the vault directory")
    p_lint.set_defaults(func=_cmd_lint)

    p_index = subparsers.add_parser(
        "index", help="Generate hierarchical index (index.md + per-folder _index.md)"
    )
    p_index.add_argument("path", help="Path to the vault directory")
    p_index.set_defaults(func=_cmd_index)

    p_ingest = subparsers.add_parser("ingest", help="Create a new note with OKF metadata")
    p_ingest.add_argument("path", help="Path to the vault directory")
    p_ingest.add_argument(
        "--type",
        "-t",
        required=True,
        choices=[t.value for t in NoteType],
        help="OKF note type",
    )
    p_ingest.add_argument("--title", required=True, help="Note title")
    p_ingest.add_argument("--description", required=True, help="Short summary (max 150 chars)")
    p_ingest.add_argument("--resource", default=None, help="External URL (optional)")
    p_ingest.add_argument("--tags", nargs="*", default=[], help="Markdown tags")
    p_ingest.add_argument("--overwrite", action="store_true", help="Overwrite existing note")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_search = subparsers.add_parser("search", help="Full-text search across vault notes")
    p_search.add_argument("path", help="Path to the vault directory")
    p_search.add_argument(
        "query", help='Search query (supports multiple terms and "quoted phrases")'
    )
    p_search.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum number of results (default: 20)",
    )
    p_search.add_argument(
        "--mode",
        choices=["fts", "vector", "hybrid", "semantic", "hybrid_reranked"],
        default="fts",
        help='Search mode: "fts" (BM25, default), "vector" (TF cosine), "hybrid" (RRF merged), "semantic" (dense embedding), "hybrid_reranked" (RRF + cross-encoder)',
    )
    p_search.set_defaults(func=_cmd_search)

    p_sync = subparsers.add_parser(
        "sync", help="Build the search index for the vault (FTS + dense embeddings)"
    )
    p_sync.add_argument("path", help="Path to the vault directory")
    p_sync.add_argument(
        "--fts-only",
        action="store_true",
        default=False,
        help="Only build the lightweight FTS index (skip embedding generation)",
    )
    p_sync.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force a full rebuild of dense embeddings (required after changing the embedding model/dimension)",
    )
    p_sync.set_defaults(func=_cmd_sync)

    p_rot = subparsers.add_parser("rot", help="Run ROT (Redundant, Outdated, Trivial) audit")
    p_rot.add_argument("path", help="Path to the vault directory")
    p_rot.add_argument(
        "--extended",
        action="store_true",
        default=False,
        help="Enable extended A2 scoring (content dedup, link rot, freshness, usage)",
    )
    p_rot.set_defaults(func=_cmd_rot)

    p_archive = subparsers.add_parser(
        "archive",
        help="Move stale/expired notes to 04_Archive",
    )
    p_archive.add_argument("path", help="Path to the vault directory")
    p_archive.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate without moving (default: true)",
    )
    p_archive.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Actually move files",
    )
    p_archive.set_defaults(func=_cmd_archive)

    p_status = subparsers.add_parser("status", help="Show vault status dashboard")
    p_status.add_argument(
        "path", nargs="?", default=None, help="Path to the vault directory (optional)"
    )
    p_status.set_defaults(func=_cmd_status)

    p_cron = subparsers.add_parser(
        "cron",
        help="Run automated maintenance: lint + index + rot audit",
    )
    p_cron.add_argument("path", help="Path to the vault directory")
    p_cron.set_defaults(func=_cmd_cron)

    p_heal = subparsers.add_parser(
        "heal",
        help="Heal missing/invalid frontmatter in vault notes",
    )
    p_heal.add_argument("path", help="Path to the vault directory")
    p_heal.add_argument(
        "--no-dry-run",
        action="store_true",
        default=False,
        help="Actually apply fixes (default: dry run)",
    )
    p_heal.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Heal at most N notes then stop (useful for large vaults)",
    )
    p_heal.set_defaults(func=_cmd_heal)

    p_md = subparsers.add_parser(
        "markdown-check",
        help="Check markdown quality issues across the vault",
    )
    p_md.add_argument("path", help="Path to the vault directory")
    p_md.set_defaults(func=_cmd_markdown_check)

    p_suggest = subparsers.add_parser(
        "suggest-related",
        help="Auto-suggest related notes via keyword/tag overlap",
    )
    p_suggest.add_argument("path", help="Path to the vault directory")
    p_suggest.add_argument(
        "--target",
        default=None,
        help="Specific note path to find relations for (optional)",
    )
    p_suggest.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Max suggestions (default: 5)",
    )
    p_suggest.set_defaults(func=_cmd_suggest_related)

    p_rename = subparsers.add_parser(
        "rename",
        help="Rename a vault note and update related paths in other notes",
    )
    p_rename.add_argument("path", help="Path to the vault directory")
    p_rename.add_argument("--old", required=True, help="Old relative path of the note")
    p_rename.add_argument("--new", required=True, help="New relative path of the note")
    p_rename.add_argument(
        "--no-dry-run",
        action="store_true",
        default=False,
        help="Actually apply changes (default: dry run)",
    )
    p_rename.set_defaults(func=_cmd_rename)

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stderr,
    )

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))
