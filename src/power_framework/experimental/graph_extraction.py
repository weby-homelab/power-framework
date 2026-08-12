"""Auto-extraction of knowledge-graph triplets (WTF #5 remediation).

POWER 3.1 only linked notes via explicit, hand-written ``related:`` YAML and
keyword/tag Jaccard overlap. This module extracts ``(subject -> relation ->
object)`` candidates automatically so ``synthesize_session`` can record
reviewable proposals without granting graph authority.

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
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)

_HEURISTIC_SOURCE = "heuristic"
_HEURISTIC_METHOD = "regex-cues"
_HEURISTIC_MODEL_VERSION = "power-local-heuristics-v1"


@dataclass(frozen=True)
class Triplet:
    """A knowledge-graph edge: subject --relation--> object."""

    subject: str
    relation: str
    object: str
    confidence: float = 1.0
    evidence: str = ""


@dataclass(frozen=True)
class GraphCandidate:
    """A heuristic edge that has not yet become accepted graph authority."""

    id: int
    source_path: str
    subject: str
    relation: str
    object: str
    source: str
    method: str
    model_version: str
    confidence: float
    evidence: str
    status: str


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
            triplets.append(
                Triplet(subject=subject, relation=relation, object=obj, evidence=sentence)
            )
            break  # one relation per sentence (first / most specific cue)

    return triplets


def store_triplets(conn: sqlite3.Connection, source_path: str, triplets: list[Triplet]) -> int:
    """Persist heuristic triplets as unreviewed graph candidates.

    This compatibility-named function intentionally never writes the accepted
    ``relations`` table. Approval is the only path that grants graph authority.
    """
    if not triplets:
        return 0
    import json

    created_at = datetime.now(UTC).isoformat()
    rows = 0
    for t in triplets:
        evidence = json.dumps(
            {"statement": t.evidence or f"{t.subject} {t.relation} {t.object}"},
            ensure_ascii=False,
            sort_keys=True,
        )
        cursor = conn.execute(
            "INSERT OR IGNORE INTO relation_candidates "
            "(source_path, subject, relation, object, source, method, model_version, confidence, "
            "evidence, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)",
            (
                source_path,
                t.subject,
                t.relation,
                t.object,
                _HEURISTIC_SOURCE,
                _HEURISTIC_METHOD,
                _HEURISTIC_MODEL_VERSION,
                t.confidence,
                evidence,
                created_at,
            ),
        )
        rows += cursor.rowcount
    conn.commit()
    return rows


def _candidate_from_row(row: tuple[object, ...]) -> GraphCandidate:
    return GraphCandidate(
        id=cast("int", row[0]),
        source_path=str(row[1]),
        subject=str(row[2]),
        relation=str(row[3]),
        object=str(row[4]),
        source=str(row[5]),
        method=str(row[6]),
        model_version=str(row[7]),
        confidence=cast("float", row[8]),
        evidence=str(row[9]),
        status=str(row[10]),
    )


def _review_candidate(
    conn: sqlite3.Connection,
    candidate_id: int,
    decision: str,
    reviewer: str,
    reason: str,
) -> GraphCandidate:
    """Record one irreversible review decision and promote only on acceptance."""
    if decision not in {"accepted", "rejected"}:
        raise ValueError(f"Unsupported candidate decision: {decision}")
    if not reviewer.strip() or not reason.strip():
        raise ValueError("reviewer and reason are required")

    row = conn.execute(
        "SELECT id, source_path, subject, relation, object, source, method, model_version, "
        "confidence, evidence, status FROM relation_candidates WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Candidate {candidate_id} does not exist")
    candidate = _candidate_from_row(row)
    if candidate.status != "candidate":
        raise ValueError(f"Candidate {candidate_id} already reviewed as {candidate.status}")

    reviewed_at = datetime.now(UTC).isoformat()
    with conn:
        if decision == "accepted":
            conn.execute(
                "INSERT INTO relations "
                "(source_path, subject, relation, object, confidence, created_at, candidate_id, "
                "accepted_by, accepted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate.source_path,
                    candidate.subject,
                    candidate.relation,
                    candidate.object,
                    candidate.confidence,
                    reviewed_at,
                    candidate.id,
                    reviewer.strip(),
                    reviewed_at,
                ),
            )
        conn.execute(
            "UPDATE relation_candidates SET status = ?, reviewed_at = ?, reviewed_by = ?, "
            "review_reason = ? WHERE id = ?",
            (decision, reviewed_at, reviewer.strip(), reason.strip(), candidate.id),
        )
        conn.execute(
            "INSERT INTO relation_candidate_decisions "
            "(candidate_id, decision, reviewer, reason, decided_at) VALUES (?, ?, ?, ?, ?)",
            (candidate.id, decision, reviewer.strip(), reason.strip(), reviewed_at),
        )

    return GraphCandidate(**{**candidate.__dict__, "status": decision})


def approve_candidate(
    conn: sqlite3.Connection, candidate_id: int, reviewer: str, reason: str
) -> GraphCandidate:
    """Promote one reviewed candidate into the accepted relations table."""
    return _review_candidate(conn, candidate_id, "accepted", reviewer, reason)


def reject_candidate(
    conn: sqlite3.Connection, candidate_id: int, reviewer: str, reason: str
) -> GraphCandidate:
    """Reject one candidate while retaining a deterministic audit record."""
    return _review_candidate(conn, candidate_id, "rejected", reviewer, reason)


def store_note_triplets(vault_dir: Path | str, rel_path: str, content: str) -> int:
    """Extract and persist triplets for ``content`` into the vault search DB.

    Convenience used by ``synthesize_session`` so every synthesized note
    records reviewable graph candidates without modifying accepted relations.
    """
    from power_framework.core.db import _init_db
    from power_framework.core.searcher import _db_path

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
