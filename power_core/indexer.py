"""
P.O.W.E.R. Index Generator.

Scans the vault for OKF-annotated notes and generates the catalog index.md.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .models import NOTE_TYPE_ORDER, OKFMetadata
from .parser import read_file_content, validate_metadata
from .utils import atomic_write, is_excluded_dir


def scan_vault_notes(vault_dir: Path) -> dict[str, list[tuple[str, str, str]]]:
    """
    Scan vault directory for notes with valid OKF metadata.

    Returns a dict mapping note_type -> list of (rel_path, title, description).
    """
    concepts: dict[str, list[tuple[str, str, str]]] = {}

    for root, dirs, files in os.walk(vault_dir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d)]

        for file in files:
            if not file.endswith(".md") or file in ("index.md", "log.md"):
                continue

            filepath = Path(root) / file
            try:
                content = read_file_content(filepath)
                metadata: OKFMetadata | None = validate_metadata(content)
                if metadata is None:
                    continue

                rel_path = os.path.relpath(filepath, vault_dir)
                note_type = metadata.type
                title = metadata.title
                desc = metadata.description

                if note_type not in concepts:
                    concepts[note_type] = []
                concepts[note_type].append((rel_path, title, desc))
            except Exception:
                continue

    return concepts


def generate_index_content(concepts: dict[str, list[tuple[str, str, str]]]) -> str:
    """Generate the full index.md content from scanned concepts."""
    lines = [
        "---",
        "type: System Guide",
        'title: "Second Brain Index"',
        'description: "Registry of all concepts in the Second Brain"',
        f"timestamp: {datetime.now().isoformat()}",
        "---",
        "",
        "# Knowledge Catalog (OKF Index)",
        "",
        "This file is automatically maintained by AI agents and contains "
        "a registry of all knowledge base pages classified by type.",
        "",
    ]

    sorted_types = sorted(
        concepts.keys(),
        key=lambda t: NOTE_TYPE_ORDER.index(t) if t in NOTE_TYPE_ORDER else 99,
    )

    for note_type in sorted_types:
        lines.append(f"## {note_type}s")
        items = sorted(concepts[note_type], key=lambda x: x[1])
        for rel_path, title, desc in items:
            lines.append(f"- **[{title}]({rel_path})** - {desc}")
        lines.append("")

    return "\n".join(lines)


def run_generate_index(vault_dir: Path) -> str:
    """
    Generate index.md for the given vault directory.

    Returns a summary message.
    """
    index_path = vault_dir / "index.md"

    concepts = scan_vault_notes(vault_dir)
    content = generate_index_content(concepts)
    atomic_write(index_path, content)

    total = sum(len(v) for v in concepts.values())
    return f"Generated index.md with {total} concepts at {index_path}."


def generate_log_initial(vault_dir: Path, note_count: int) -> None:
    """Generate initial log.md if it doesn't exist."""
    log_path = vault_dir / "log.md"
    if log_path.exists():
        return

    timestamp = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y-%m-%d")
    content = "\n".join(
        [
            "---",
            "type: System Guide",
            'title: "Second Brain Change Log"',
            'description: "Append-only chronological log of operations"',
            f"timestamp: {timestamp}",
            "---",
            "",
            "# Chronological Second Brain Change Log",
            "",
            f"## [{date_str}] initialization",
            "- **Action:** Initialized OKF / LLM-Wiki schema overlay across the vault.",
            f"- **Result:** Migrated {note_count} files to OKF format and compiled index.",
            "",
        ]
    )
    atomic_write(log_path, content)
