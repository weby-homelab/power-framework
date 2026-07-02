"""
P.O.W.E.R. Index Generator.

Scans the vault for OKF-annotated notes and generates a hierarchical catalog:
- Main index.md with summary (section headers + counts)
- Per-folder _index.md files with detailed entries

This structure keeps the main index small and token-efficient for AI agents,
while detailed entries are loaded on-demand from sub-index files.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .models import NOTE_TYPE_ORDER, OKFMetadata
from .parser import read_file_content, validate_metadata
from .utils import atomic_write, is_excluded_dir

# Maps OKF note types to their P.A.R.A. directory names
FOLDER_MAP: dict[str, str] = {
    "Project": "01_Projects",
    "Area": "02_Areas",
    "Resource": "03_Resources",
    "Daily Log": "06_Daily_Logs",
    "Archive": "04_Archive",
    "System Guide": "PROTOCOLS",
}


def scan_vault_notes(vault_dir: Path) -> dict[str, list[tuple[str, str, str]]]:
    """
    Scan vault directory for notes with valid OKF metadata.

    Returns a dict mapping note_type -> list of (rel_path, title, description).
    """
    concepts: dict[str, list[tuple[str, str, str]]] = {}

    for root, dirs, files in os.walk(vault_dir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d)]

        for file in files:
            if not file.endswith(".md") or file in ("index.md", "log.md", "_index.md"):
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


def generate_hierarchical_index(
    vault_dir: Path,
    concepts: dict[str, list[tuple[str, str, str]]],
) -> dict[str, str]:
    """
    Generate hierarchical index: main summary + per-folder _index.md files.

    Returns a dict mapping relative file paths to their content.
    The caller should write each file atomically.
    """
    outputs: dict[str, str] = {}

    # Group notes by folder (directory)
    by_folder: dict[str, list[tuple[str, str, str]]] = {}
    by_type: dict[str, list[tuple[str, str, str]]] = {}

    for rel_path, title, desc in _flatten_concepts(concepts):
        folder = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
        by_folder.setdefault(folder, []).append((rel_path, title, desc))

    for note_type, items in concepts.items():
        by_type[note_type] = list(items)

    # Generate _index.md for each folder that has notes
    for folder, items in sorted(by_folder.items()):
        folder_lines = [
            "---",
            "type: System Guide",
            f'title: "{folder} Index"',
            f'description: "Catalog of notes in {folder}"',
            f"timestamp: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {folder} Catalog",
            "",
        ]
        for rel_path, title, desc in sorted(items, key=lambda x: x[1]):
            folder_lines.append(f"- **[{title}]({rel_path})** - {desc}")
        folder_lines.append("")

        outputs[f"{folder}/_index.md"] = "\n".join(folder_lines)

    # Generate main index.md with summary only
    main_lines = [
        "---",
        "type: System Guide",
        'title: "Second Brain Index"',
        'description: "Hierarchical registry of all concepts in the Second Brain"',
        f"timestamp: {datetime.now().isoformat()}",
        "---",
        "",
        "# Knowledge Catalog (Hierarchical OKF Index)",
        "",
        "This file provides a high-level overview. ",
        "Each section links to a detailed `_index.md` within its directory.",
        "",
    ]

    for note_type in NOTE_TYPE_ORDER:
        if note_type not in by_type:
            continue
        folder = FOLDER_MAP.get(note_type, "")
        count = len(by_type[note_type])
        main_lines.append(f"## {note_type}s ({count} notes)")
        if folder:
            main_lines.append(f"> See full catalog: [`{folder}/_index.md`]({folder}/_index.md)")
        main_lines.append("")

    outputs["index.md"] = "\n".join(main_lines)
    return outputs


def _flatten_concepts(
    concepts: dict[str, list[tuple[str, str, str]]],
) -> list[tuple[str, str, str]]:
    """Flatten concepts dict into a single list of (rel_path, title, desc)."""
    result: list[tuple[str, str, str]] = []
    for items in concepts.values():
        result.extend(items)
    return result


def run_generate_index(vault_dir: Path) -> str:
    """
    Generate hierarchical index files for the given vault directory.

    Creates index.md (summary) + per-folder _index.md files.

    Returns a summary message.
    """
    concepts = scan_vault_notes(vault_dir)
    total = sum(len(v) for v in concepts.values())

    outputs = generate_hierarchical_index(vault_dir, concepts)

    # Write all output files atomically
    for rel_path, content in outputs.items():
        target = vault_dir / rel_path
        atomic_write(target, content)

    sub_count = len(outputs) - 1  # exclude index.md
    return (
        f"Generated hierarchical index with {total} concepts: "
        f"index.md + {sub_count} sub-index files at {vault_dir}."
    )


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
