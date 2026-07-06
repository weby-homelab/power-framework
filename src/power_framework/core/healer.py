"""
P.O.W.E.R. Frontmatter Healer.

Auto-heals missing or invalid OKF frontmatter fields:
  - Title from filename (if missing)
  - Description from first content paragraph (if missing)
  - Timestamp (if missing, added with current UTC time)
  - Type from parent folder (if missing)
  - Type casing/cleanup (if invalid)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from .models import NoteType
from .parser import (
    FRONTMATTER_PATTERN,
    extract_frontmatter_raw,
    parse_frontmatter,
    read_file_content,
)
from .utils import atomic_write, create_backup

FOLDER_TO_TYPE: dict[str, str] = {
    "01_Projects": "Project",
    "02_Areas": "Area",
    "03_Resources": "Resource",
    "04_Archive": "Archive",
    "06_Daily_Logs": "Daily Log",
    "PROTOCOLS": "System Guide",
}

DEFAULT_EXCLUDED = frozenset(
    {
        "index.md",
        "log.md",
        "_index.md",
        ".git",
        ".backups",
        "05_Templates",
        "scratch",
        ".system_generated",
        ".agents",
    }
)


def _infer_title_from_filename(filepath: Path) -> str:
    """Convert filename (kebab/snake) to Title Case, stripping date prefixes."""
    stem = filepath.stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[\s_-]*", "", stem)
    stem = re.sub(r"[-_]+", " ", stem)
    words = [w.capitalize() for w in stem.split() if w.strip()]
    return " ".join(words) if words else stem


def _infer_type_from_folder(filepath: Path, vault_dir: Path) -> str | None:
    """Infer note type from the parent P.A.R.A. folder."""
    try:
        rel = filepath.resolve().relative_to(vault_dir.resolve())
    except ValueError:
        return None
    top = rel.parts[0]
    return FOLDER_TO_TYPE.get(top)


def _extract_first_paragraph(content: str) -> str:
    """Extract first non-empty, non-header paragraph after frontmatter."""
    body = content
    if content.startswith("---"):
        match = FRONTMATTER_PATTERN.match(content)
        if match:
            body = content[match.end() :]
    for line in body.strip().split("\n"):
        line = line.strip()
        if (
            line
            and not line.startswith("#")
            and not line.startswith("![")
            and not line.startswith("```")
        ):
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                return clean[:150]
    return ""


def _escape_yaml(value: str) -> str:
    """Escape double quotes and backslashes for YAML."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_frontmatter(
    fm_data: dict,
    note_type: str | None,
    title: str | None,
    description: str | None,
    timestamp: datetime | None,
) -> str:
    """Build healed frontmatter string, preserving existing optional fields."""
    parts = ["---"]
    if note_type:
        parts.append(f"type: {note_type}")
    if title:
        parts.append(f'title: "{_escape_yaml(title)}"')
    if description:
        parts.append(f'description: "{_escape_yaml(description)}"')
    for field in ("resource", "tags", "owner", "status", "expiry", "related"):
        val = fm_data.get(field)
        if val is not None and val != "" and val != []:
            if isinstance(val, list):
                items = ", ".join(str(v) for v in val)
                parts.append(f"{field}: [{items}]")
            elif isinstance(val, bool):
                parts.append(f"{field}: {str(val).lower()}")
            else:
                parts.append(f'{field}: "{_escape_yaml(str(val))}"')
    if timestamp:
        ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        parts.append(f"timestamp: {ts_str}")
    parts.append("---")
    return "\n".join(parts)


def heal_frontmatter(
    content: str,
    filepath: Path,
    vault_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """
    Heal missing or invalid OKF frontmatter fields.

    Returns (healed_content, list_of_changes).
    Returns original content with empty changes list if nothing to heal.
    """
    changes: list[str] = []
    raw_fm = extract_frontmatter_raw(content)
    had_no_fm = raw_fm is None
    fm_data: dict = {}

    if had_no_fm:
        changes.append("No frontmatter found — created minimal frontmatter")
    else:
        fm_data = parse_frontmatter(content) or {}

    note_type: str | None = fm_data.get("type")
    title: str | None = fm_data.get("title")
    description: str | None = fm_data.get("description")
    timestamp: datetime | None = fm_data.get("timestamp")

    if note_type:
        valid_types = {t.value.lower(): t.value for t in NoteType}
        tl = str(note_type).strip().lower()
        if tl in valid_types and str(note_type) != valid_types[tl]:
            changes.append(f"Fixed type casing: '{note_type}' → '{valid_types[tl]}'")
            note_type = valid_types[tl]

    if not note_type and vault_dir:
        inferred = _infer_type_from_folder(filepath, vault_dir)
        if inferred:
            changes.append(f"Added missing type: {inferred}")
            note_type = inferred

    if not title:
        inferred = _infer_title_from_filename(filepath)
        if inferred:
            changes.append(f"Added missing title: '{inferred}'")
            title = inferred

    if not description:
        inferred = _extract_first_paragraph(content)
        if inferred:
            changes.append(f"Added missing description: '{inferred[:60]}...'")
            description = inferred

    if not timestamp:
        timestamp = datetime.now(timezone.utc)
        changes.append("Added missing timestamp")

    if not changes:
        return content, []

    new_fm = _format_frontmatter(fm_data, note_type, title, description, timestamp)

    if raw_fm is not None:
        healed = re.sub(
            r"^---.*?\n---\n?",
            new_fm + "\n",
            content,
            count=1,
            flags=re.DOTALL,
        )
    else:
        healed = new_fm + "\n\n" + content

    return healed, changes


def heal_vault(vault_dir: Path, dry_run: bool = True) -> str:
    """Scan vault and heal all notes with missing/invalid frontmatter. Returns formatted report."""
    healed_count = 0
    changes_log: list[str] = []

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if any(part in DEFAULT_EXCLUDED for part in rel.parts):
            continue
        if filepath.name in DEFAULT_EXCLUDED:
            continue

        try:
            content = read_file_content(filepath)
        except Exception:
            logging.exception("Failed to read %s", filepath)
            continue
        if not content.strip():
            continue

        healed, changes = heal_frontmatter(content, filepath, vault_dir)
        if not changes:
            continue

        healed_count += 1
        if dry_run:
            changes_log.append(f"  {rel}:")
            changes_log.extend(f"    - {c}" for c in changes)
        else:
            backup_path = create_backup(filepath)
            atomic_write(filepath, healed)
            changes_log.append(f"  {rel}:")
            changes_log.extend(f"    - {c}" for c in changes)
            if backup_path:
                changes_log.append(f"    (backup: {backup_path.name})")

    lines = [
        "=== Frontmatter Heal Report ===",
        f"Vault: {vault_dir}",
        f"Mode: {'DRY RUN' if dry_run else 'LIVE'}",
        f"Notes healed: {healed_count}",
        "",
    ]
    if changes_log:
        lines.append("Changes:")
        lines.extend(changes_log)
        lines.append("")
    else:
        lines.append("No notes needed healing.")
        lines.append("")

    return "\n".join(lines)
