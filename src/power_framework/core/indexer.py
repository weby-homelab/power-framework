"""
P.O.W.E.R. Index Generator.

Scans the vault for OKF-annotated notes and generates hierarchical index files:
- Root index.md (navigation map with sub-index links)
- Per-folder _index.md (detailed note catalogs)
"""

from __future__ import annotations

import json
import posixpath
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from .constants import INDEX_FOLDERS, INDEX_MAX_BYTES, is_catalog_filename
from .ignore import should_skip
from .models import MAX_DESCRIPTION_LENGTH, NOTE_TYPE_ORDER, OKFMetadata, TypedRelation
from .parser import read_file_content, validate_metadata
from .utils import atomic_write, is_regular_vault_file, iter_vault_markdown_files
from .vault_storage import vault_cache_dir

INDEX_CACHE_SCHEMA_VERSION = 3
INDEX_RENDERER_VERSION = 2
CATALOG_MARKER = "x-generated-by: power"


def truncate_for_catalog(description: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> str:
    """Truncate a note description to ``max_length`` for catalog (index.md) rendering only.

    The stored note keeps its full description; truncation is applied solely when
    rendering the hierarchical index so the catalog row stays compact.
    """
    if not description:
        return ""
    if len(description) <= max_length:
        return description
    return description[: max_length - 3].rstrip() + "..."


def scan_vault_notes(vault_dir: Path) -> dict[str, list[tuple[str, str, str]]]:
    """
    Scan vault directory for notes with valid OKF metadata.

    Returns a dict mapping note_type -> list of (rel_path, title, description).
    Kept for backward compatibility.
    """
    concepts: dict[str, list[tuple[str, str, str]]] = {}

    for filepath in iter_vault_markdown_files(vault_dir):
        if filepath.name in {"index.md", "log.md"} or is_catalog_filename(filepath.name):
            continue
        if should_skip(vault_dir, filepath.relative_to(vault_dir).as_posix()):
            continue

        try:
            content = read_file_content(filepath)
            metadata: OKFMetadata | None = validate_metadata(content)
            if metadata is None:
                continue

            rel_path = filepath.relative_to(vault_dir).as_posix()
            note_type = metadata.type
            title = metadata.title
            desc = metadata.description

            if note_type not in concepts:
                concepts[note_type] = []
            concepts[note_type].append((rel_path, title, desc))
        except Exception:  # noqa: S112
            continue

    return concepts


def scan_folder_notes(
    vault_dir: Path, invalid_notes: list[tuple[str, str]] | None = None
) -> dict[str, list[dict]]:
    """
    Scan vault directory grouping notes by their P.A.R.A. folder.

    Returns a dict mapping folder_name -> list of note dicts with keys:
        rel_path, title, description, note_type, tags, timestamp, filename
    """
    folder_notes: dict[str, list[dict]] = {}

    for filepath in iter_vault_markdown_files(vault_dir):
        if filepath.name in {"index.md", "log.md"} or is_catalog_filename(filepath.name):
            continue

        rel_path = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, rel_path.as_posix()):
            continue

        top_folder = rel_path.parts[0]
        if top_folder not in INDEX_FOLDERS:
            continue

        try:
            content = read_file_content(filepath)
            metadata: OKFMetadata | None = validate_metadata(content)
            if metadata is None:
                if invalid_notes is not None:
                    invalid_notes.append((rel_path.as_posix(), "Invalid OKF metadata"))
                continue

            tags = metadata.tags if metadata.tags else []
            ts = metadata.timestamp.isoformat() if metadata.timestamp else ""
            owner = metadata.owner if metadata.owner else ""
            status = metadata.status if metadata.status else ""
            expiry = metadata.expiry.isoformat() if metadata.expiry else ""
            related = metadata.related if metadata.related else []

            note_info = {
                "rel_path": rel_path.as_posix(),
                "title": metadata.title,
                "description": metadata.description,
                "note_type": metadata.type,
                "tags": tags,
                "timestamp": ts,
                "filename": filepath.name,
                "owner": owner,
                "status": status,
                "expiry": expiry,
                "related": related,
            }

            if top_folder not in folder_notes:
                folder_notes[top_folder] = []
            folder_notes[top_folder].append(note_info)
        except Exception:  # noqa: S112
            continue

    return folder_notes


def _note_info_from_metadata(filepath: Path, vault_dir: Path, metadata: OKFMetadata) -> dict:
    """Build the catalog representation shared by full and incremental scans."""
    rel_path = filepath.relative_to(vault_dir)
    return {
        "rel_path": rel_path.as_posix(),
        "title": metadata.title,
        "description": metadata.description,
        "note_type": metadata.type,
        "tags": metadata.tags if metadata.tags else [],
        "timestamp": metadata.timestamp.isoformat() if metadata.timestamp else "",
        "filename": filepath.name,
        "owner": metadata.owner if metadata.owner else "",
        "status": metadata.status if metadata.status else "",
        "expiry": metadata.expiry.isoformat() if metadata.expiry else "",
        "related": metadata.related if metadata.related else [],
    }


def _serialise_note_info(note: dict) -> dict:
    """Convert catalog metadata to JSON-safe cache data."""
    serialised = dict(note)
    serialised["related"] = [
        relation.model_dump(mode="json", exclude_none=True)
        if isinstance(relation, TypedRelation)
        else relation
        for relation in note.get("related", [])
    ]
    return serialised


def _deserialise_note_info(note: dict) -> dict:
    """Restore typed relations after loading the incremental catalog cache."""
    restored = dict(note)
    restored["rel_path"] = str(restored.get("rel_path", "")).replace("\\", "/")
    restored["related"] = [
        relation if isinstance(relation, TypedRelation) else TypedRelation.model_validate(relation)
        for relation in note.get("related", [])
    ]
    return restored


def _ancestor_dirs(rel_path: Path) -> list[str]:
    """Return the note's catalog directory and all indexed ancestors."""
    if not rel_path.parts or rel_path.parts[0] not in INDEX_FOLDERS:
        return []
    parent = rel_path.parent
    if str(parent) == ".":
        return []
    parts = parent.parts
    return ["/".join(parts[:index]) for index in range(len(parts), 0, -1)]


def _scan_folder_notes_incremental(
    vault_dir: Path,
) -> tuple[
    dict[str, list[dict]],
    list[tuple[str, str]],
    int,
    set[str],
    dict[str, list[dict]],
    bool,
]:
    """Scan notes and identify exact catalog directories affected by changes.

    The cache lives outside the Markdown vault content under POWER's stable
    per-vault cache namespace. File size and nanosecond mtime form the cheap
    change detector; a cache miss always re-reads and validates the note. The
    renderer version is part of the cache contract so a catalog-format change
    invalidates every folder exactly once.
    """
    cache_path = vault_cache_dir(vault_dir) / "hierarchical-index-cache.json"
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    except (OSError, ValueError, TypeError):
        cached = {}
    cache_is_current = (
        isinstance(cached, dict)
        and cached.get("schema_version") == INDEX_CACHE_SCHEMA_VERSION
        and cached.get("renderer_version") == INDEX_RENDERER_VERSION
    )
    cached_entries = cached.get("entries", {}) if cache_is_current else {}
    if not isinstance(cached_entries, dict):
        cached_entries = {}

    folder_notes: dict[str, list[dict]] = {}
    directory_notes: dict[str, list[dict]] = {}
    invalid_notes: list[tuple[str, str]] = []
    next_entries: dict[str, dict] = {}
    changed_dirs: set[str] = set()
    seen_paths: set[str] = set()
    for filepath in sorted(iter_vault_markdown_files(vault_dir)):
        if filepath.name in {"index.md", "log.md"} or is_catalog_filename(filepath.name):
            continue
        rel_path = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, rel_path.as_posix()) or not rel_path.parts:
            continue
        top_folder = rel_path.parts[0]
        if top_folder not in INDEX_FOLDERS:
            continue
        rel_path_str = rel_path.as_posix()
        seen_paths.add(rel_path_str)

        try:
            stat = filepath.stat()
            signature = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
        except OSError:
            changed_dirs.update(_ancestor_dirs(rel_path))
            invalid_notes.append((rel_path.as_posix(), "read_error"))
            continue

        cached_entry = cached_entries.get(rel_path_str)
        if (
            isinstance(cached_entry, dict)
            and cached_entry.get("signature") == signature
            and isinstance(cached_entry.get("note"), dict)
        ):
            note_info = _deserialise_note_info(cached_entry["note"])
            if cached_entry.get("valid", False):
                folder_notes.setdefault(top_folder, []).append(note_info)
                directory = "/".join(rel_path.parts[:-1])
                directory_notes.setdefault(directory, []).append(note_info)
            else:
                invalid_notes.append(
                    (rel_path.as_posix(), str(cached_entry.get("reason", "invalid_metadata")))
                )
            next_entries[rel_path.as_posix()] = {
                **cached_entry,
                "note": _serialise_note_info(note_info),
            }
            continue

        changed_dirs.update(_ancestor_dirs(rel_path))

        try:
            metadata = validate_metadata(read_file_content(filepath))
        except (OSError, UnicodeError):
            metadata = None
        if metadata is None:
            reason = "Invalid OKF metadata"
            invalid_notes.append((rel_path.as_posix(), reason))
            next_entries[rel_path.as_posix()] = {
                "signature": signature,
                "valid": False,
                "reason": reason,
                "note": {},
            }
            continue

        note_info = _note_info_from_metadata(filepath, vault_dir, metadata)
        folder_notes.setdefault(top_folder, []).append(note_info)
        directory = "/".join(rel_path.parts[:-1])
        directory_notes.setdefault(directory, []).append(note_info)
        next_entries[rel_path.as_posix()] = {
            "signature": signature,
            "valid": True,
            "note": _serialise_note_info(note_info),
        }

    # A deleted note is not visited above. Mark its former directory and all
    # ancestors so stale rows and descendant counts are removed on this run.
    for cached_path in cached_entries:
        if cached_path in seen_paths:
            continue
        changed_dirs.update(_ancestor_dirs(Path(cached_path)))

    atomic_write(
        cache_path,
        json.dumps(
            {
                "schema_version": INDEX_CACHE_SCHEMA_VERSION,
                "renderer_version": INDEX_RENDERER_VERSION,
                "entries": next_entries,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
    )
    return (
        folder_notes,
        invalid_notes,
        len(next_entries),
        changed_dirs,
        directory_notes,
        not cache_is_current,
    )


def scan_folder_notes_incremental(
    vault_dir: Path,
) -> tuple[dict[str, list[dict]], list[tuple[str, str]], int]:
    """Scan changed notes and reuse validated metadata for unchanged notes.

    Keep the historical three-value return shape for callers outside the
    hierarchical generator; the internal helper additionally reports the
    folders whose rendered indexes are stale.
    """
    folder_notes, invalid_notes, entry_count, _, _, _ = _scan_folder_notes_incremental(vault_dir)
    return folder_notes, invalid_notes, entry_count


def scan_root_daily_logs(vault_dir: Path) -> list[dict]:
    """Collect valid root-level daily logs for direct root-index navigation."""
    root_logs: list[dict] = []
    for filepath in vault_dir.glob("*.md"):
        rel_path = filepath.relative_to(vault_dir)
        if filepath.name in {"index.md", "log.md"} or is_catalog_filename(filepath.name):
            continue
        if len(rel_path.parts) != 1 or should_skip(vault_dir, rel_path.as_posix()):
            continue

        try:
            content = read_file_content(filepath)
            metadata: OKFMetadata | None = validate_metadata(content)
            if metadata is None:
                continue
            root_logs.append(
                {
                    "rel_path": rel_path.as_posix(),
                    "title": metadata.title,
                    "description": metadata.description,
                }
            )
        except Exception:  # noqa: S112
            continue
    return sorted(root_logs, key=lambda note: note["rel_path"])


def generate_index_content(concepts: dict[str, list[tuple[str, str, str]]]) -> str:
    """Generate the full index.md content from scanned concepts (flat, legacy)."""
    lines = [
        "---",
        "type: System Guide",
        'title: "Second Brain Index"',
        'description: "Registry of all concepts in the Second Brain"',
        f"timestamp: {datetime.now(UTC).isoformat()}",
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
            lines.append(f"- **[{title}]({rel_path})** - {truncate_for_catalog(desc)}")
        lines.append("")

    return "\n".join(lines)


def generate_main_index_content(
    folder_notes: dict[str, list[dict]], root_daily_logs: list[dict] | None = None
) -> str:
    """Generate the root index.md as a navigation map linking to sub-indexes."""
    lines = [
        "---",
        "type: System Guide",
        'title: "Second Brain Index"',
        'description: "Hierarchical navigation map for the knowledge vault"',
        f"timestamp: {datetime.now(UTC).isoformat()}",
        "---",
        "",
        "# Knowledge Catalog",
        "",
        "This file is automatically maintained by AI agents.",
        "Use sub-index links to explore detailed entries per category.",
        "",
        "## Navigation Map",
        "",
        "| Category | Notes | Sub-Index |",
        "|----------|-------|-----------|",
    ]

    for folder in INDEX_FOLDERS:
        notes = folder_notes.get(folder, [])
        count = len(notes)
        sub_index_link = f"[_index.md]({folder}/_index.md)"
        display_name = folder.replace("_", " ")
        lines.append(f"| {display_name} | {count} | {sub_index_link} |")

    if root_daily_logs:
        lines.extend(["", "## Root Daily Logs", ""])
        lines.extend(
            [
                f"- [{note['title']}]({note['rel_path']}) — "
                f"{truncate_for_catalog(note['description'])}"
                for note in root_daily_logs
            ]
        )

    lines.append("")
    lines.append("## Agent Protocol")
    lines.append("")
    lines.append("1. **Read this file** — identify the relevant category.")
    lines.append("2. **Read the sub-index** — load `folder/_index.md` for detailed entries.")
    lines.append("3. **Read specific notes** — only when the sub-index indicates relevance.")
    lines.append("4. **NEVER glob all `.md` files** — use sub-indexes as a map.")
    lines.append("")

    return "\n".join(lines)


def _catalog_link(folder: str, rel_path: str) -> str:
    """Render a vault-relative path as an explicit relative Markdown link."""
    normalized = rel_path.replace("\\", "/")
    target = posixpath.relpath(normalized, folder)
    if not target.startswith((".", "/")):
        target = f"./{target}"
    return f"[{normalized}](<{target}>)"


def _catalog_page_filename(page: int) -> str:
    """Return the stable filename for a one-based catalog page."""
    return "_index.md" if page == 1 else f"_index-{page}.md"


def _catalog_header(folder: str, page: int, page_count: int) -> list[str]:
    """Build the machine-readable header shared by every catalog page."""
    display_name = folder.replace("_", " ")
    return [
        "---",
        "type: System Guide",
        f"title: {json.dumps(f'{display_name} Sub-Index', ensure_ascii=False)}",
        f"description: {json.dumps(f'Detailed catalog of all notes in {display_name}', ensure_ascii=False)}",
        f"timestamp: {datetime.now(UTC).isoformat()}",
        CATALOG_MARKER,
        f"x-index-renderer: {INDEX_RENDERER_VERSION}",
        f"x-index-directory: {json.dumps(folder)}",
        f"x-index-page: {page}",
        f"x-index-pages: {page_count}",
        "---",
        "",
    ]


def _catalog_navigation(folder: str, page: int, page_count: int) -> list[str]:
    """Build page and parent navigation without linking outside the vault scope."""
    links: list[str] = []
    if page > 1:
        links.append(f"[Previous](<./{_catalog_page_filename(page - 1)}>)")
    links.append(f"Page {page} of {page_count}")
    if page < page_count:
        links.append(f"[Next](<./{_catalog_page_filename(page + 1)}>)")

    lines = [" | ".join(links)]
    parent = Path(folder).parent.as_posix()
    if parent != ".":
        lines.append("[Parent catalog](<../_index.md>)")
    lines.append("")
    return lines


def _note_catalog_block(folder: str, note: dict) -> str:
    """Render one note entry, including a link that resolves from its catalog."""
    lines = [
        f"## {note['title']}",
        f"- **Path:** {_catalog_link(folder, note['rel_path'])}",
        f"- **Type:** {note['note_type']}",
        f"- **Description:** {truncate_for_catalog(note['description'])}",
    ]
    if note.get("tags"):
        tags_str = ", ".join(note["tags"])
        lines.append(f"- **Tags:** [{tags_str}]")
    if note.get("owner"):
        lines.append(f"- **Owner:** {note['owner']}")
    if note.get("status"):
        lines.append(f"- **Status:** {note['status']}")
    if note.get("expiry"):
        lines.append(f"- **Review by:** {note['expiry']}")
    if note.get("related"):
        rel_str = ", ".join(r.path for r in note["related"])
        lines.append(f"- **Related:** {rel_str}")
    if note.get("timestamp"):
        lines.append(f"- **Updated:** {note['timestamp'][:10]}")
    return "\n".join(lines) + "\n"


def _child_catalog_block(folder: str, child: str, note_count: int) -> str:
    """Render one nested-directory entry for its parent catalog."""
    child_name = Path(child).name.replace("_", " ")
    child_path = f"{child}/_index.md"
    return "\n".join(
        [
            f"## {child_name}",
            f"- **Folder:** {_catalog_link(folder, child_path)}",
            f"- **Notes:** {note_count}",
            "",
        ]
    )


def _catalog_blocks(
    folder: str,
    notes: list[dict],
    child_dirs: list[str],
    note_counts: dict[str, int],
) -> list[str]:
    """Build deterministic, independently paginable directory entries."""
    blocks = [
        _child_catalog_block(folder, child, note_counts.get(child, 0))
        for child in sorted(child_dirs)
    ]
    blocks.extend(
        _note_catalog_block(folder, note)
        for note in sorted(notes, key=lambda item: (item["title"].casefold(), item["rel_path"]))
    )
    return blocks


def _render_catalog_page(folder: str, blocks: list[str], page: int, page_count: int) -> str:
    """Render one catalog page from already partitioned entry blocks."""
    display_name = folder.replace("_", " ")
    lines = _catalog_header(folder, page, page_count)
    lines.append(f"# {display_name} — Detailed Index")
    lines.append("")
    lines.extend(_catalog_navigation(folder, page, page_count))
    if blocks:
        lines.extend(blocks)
    else:
        lines.append("_No notes or nested folders in this category yet._")
        lines.append("")
    return "\n".join(lines)


def _generate_catalog_pages(
    folder: str,
    notes: list[dict],
    child_dirs: list[str] | None = None,
    note_counts: dict[str, int] | None = None,
    max_bytes: int | None = None,
) -> dict[str, str]:
    """Render a directory catalog into deterministic UTF-8-bounded pages."""
    if max_bytes is None:
        max_bytes = INDEX_MAX_BYTES
    if max_bytes <= 0:
        raise ValueError("INDEX_MAX_BYTES must be positive")

    blocks = _catalog_blocks(folder, notes, child_dirs or [], note_counts or {})
    pages: list[list[str]] = []
    if not blocks:
        pages.append([])
    else:
        # Upper bound for navigation overhead. The page number must be both
        # greater than 1 and less than the page count, otherwise the probe drops
        # the "Previous" or "Next" link that a real middle page carries and the
        # bound is short by the width of a whole element -- wider page *numbers*
        # do not compensate for a missing *link*.
        page_hint = len(blocks)
        count_hint = page_hint + 1
        current: list[str] = []
        for block in blocks:
            candidate = [*current, block]
            rendered = _render_catalog_page(folder, candidate, page_hint, count_hint)
            if len(rendered.encode("utf-8")) <= max_bytes:
                current = candidate
                continue
            if not current:
                raise ValueError(
                    f"catalog_entry_exceeds_limit:{folder}:{len(block.encode('utf-8'))}"
                )
            pages.append(current)
            current = [block]
            single = _render_catalog_page(folder, current, page_hint, count_hint)
            if len(single.encode("utf-8")) > max_bytes:
                raise ValueError(
                    f"catalog_entry_exceeds_limit:{folder}:{len(block.encode('utf-8'))}"
                )
        if current:
            pages.append(current)

    page_count = len(pages)
    rendered_pages = {
        _catalog_page_filename(page): _render_catalog_page(folder, page_blocks, page, page_count)
        for page, page_blocks in enumerate(pages, start=1)
    }
    oversized = [
        (filename, len(content.encode("utf-8")))
        for filename, content in rendered_pages.items()
        if len(content.encode("utf-8")) > max_bytes
    ]
    if oversized:
        filename, size = oversized[0]
        raise ValueError(f"catalog_page_exceeds_limit:{folder}/{filename}:{size}")
    return rendered_pages


def generate_sub_index_content(folder: str, notes: list[dict]) -> str:
    """Generate the first bounded page of a directory catalog.

    The two-argument signature remains stable for library and MCP callers.
    Hierarchical generation adds nested-directory entries through the internal
    paginated renderer.
    """
    return _generate_catalog_pages(folder, notes)["_index.md"]


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
    normalized_folder = Path(folder).as_posix()
    folder_notes = scan_folder_notes(vault_dir)
    directory_notes = _directory_notes_from_folder_notes(folder_notes)
    desired_dirs = _desired_catalog_dirs(directory_notes)
    children = _catalog_children(desired_dirs)
    counts = _catalog_note_counts(directory_notes)
    notes = (
        folder_notes.get(normalized_folder, [])
        if normalized_folder in INDEX_FOLDERS
        else directory_notes.get(normalized_folder, [])
    )
    pages = _generate_catalog_pages(
        normalized_folder,
        notes,
        children.get(normalized_folder, []),
        counts,
    )
    conflicts: list[str] = []
    _write_catalog_pages(vault_dir, normalized_folder, pages, conflicts)
    result = f"Generated {normalized_folder}/_index.md with {len(notes)} entries."
    if conflicts:
        result += "\nWARNING: catalog conflicts preserved:\n" + "\n".join(
            f"  - {path}" for path in conflicts
        )
    return result


def _directory_notes_from_folder_notes(
    folder_notes: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Group top-level scan results by the exact directory containing each note."""
    directory_notes: dict[str, list[dict]] = {}
    for notes in folder_notes.values():
        for note in notes:
            directory = Path(note["rel_path"]).parent.as_posix()
            directory_notes.setdefault(directory, []).append(note)
    return directory_notes


def _desired_catalog_dirs(directory_notes: dict[str, list[dict]]) -> set[str]:
    """Return top-level catalog roots plus every indexed note ancestor."""
    desired = set(INDEX_FOLDERS)
    for directory in directory_notes:
        desired.update(_ancestor_dirs(Path(directory) / "_note.md"))
    return desired


def _catalog_children(desired_dirs: set[str]) -> dict[str, list[str]]:
    """Build an immediate-child map for recursive catalog navigation."""
    children: dict[str, list[str]] = {directory: [] for directory in desired_dirs}
    for directory in desired_dirs:
        parent = Path(directory).parent.as_posix()
        if parent in children:
            children[parent].append(directory)
    return children


def _catalog_note_counts(directory_notes: dict[str, list[dict]]) -> dict[str, int]:
    """Count direct and descendant notes for every catalog directory."""
    counts: dict[str, int] = dict.fromkeys(INDEX_FOLDERS, 0)
    for directory, notes in directory_notes.items():
        for ancestor in _ancestor_dirs(Path(directory) / "_note.md"):
            counts[ancestor] = counts.get(ancestor, 0) + len(notes)
    return counts


def _existing_catalog_dirs(vault_dir: Path) -> set[str]:
    """Find existing generated-catalog directories inside indexed roots."""
    directories: set[str] = set()
    for filepath in iter_vault_markdown_files(vault_dir):
        if not is_catalog_filename(filepath.name):
            continue
        rel_path = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, rel_path.as_posix()) or not rel_path.parts:
            continue
        if rel_path.parts[0] in INDEX_FOLDERS:
            directories.add(rel_path.parent.as_posix())
    return directories


def _catalog_files(vault_dir: Path, folder: str) -> list[Path]:
    """Return generated-page-shaped files in one catalog directory."""
    directory = vault_dir / Path(folder)
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob("_index*.md")
        if is_catalog_filename(path.name) and is_regular_vault_file(vault_dir, path)
    )


def _is_owned_catalog(path: Path, vault_dir: Path) -> bool:
    """Recognize POWER catalogs without taking ownership of foreign files."""
    if not path.exists():
        return False
    relative_dir = path.parent.relative_to(vault_dir).as_posix()
    try:
        prefix = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return False
    if CATALOG_MARKER in prefix:
        return True
    # v1 catalogs had no marker. Upgrade only the exact POWER-generated
    # frontmatter shape; an unmarked hand-maintained top-level catalog must be
    # preserved and reported as a conflict.
    if path.name == "_index.md" and relative_dir in INDEX_FOLDERS:
        display_name = relative_dir.replace("_", " ")
        return (
            f'title: "{display_name} Sub-Index"' in prefix
            and f'description: "Detailed catalog of all notes in {display_name}"' in prefix
        )
    return False


def _catalog_is_current(path: Path, vault_dir: Path) -> bool:
    """Return whether a catalog landing page and all declared pages are current."""
    if not _is_owned_catalog(path, vault_dir):
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return False
    if f"x-index-renderer: {INDEX_RENDERER_VERSION}" not in content:
        return False
    page_line = next(
        (line for line in content.splitlines() if line.startswith("x-index-pages:")),
        "",
    )
    try:
        page_count = int(page_line.split(":", 1)[1].strip())
    except (IndexError, ValueError):
        return False
    folder = path.parent.relative_to(vault_dir).as_posix()
    expected = {
        vault_dir / folder / _catalog_page_filename(page) for page in range(1, page_count + 1)
    }
    existing = set(_catalog_files(vault_dir, folder))
    return existing == expected and all(
        (vault_dir / folder / _catalog_page_filename(page)).exists()
        and _is_owned_catalog(vault_dir / folder / _catalog_page_filename(page), vault_dir)
        for page in range(1, page_count + 1)
    )


def _write_catalog_pages(
    vault_dir: Path, folder: str, pages: dict[str, str], conflicts: list[str]
) -> bool:
    """Atomically write owned pages and remove obsolete owned pagination files."""
    directory = vault_dir / Path(folder)
    directory.mkdir(parents=True, exist_ok=True)
    existing = _catalog_files(vault_dir, folder)
    expected = {directory / filename for filename in pages}
    blocking = [
        path
        for path in [*expected, *existing]
        if path.exists() and path not in expected and not _is_owned_catalog(path, vault_dir)
    ]
    blocking.extend(
        path for path in expected if path.exists() and not _is_owned_catalog(path, vault_dir)
    )
    if blocking:
        conflicts.extend(sorted({path.relative_to(vault_dir).as_posix() for path in blocking}))
        return False

    for filename, content in pages.items():
        atomic_write(directory / filename, content)
    for path in existing:
        if path not in expected and _is_owned_catalog(path, vault_dir):
            path.unlink()
    return True


def _remove_stale_catalog_dir(vault_dir: Path, folder: str, conflicts: list[str]) -> None:
    """Remove only POWER-owned pages from a directory no longer in the index."""
    for path in _catalog_files(vault_dir, folder):
        if _is_owned_catalog(path, vault_dir):
            path.unlink()
        else:
            conflicts.append(path.relative_to(vault_dir).as_posix())


def run_generate_hierarchical_index(vault_dir: Path) -> str:
    """
    Generate hierarchical index: root index.md + per-folder _index.md files.

    Returns a summary message.
    """
    (
        folder_notes,
        invalid_notes,
        _,
        changed_dirs,
        directory_notes,
        force_render,
    ) = _scan_folder_notes_incremental(vault_dir)
    root_daily_logs = scan_root_daily_logs(vault_dir)
    desired_dirs = _desired_catalog_dirs(directory_notes)
    children = _catalog_children(desired_dirs)
    note_counts = _catalog_note_counts(directory_notes)
    existing_dirs = _existing_catalog_dirs(vault_dir)
    conflicts: list[str] = []

    for stale_dir in sorted(existing_dirs - desired_dirs, key=lambda item: (item.count("/"), item)):
        _remove_stale_catalog_dir(vault_dir, stale_dir, conflicts)

    total_notes = sum(len(notes) for notes in folder_notes.values()) + len(root_daily_logs)

    main_index_path = vault_dir / "index.md"
    main_content = generate_main_index_content(folder_notes, root_daily_logs)
    atomic_write(main_index_path, main_content)

    generated_pages = 0
    written_catalogs: set[str] = set()
    try:
        for folder in sorted(desired_dirs, key=lambda item: (item.count("/"), item)):
            landing = vault_dir / folder / "_index.md"
            if (
                force_render
                or folder in changed_dirs
                or not _catalog_is_current(landing, vault_dir)
            ):
                notes = (
                    folder_notes.get(folder, [])
                    if folder in INDEX_FOLDERS
                    else directory_notes.get(folder, [])
                )
                pages = _generate_catalog_pages(
                    folder,
                    notes,
                    children.get(folder, []),
                    note_counts,
                )
                if _write_catalog_pages(vault_dir, folder, pages, conflicts):
                    generated_pages += len(pages)
                    written_catalogs.add(folder)
    except Exception:
        # The scan cache is written before rendering for incremental callers.
        # Never let a failed render make the next run believe the old catalog
        # is current; the next invocation will perform a safe full rebuild.
        cache_path = vault_cache_dir(vault_dir) / "hierarchical-index-cache.json"
        with suppress(FileNotFoundError):
            cache_path.unlink()
        raise

    sub_index_results = ["  index.md (navigation map)"]
    for folder in INDEX_FOLDERS:
        landing = vault_dir / folder / "_index.md"
        note_count = len(folder_notes.get(folder, []))
        available = folder in written_catalogs or _catalog_is_current(landing, vault_dir)
        suffix = f"({note_count} notes)" if available else f"NOT WRITTEN ({note_count} notes)"
        sub_index_results.append(f"  {folder}/_index.md {suffix}")
    sub_index_results.append(f"  generated catalog pages: {generated_pages}")

    lines = [
        f"Generated hierarchical index with {total_notes} total notes:",
    ]
    if invalid_notes:
        lines.append(f"WARNING: skipped invalid notes ({len(invalid_notes)}):")
        lines.extend(f"  - {path}: {reason}" for path, reason in sorted(invalid_notes))
    if conflicts:
        lines.append(f"WARNING: catalog conflicts preserved ({len(set(conflicts))}):")
        lines.extend(f"  - {path}" for path in sorted(set(conflicts)))
    lines.extend(sub_index_results)

    return "\n".join(lines)


def generate_log_initial(vault_dir: Path, note_count: int) -> None:
    """Generate initial log.md if it doesn't exist."""
    log_path = vault_dir / "log.md"
    if log_path.exists():
        return

    timestamp = datetime.now(UTC).isoformat()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
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
