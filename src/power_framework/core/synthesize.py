"""POWER 3.0 Phase 3 — synthesize_session auto-ingest (core entry point).

Extracts the session-synthesis logic previously only available inside the MCP
server into a reusable, framework-agnostic core function so it can be invoked:

  * from the CLI (``power synthesize``),
  * programmatically after an agent session (the Auto-Ingest Feedback Loop),
  * and still by the MCP ``synthesize_session`` tool (which now delegates here).

Every synthesized note gets auto-classified OKF frontmatter, hierarchical-index
regeneration, blocking lint, search publication, log append, and a receipt. The
optional Graph-RAG candidate projection runs after that core transaction.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from pathlib import Path

from .linter import run_lint_report
from .memory_api import commit_note_change
from .models import MemoryKind, MemoryMetadata, NoteType, OKFMetadata, TypedRelation, WritePolicy
from .parser import build_frontmatter
from .utils import resolve_path_in_vault

logger = logging.getLogger(__name__)

_DEFAULT_TZ = datetime.UTC


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
    related_typed = [
        TypedRelation.from_legacy_path(path)
        for relation in (related or [])
        if (path := relation.strip())
    ]

    if not name.endswith(".md"):
        name += ".md"

    target_file = resolve_path_in_vault(vault, name)
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
        okf_version="0.2",
        memory=MemoryMetadata(
            kind=MemoryKind.EPISODIC,
            sources=["power://synthesize_session"],
            evidence=[f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"],
            write_policy=WritePolicy.AGENT_PROPOSED,
        ),
        timestamp=ts,
    )

    frontmatter = build_frontmatter(metadata)
    full_content = f"{frontmatter}\n\n{content}\n"

    date_str = ts.strftime("%Y-%m-%d")
    log_entry = (
        f"\n## [{date_str}] synthesize | {title}\n"
        f"- **Action:** Created session note '{name}' of type {note_type}.\n"
        f"- **Related:** {', '.join(related) if related else 'none'}\n"
        f"- **Owner:** {owner or 'unassigned'}\n"
        f"- **Result:** Saved to {name} and compiled hierarchical index.\n"
    )
    receipt = commit_note_change(
        vault,
        name,
        full_content,
        require_absent=True,
        operation="synthesize.session",
        log_entry=log_entry,
    )

    # Graph extraction is deliberately an optional projection.  A failure here
    # must not invalidate the already verified Markdown/search transaction.
    try:
        from .graph_extraction import store_note_triplets

        store_note_triplets(vault, name, content)
    except Exception as exc:
        logger.warning("Triplet extraction failed for %s: %s", name, exc)

    lint_result = run_lint_report(vault)

    return (
        f"Session note '{name}' has been synthesized and ingested!\n"
        f"{receipt['index_summary']}\n"
        f"Search projection: {receipt['search_mode']} ({receipt['search_generation']})\n"
        f"Action appended to log.md when the log exists.\n\n"
        f"Linting Check:\n{lint_result}"
    )
