"""
P.O.W.E.R. Index Generator.

Scans the vault for OKF-annotated notes and generates hierarchical index files:
- Root index.md (navigation map with sub-index links)
- Per-folder _index.md (detailed note catalogs)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path  # noqa: TC003

from .models import NOTE_TYPE_ORDER, PARA_FOLDERS, OKFMetadata
from .parser import read_file_content, validate_metadata
from .utils import EXCLUDED_DIRS, atomic_write


def scan_vault_notes(vault_dir: Path) -> dict[str, list[tuple[str, str, str]]]:
    """
    Scan vault directory for notes with valid OKF metadata.

    Returns a dict mapping note_type -> list of (rel_path, title, description).
    Kept for backward compatibility.
    """
    concepts: dict[str, list[tuple[str, str, str]]] = {}

    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in ("index.md", "log.md"):
            continue
        if any(part in EXCLUDED_DIRS for part in filepath.relative_to(vault_dir).parts):
            continue

        try:
            content = read_file_content(filepath)
            metadata: OKFMetadata | None = validate_metadata(content)
            if metadata is None:
                continue

            rel_path = str(filepath.relative_to(vault_dir))
            note_type = metadata.type
            title = metadata.title
            desc = metadata.description

            if note_type not in concepts:
                concepts[note_type] = []
            concepts[note_type].append((rel_path, title, desc))
        except Exception:  # noqa: S112
            continue

    return concepts


def scan_folder_notes(vault_dir: Path) -> dict[str, list[dict]]:
    """
    Scan vault directory grouping notes by their P.A.R.A. folder.

    Returns a dict mapping folder_name -> list of note dicts with keys:
        rel_path, title, description, note_type, tags, timestamp, filename
    """
    folder_notes: dict[str, list[dict]] = {}

    excluded_names = frozenset({"index.md", "log.md", "_index.md"})

    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in excluded_names:
            continue

        rel_path = filepath.relative_to(vault_dir)
        if any(part in EXCLUDED_DIRS for part in rel_path.parts):
            continue

        top_folder = rel_path.parts[0]
        if top_folder not in PARA_FOLDERS:
            continue

        try:
            content = read_file_content(filepath)
            metadata: OKFMetadata | None = validate_metadata(content)
            if metadata is None:
                continue

            tags = metadata.tags if metadata.tags else []
            ts = metadata.timestamp.isoformat() if metadata.timestamp else ""

            note_info = {
                "rel_path": str(rel_path),
                "title": metadata.title,
                "description": metadata.description,
                "note_type": metadata.type,
                "tags": tags,
                "timestamp": ts,
                "filename": filepath.name,
            }

            if top_folder not in folder_notes:
                folder_notes[top_folder] = []
            folder_notes[top_folder].append(note_info)
        except Exception:  # noqa: S112
            continue

    return folder_notes


def generate_index_content(concepts: dict[str, list[tuple[str, str, str]]]) -> str:
    """Generate the full index.md content from scanned concepts (flat, legacy)."""
    lines = [
        "---",
        "type: System Guide",
        'title: "Second Brain Index"',
        'description: "Registry of all concepts in the Second Brain"',
        f"timestamp: {datetime.now(timezone.utc).isoformat()}",
        "---",
        "",
        "# Knowledge Catalog (OKF Index)",
        "",
        "This file is automatically maintained by AI agents and contains a registry of all knowledge base pages classified by type.",
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


def generate_main_index_content(folder_notes: dict[str, list[dict]]) -> str:
    """Generate the root index.md as a navigation map linking to sub-indexes."""
    lines = [
        "---",
        "type: System Guide",
        'title: "Second Brain Index"',
        'description: "Hierarchical navigation map for the knowledge vault"',
        f"timestamp: {datetime.now(timezone.utc).isoformat()}",
        "---",
        "",
        "# Knowledge Catalog",
        "",
        "This file is automatically maintained by AI agents. ",
        "Use sub-index links to explore detailed entries per category.",
        "",
        "## Navigation Map",
        "",
        "| Category | Notes | Sub-Index |",
        "|----------|-------|-----------|",
    ]

    for folder in PARA_FOLDERS:
        notes = folder_notes.get(folder, [])
        count = len(notes)
        sub_index_link = f"[_index.md]({folder}/_index.md)"
        display_name = folder.replace("_", " ")
        lines.append(f"| {display_name} | {count} | {sub_index_link} |")

    lines.append("")
    lines.append("## Agent Protocol")
    lines.append("")
    lines.append("1. **Read this file** — identify the relevant category.")
    lines.append("2. **Read the sub-index** — load `folder/_index.md` for detailed entries.")
    lines.append("3. **Read specific notes** — only when the sub-index indicates relevance.")
    lines.append("4. **NEVER glob all `.md` files** — use sub-indexes as a map.")
    lines.append("")

    return "\n".join(lines)


def generate_sub_index_content(folder: str, notes: list[dict]) -> str:
    """Generate a detailed _index.md for a specific P.A.R.A. folder."""
    display_name = folder.replace("_", " ")

    lines = [
        "---",
        "type: System Guide",
        f'title: "{display_name} Sub-Index"',
        f'description: "Detailed catalog of all notes in {display_name}"',
        f"timestamp: {datetime.now(timezone.utc).isoformat()}",
        "---",
        "",
    ]

    if not notes:
        lines.append(f"# {display_name}")
        lines.append("")
        lines.append("_No notes in this category yet._")
        lines.append("")
    else:
        lines.append(f"# {display_name} — Detailed Index")
        lines.append("")

        sorted_notes = sorted(notes, key=lambda x: x["title"])

        for note in sorted_notes:
            lines.append(f"## {note['title']}")
            lines.append(f"- **Path:** `{note['rel_path']}`")
            lines.append(f"- **Type:** {note['note_type']}")
            lines.append(f"- **Description:** {note['description']}")
            if note["tags"]:
                tags_str = ", ".join(note["tags"])
                lines.append(f"- **Tags:** [{tags_str}]")
            if note["timestamp"]:
                lines.append(f"- **Updated:** {note['timestamp'][:10]}")
            lines.append("")

    return "\n".join(lines)


def run_generate_index(vault_dir: Path) -> str:
    """
    Generate index.md for the given vault directory (flat, legacy).

    Returns a summary message.
    """
    index_path = vault_dir / "index.md"

    concepts = scan_vault_notes(vault_dir)
    content = generate_index_content(concepts)
    atomic_write(index_path, content)

    total = sum(len(v) for v in concepts.values())
    return f"Generated index.md with {total} concepts at {index_path}."


def run_generate_sub_index(vault_dir: Path, folder: str) -> str:
    """
    Generate _index.md for a specific P.A.R.A. folder.

    Returns a summary message.
    """
    folder_notes = scan_folder_notes(vault_dir)
    notes = folder_notes.get(folder, [])

    sub_index_path = vault_dir / folder / "_index.md"
    content = generate_sub_index_content(folder, notes)
    atomic_write(sub_index_path, content)

    return f"Generated {folder}/_index.md with {len(notes)} entries."


def run_generate_hierarchical_index(vault_dir: Path) -> str:
    """
    Generate hierarchical index: root index.md + per-folder _index.md files.

    Returns a summary message.
    """
    folder_notes = scan_folder_notes(vault_dir)

    total_notes = sum(len(notes) for notes in folder_notes.values())

    main_index_path = vault_dir / "index.md"
    main_content = generate_main_index_content(folder_notes)
    atomic_write(main_index_path, main_content)

    sub_index_results = ["  index.md (navigation map)"]
    for folder in PARA_FOLDERS:
        notes = folder_notes.get(folder, [])
        sub_index_path = vault_dir / folder / "_index.md"
        sub_content = generate_sub_index_content(folder, notes)
        atomic_write(sub_index_path, sub_content)
        sub_index_results.append(f"  {folder}/_index.md ({len(notes)} notes)")

    lines = [
        f"Generated hierarchical index with {total_notes} total notes:",
    ]
    lines.extend(sub_index_results)

    return "\n".join(lines)


def generate_log_initial(vault_dir: Path, note_count: int) -> None:
    """Generate initial log.md if it doesn't exist."""
    log_path = vault_dir / "log.md"
    if log_path.exists():
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
