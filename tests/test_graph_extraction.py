"""Tests for local triplet extraction and persistence (WTF #5 remediation)."""

from __future__ import annotations

import sqlite3

import pytest

from power_framework.core.db import _init_db
from power_framework.core.graph_extraction import (
    Triplet,
    approve_candidate,
    extract_triplets,
    reject_candidate,
    store_note_triplets,
    store_triplets,
)


def test_extracts_ua_is_a_triplet():
    text = "POWER це AI-native Second Brain toolkit для знань."
    triplets = extract_triplets(text)
    assert triplets
    top = triplets[0]
    assert top.relation == "is_a"
    assert "POWER" in top.subject
    assert "AI-native" in top.object


def test_extracts_en_uses_triplet():
    text = "The reranker uses a cross-encoder to score documents."
    triplets = extract_triplets(text)
    assert any(t.relation == "uses" for t in triplets)


def test_no_triplet_when_no_cue():
    text = "Just a plain sentence without any relationship expressed here."
    assert extract_triplets(text) == []


def test_skips_trivial_self_loop():
    text = "Energy is energy."
    # subject and object are identical -> skipped.
    assert extract_triplets(text) == []


def test_store_triplets_persists_candidates_with_required_provenance(tmp_path):
    db = tmp_path / "search.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    triplets = [
        Triplet(subject="A", relation="uses", object="B"),
        Triplet(subject="A", relation="is_a", object="C"),
    ]
    written = store_triplets(conn, "note.md", triplets)
    assert written == 2
    rows = conn.execute(
        "SELECT source_path, subject, relation, object, source, method, model_version, "
        "confidence, evidence, status FROM relation_candidates ORDER BY id"
    ).fetchall()
    assert rows[0][:8] == (
        "note.md",
        "A",
        "uses",
        "B",
        "heuristic",
        "regex-cues",
        "power-local-heuristics-v1",
        1.0,
    )
    assert rows[0][8]
    assert rows[0][9] == "candidate"
    assert conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 0
    conn.close()


def test_store_note_triplets_extracts_and_persists(tmp_path, monkeypatch):
    db = tmp_path / "search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))
    # Pre-create the DB so store_note_triplets finds it.
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    conn.close()

    content = "SQLite це embedded database engine. The framework uses WAL mode."
    written = store_note_triplets(tmp_path, "01_Projects/Note.md", content)
    assert written >= 1

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT source_path, relation, status FROM relation_candidates WHERE source_path = ?",
        ("01_Projects/Note.md",),
    ).fetchall()
    conn.close()
    assert ("01_Projects/Note.md", "is_a", "candidate") in rows
    assert ("01_Projects/Note.md", "uses", "candidate") in rows


def test_candidate_review_is_deterministic_and_only_approval_creates_relation(tmp_path):
    db = tmp_path / "search.db"
    conn = sqlite3.connect(str(db))
    _init_db(conn)
    store_triplets(
        conn,
        "note.md",
        [
            Triplet(subject="A", relation="uses", object="B", evidence="A uses B."),
            Triplet(subject="A", relation="is_a", object="C", evidence="A is C."),
        ],
    )

    candidate_ids = [
        row[0] for row in conn.execute("SELECT id FROM relation_candidates ORDER BY id").fetchall()
    ]
    approved = approve_candidate(conn, candidate_ids[0], reviewer="human", reason="verified")
    rejected = reject_candidate(conn, candidate_ids[1], reviewer="human", reason="irrelevant")

    assert approved.status == "accepted"
    assert rejected.status == "rejected"
    assert conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 1
    assert conn.execute("SELECT candidate_id FROM relations").fetchone()[0] == candidate_ids[0]
    decisions = conn.execute(
        "SELECT candidate_id, decision FROM relation_candidate_decisions ORDER BY id"
    ).fetchall()
    assert decisions == [(candidate_ids[0], "accepted"), (candidate_ids[1], "rejected")]
    with pytest.raises(ValueError, match="already reviewed"):
        approve_candidate(conn, candidate_ids[0], reviewer="human", reason="again")
    conn.close()


def test_legacy_relations_are_reclassified_as_unreviewed_candidates(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE relations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL, subject TEXT NOT NULL, "
        "relation TEXT NOT NULL, object TEXT NOT NULL, confidence REAL DEFAULT 1.0, "
        "created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO relations (source_path, subject, relation, object, confidence, created_at) "
        "VALUES ('legacy.md', 'A', 'uses', 'B', 0.7, '2026-07-29T00:00:00+00:00')"
    )
    conn.commit()

    _init_db(conn)

    assert conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 0
    row = conn.execute(
        "SELECT source, method, model_version, confidence, status FROM relation_candidates"
    ).fetchone()
    assert row == ("heuristic", "legacy-unreviewed", "pre-m1.2", 0.7, "candidate")
    conn.close()
