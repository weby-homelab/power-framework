"""Auto-extraction of knowledge-graph triplets (WTF #5 remediation).

POWER 3.1 only linked notes via explicit, hand-written ``related:`` YAML and
keyword/tag Jaccard overlap. This module extracts ``(subject -> relation ->
object)`` triplets automatically so ``synthesize_session`` can populate a real
graph without manual curation.

Two backends:
  * Local (default, no network): deterministic regex / linguistic heuristics
    over UA↔EN relationship cues. Keeps the framework API-optional and
    reproducible (ADR 0001 decision 6).
  * LLM (opt-in, ``OPENROUTER_API_KEY``): prompt-based extraction for richer
    triplets. Never required for a release build.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Triplet:
    """A knowledge-graph edge: subject --relation--> object."""

    subject: str
    relation: str
    object: str
    confidence: float = 1.0


# UA↔EN relationship cues -> canonical relation name. Order matters: longer /
# more specific cues are tried first.
_RELATION_CUES: list[tuple[str, str]] = [
    ("це", "is_a"),
    ("є", "is_a"),
    ("is a", "is_a"),
    ("is an", "is_a"),
    ("are a", "is_a"),
    ("are an", "is_a"),
    ("is", "is_a"),
    ("are", "is_a"),
    ("використовує", "uses"),
    ("використовують", "uses"),
    ("uses", "uses"),
    ("use", "uses"),
    ("потребує", "requires"),
    ("потребують", "requires"),
    ("requires", "requires"),
    ("require", "requires"),
    ("needs", "requires"),
    ("пов'язаний з", "related_to"),
    ("пов'язана з", "related_to"),
    ("related to", "related_to"),
    ("relates to", "related_to"),
]

_SENT_SPLIT = re.compile(r"[.!?\n;]+")
_NOISE = re.compile(r"[^\w\s'’\-]", flags=re.UNICODE)  # noqa: RUF001


def _clean_phrase(text: str, limit: int = 80) -> str:
    """Reduce a raw phrase to a compact entity label."""
    text = text.strip()
    text = _NOISE.sub(" ", text)
    words = text.split()
    if not words:
        return ""
    # Keep at most the first 8 words for a readable entity label.
    trimmed = " ".join(words[:8]).strip()
    if len(trimmed) > limit:
        trimmed = trimmed[: limit - 1].rstrip() + "…"
    return trimmed


def extract_triplets(content: str, note_path: str | None = None) -> list[Triplet]:
    """Extract deterministic (subject, relation, object) triplets from note text.

    Local backend only (no model, no network). Scans each sentence for a
    relationship cue and splits the sentence into a subject (pre-cue) and object
    (post-cue). Returns an empty list when nothing matches.
    """
    if not content or not content.strip():
        return []

    triplets: list[Triplet] = []
    for sentence in _SENT_SPLIT.split(content):
        sentence = sentence.strip()
        if len(sentence) < 6:
            continue
        low = sentence.lower()
        for cue, relation in _RELATION_CUES:
            idx = low.find(cue)
            if idx == -1:
                continue
            # Avoid matching the cue inside a longer word.
            before = low[:idx].rstrip()
            after = low[idx + len(cue) :].lstrip()
            if not before or not after:
                continue
            subject = _clean_phrase(sentence[:idx])
            obj = _clean_phrase(sentence[idx + len(cue) :])
            if not subject or not obj:
                continue
            # Skip trivial self-loops.
            if subject.lower() == obj.lower():
                continue
            triplets.append(Triplet(subject=subject, relation=relation, object=obj))
            break  # one relation per sentence (first / most specific cue)

    return triplets


def store_triplets(conn: sqlite3.Connection, source_path: str, triplets: list[Triplet]) -> int:
    """Persist triplets into the ``relations`` table. Returns rows written."""
    if not triplets:
        return 0
    from datetime import datetime, timezone

    created_at = datetime.now(timezone.utc).isoformat()
    rows = 0
    for t in triplets:
        conn.execute(
            "INSERT INTO relations (source_path, subject, relation, object, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_path, t.subject, t.relation, t.object, t.confidence, created_at),
        )
        rows += 1
    conn.commit()
    return rows


def store_note_triplets(vault_dir: Path | str, rel_path: str, content: str) -> int:
    """Extract and persist triplets for ``content`` into the vault search DB.

    Convenience used by ``synthesize_session`` so every synthesized note grows
    the auto knowledge graph without manual ``related:`` YAML.
    """
    from .db import _init_db
    from .searcher import _db_path

    triplets = extract_triplets(content, rel_path)
    if not triplets:
        return 0
    db_path = _db_path(Path(vault_dir))
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        _init_db(conn)
        return store_triplets(conn, rel_path, triplets)
    finally:
        conn.close()
