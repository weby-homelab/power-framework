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
import sys
from datetime import datetime, timezone
from pathlib import Path

from .healer import heal_vault
from .indexer import generate_log_initial, run_generate_hierarchical_index
from .linter import archive_stale_notes, run_lint_report, run_rot_report
from .markdown_checks import check_all as check_markdown_issues
from .models import VAULT_STRUCTURE, NoteType, OKFMetadata
from .parser import build_frontmatter, read_file_content
from .relations import format_relation_suggestions, suggest_related
from .searcher import format_search_results, search_vault
from .utils import __version__, atomic_write

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
    env_val = os.getenv("POWER_VAULT_DIR")
    if env_val:
        return Path(env_val).resolve()
    return Path.cwd().resolve()


def _cmd_init(args: argparse.Namespace) -> int:
    """Create a new OKF-compliant vault structure."""
    vault_dir = _resolve_path(args.path)

    if vault_dir.exists() and any(vault_dir.iterdir()):
        print(f"⚠️  Directory {vault_dir} is not empty. Use an empty directory or a new path.")  # noqa: T201
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

    print(f"Created vault structure at {vault_dir}")  # noqa: T201
    for item in created:
        print(item)  # noqa: T201
    print()  # noqa: T201
    print("Next steps:")  # noqa: T201
    print(f"  power index {args.path}")  # noqa: T201
    print(f"  power lint  {args.path}")  # noqa: T201
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    """Run health lint on the vault."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    report = run_lint_report(vault_dir)
    print(report)  # noqa: T201
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    """Generate hierarchical index (index.md + _index.md files) from vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    msg = run_generate_hierarchical_index(vault_dir)
    print(f"Generated hierarchical index:\n{msg}")  # noqa: T201
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Create a new note with OKF metadata."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    note_type = args.type
    title = args.title
    description = args.description
    resource = args.resource
    tags = args.tags or []

    # Determine target directory based on type
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

    # Create filename from title
    safe_name = title.lower().replace(" ", "_").replace("/", "-")
    note_path = target_dir / f"{safe_name}.md"

    if note_path.exists() and not args.overwrite:
        print(f"Note already exists: {note_path}")  # noqa: T201
        print("Use --overwrite to replace it.")  # noqa: T201
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
    print(f"Created note: {note_path.relative_to(vault_dir)}")  # noqa: T201
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Search vault notes with configurable mode (fts/vector/hybrid)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    query = args.query
    max_results = args.max_results
    mode = args.mode

    results = search_vault(vault_dir, query, max_results=max_results, mode=mode)
    report = format_search_results(results, query, mode=mode)
    print(report)  # noqa: T201
    return 0


def _cmd_rot(args: argparse.Namespace) -> int:
    """Run ROT (Redundant, Outdated, Trivial) audit."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1
    report = run_rot_report(vault_dir)
    print(report)  # noqa: T201
    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    """Move stale/expired notes to 04_Archive."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1
    result = archive_stale_notes(vault_dir, dry_run=args.dry_run)
    print(result)  # noqa: T201
    return 0


def _cmd_cron(args: argparse.Namespace) -> int:
    """Run automated maintenance: lint + index + rot. Designed for cron/systemd timer."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    print("=== P.O.W.E.R. Cron Maintenance ===")  # noqa: T201
    print(f"Vault: {vault_dir}")  # noqa: T201
    print()  # noqa: T201

    # Step 1: Lint
    print("--- Step 1: Lint ---")  # noqa: T201
    lint_report = run_lint_report(vault_dir)
    print(lint_report)  # noqa: T201
    print()  # noqa: T201

    # Step 2: Index
    print("--- Step 2: Index ---")  # noqa: T201
    index_msg = run_generate_hierarchical_index(vault_dir)
    print(index_msg)  # noqa: T201
    print()  # noqa: T201

    # Step 3: ROT audit
    print("--- Step 3: ROT Audit ---")  # noqa: T201
    rot_report = run_rot_report(vault_dir)
    print(rot_report)  # noqa: T201

    return 0


def _cmd_heal(args: argparse.Namespace) -> int:
    """Heal missing/invalid frontmatter in vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    dry_run = not args.no_dry_run

    report = heal_vault(vault_dir, dry_run=dry_run)
    print(report)  # noqa: T201
    return 0


def _cmd_markdown_check(args: argparse.Namespace) -> int:
    """Check markdown quality (trailing whitespace, list markers, header jumps, code language)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    total_issues = 0
    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if any(p in (".git", "05_Templates", ".system_generated") for p in rel.parts):
            continue
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue

        try:
            content = read_file_content(filepath)
        except Exception:
            logging.exception("Failed to read %s", filepath)
            continue

        issues = check_markdown_issues(content)
        if issues:
            total_issues += len(issues)
            print(f"{rel}:")  # noqa: T201
            for issue in issues:
                print(f"  L{issue['line']}: [{issue['type']}] {issue['context']}")  # noqa: T201

    print(f"\nTotal issues found: {total_issues}")  # noqa: T201
    return 0


def _cmd_suggest_related(args: argparse.Namespace) -> int:
    """Auto-suggest related notes via keyword/tag overlap."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")  # noqa: T201
        return 1

    suggestions = suggest_related(
        vault_dir,
        target_path=args.target,
        max_results=args.max_results,
    )
    report = format_relation_suggestions(suggestions, vault_dir)
    print(report)  # noqa: T201
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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # power init
    p_init = subparsers.add_parser("init", help="Create a new OKF-compliant vault structure")
    p_init.add_argument("path", help="Path to the vault directory")
    p_init.set_defaults(func=_cmd_init)

    # power lint
    p_lint = subparsers.add_parser("lint", help="Run health lint on the vault")
    p_lint.add_argument("path", help="Path to the vault directory")
    p_lint.set_defaults(func=_cmd_lint)

    # power index
    p_index = subparsers.add_parser(
        "index", help="Generate hierarchical index (index.md + per-folder _index.md)"
    )
    p_index.add_argument("path", help="Path to the vault directory")
    p_index.set_defaults(func=_cmd_index)

    # power ingest
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

    # power search
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
        choices=["fts", "vector", "hybrid"],
        default="fts",
        help='Search mode: "fts" (BM25, default), "vector" (TF cosine), "hybrid" (RRF merged)',
    )
    p_search.set_defaults(func=_cmd_search)

    # power rot
    p_rot = subparsers.add_parser("rot", help="Run ROT (Redundant, Outdated, Trivial) audit")
    p_rot.add_argument("path", help="Path to the vault directory")
    p_rot.set_defaults(func=_cmd_rot)

    # power archive
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

    # power cron
    p_cron = subparsers.add_parser(
        "cron",
        help="Run automated maintenance: lint + index + rot audit",
    )
    p_cron.add_argument("path", help="Path to the vault directory")
    p_cron.set_defaults(func=_cmd_cron)

    # power heal
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
    p_heal.set_defaults(func=_cmd_heal)

    # power markdown-check
    p_md = subparsers.add_parser(
        "markdown-check",
        help="Check markdown quality issues across the vault",
    )
    p_md.add_argument("path", help="Path to the vault directory")
    p_md.set_defaults(func=_cmd_markdown_check)

    # power suggest-related
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

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))
