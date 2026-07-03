"""
P.O.W.E.R. CLI — AI-Native Toolkit for Obsidian.

Usage:
    power init ~/my-vault
    power lint ~/my-vault
    power index ~/my-vault
    power ingest ~/my-vault --type Project --title "My Project" --description "A new project"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .indexer import generate_log_initial, run_generate_hierarchical_index
from .linter import run_lint_report
from .models import VAULT_STRUCTURE, NoteType, OKFMetadata
from .parser import build_frontmatter
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
        print(f"⚠️  Directory {vault_dir} is not empty. Use an empty directory or a new path.")
        return 1

    created = []
    for entry in VAULT_STRUCTURE:
        dir_path = vault_dir / entry
        dir_path.mkdir(parents=True, exist_ok=True)
        created.append(f"  {entry}/")

    # Create index.md
    index_path = vault_dir / "index.md"
    atomic_write(index_path, "")
    created.append("  index.md")

    # Create a minimal template note
    template_path = vault_dir / "05_Templates" / "default.md"
    content = TEMPLATE_NOTE.format(
        type="Resource",
        title="Template Note",
        description="Default OKF template for new notes",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    atomic_write(template_path, content)
    created.append("  05_Templates/default.md")

    # Create initial log.md
    generate_log_initial(vault_dir, 0)
    created.append("  log.md")

    print(f"Created vault structure at {vault_dir}")
    for item in created:
        print(item)
    print()
    print("Next steps:")
    print(f"  power index {args.path}")
    print(f"  power lint  {args.path}")
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    """Run health lint on the vault."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")
        return 1

    report = run_lint_report(vault_dir)
    print(report)
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    """Generate hierarchical index (index.md + _index.md files) from vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")
        return 1

    msg = run_generate_hierarchical_index(vault_dir)
    print(f"Generated hierarchical index:\n{msg}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Create a new note with OKF metadata."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")
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
        print(f"Note already exists: {note_path}")
        print("Use --overwrite to replace it.")
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
    print(f"Created note: {note_path.relative_to(vault_dir)}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Full-text search across vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        print(f"Vault not found: {vault_dir}")
        return 1

    query = args.query
    max_results = args.max_results

    results = search_vault(vault_dir, query, max_results=max_results)
    report = format_search_results(results, query)
    print(report)
    return 0


def main() -> None:
    """P.O.W.E.R. CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="power",
        description="AI-Native Toolkit for Obsidian — validate, index, and manage your knowledge base.",
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
    p_ingest.add_argument("--tags", nargs="*", default=[], help="Obsidian tags")
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
    p_search.set_defaults(func=_cmd_search)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))
