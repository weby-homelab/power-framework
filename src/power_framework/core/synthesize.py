"""POWER 3.0 Phase 3 — synthesize_session auto-ingest (core entry point).

Extracts the session-synthesis logic previously only available inside the MCP
server into a reusable, framework-agnostic core function so it can be invoked:

  * from the CLI (``power synthesize``),
  * programmatically after an agent session (the Auto-Ingest Feedback Loop),
  * and still by the MCP ``synthesize_session`` tool (which now delegates here).

Every synthesized note gets auto-classified OKF frontmatter, Graph-RAG related
links, atomic write, hierarchical-index regeneration, log append, and a lint
report — exactly mirroring the MCP behavior.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .indexer import run_generate_hierarchical_index
from .linter import run_lint_report
from .models import NoteType, OKFMetadata, TypedRelation
from .parser import build_frontmatter
from .utils import atomic_write

if TYPE_CHECKING:
    from zoneinfo import ZoneInfo

_DEFAULT_TZ = datetime.timezone.utc


def synthesize_session_ingest(
    name: str,
    title: str,
    description: str,
    content: str,
    note_type: str = "Daily Log",
    tags: list[str] | None = None,
    related: list[str] | None = None,
    owner: str | None = None,
    vault_path: str | str | Path = ".",
    timestamp: datetime.datetime | None = None,
) -> str:
    """Create a session synthesis note with auto-classified OKF metadata + ingest.

    Returns a human-readable report (saved path, index result, lint result).
    Raises ``FileExistsError`` if the note already exists.
    """
    vault = Path(vault_path).expanduser().resolve()
    tags = tags or []
    related_typed = [TypedRelation(path=r) for r in (related or [])]

    if not name.endswith(".md"):
        name += ".md"

    target_file = vault / name
    if target_file.exists():
        raise FileExistsError(f"Note already exists at {name}")

    ts = timestamp or datetime.datetime.now(_DEFAULT_TZ)
    metadata = OKFMetadata(
        type=NoteType(note_type),
        title=title,
        description=description,
        tags=tags,
        related=related_typed,
        owner=owner,
        timestamp=ts,
    )

    frontmatter = build_frontmatter(metadata)
    full_content = f"{frontmatter}\n\n{content}\n"

    target_file.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target_file, full_content)

    index_result = run_generate_hierarchical_index(vault)

    log_file = vault / "log.md"
    if log_file.exists():
        date_str = ts.strftime("%Y-%m-%d")
        log_entry = (
            f"\n## [{date_str}] synthesize | {title}\n"
            f"- **Action:** Created session note '{name}' of type {note_type}.\n"
            f"- **Related:** {', '.join(related) if related else 'none'}\n"
            f"- **Owner:** {owner or 'unassigned'}\n"
            f"- **Result:** Saved to {name} and compiled hierarchical index.\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

    lint_result = run_lint_report(vault)

    return (
        f"Session note '{name}' has been synthesized and ingested!\n"
        f"{index_result}\n"
        f"Action appended to log.md.\n\n"
        f"Linting Check:\n{lint_result}"
    )
