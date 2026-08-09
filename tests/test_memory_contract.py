"""Regression tests for the additive OKF Memory Contract v0.2."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from power_framework.core.db import _init_db
from power_framework.core.healer import heal_frontmatter
from power_framework.core.models import MemoryMetadata, OKFMetadata
from power_framework.core.parser import build_frontmatter, validate_metadata
from power_framework.core.searcher import _sync_vault_to_db
from power_framework.core.temporal import (
    TemporalRecord,
    TemporalStatus,
    load_temporal_records,
    resolve_temporal_statuses,
)


def _memory(**overrides: object) -> MemoryMetadata:
    values: dict[str, object] = {
        "kind": "semantic",
        "confidence": 0.95,
        "valid_from": date(2026, 7, 1),
        "supersedes": ["03_Resources/previous.md"],
        "sources": ["https://example.com/source"],
        "evidence": ["sha256:abc123"],
        "write_policy": "agent-proposed",
        "sensitivity": "internal",
    }
    values.update(overrides)
    return MemoryMetadata(**values)


def test_memory_contract_round_trips_and_preserves_unknown_fields() -> None:
    metadata = OKFMetadata(
        type="Resource",
        title="Governed fact",
        description="A fact with provenance.",
        timestamp=datetime(2026, 7, 27, 12, 0, 0),
        okf_version="0.2",
        memory=_memory(),
        custom_extension={"retention": "90d"},
    )

    rendered = build_frontmatter(metadata)
    parsed = validate_metadata(rendered + "\n\nBody")

    assert parsed is not None
    assert parsed.okf_version == "0.2"
    assert parsed.memory is not None
    assert parsed.memory.kind == "semantic"
    assert parsed.memory.supersedes == ["03_Resources/previous.md"]
    assert parsed.model_extra == {"custom_extension": {"retention": "90d"}}


def test_agent_memory_requires_provenance_and_valid_dates() -> None:
    with pytest.raises(ValidationError, match="requires sources and evidence"):
        _memory(sources=[], evidence=[])
    with pytest.raises(ValidationError, match="valid_until must not be before valid_from"):
        _memory(valid_until=date(2026, 6, 30))


def test_healer_preserves_memory_and_unknown_fields(tmp_path) -> None:
    filepath = tmp_path / "governed.md"
    content = """---
type: Project
title: \"Governed note\"
okf_version: \"0.2\"
memory:
  kind: semantic
  sources: [https://example.com/source]
  evidence: [sha256:abc123]
  write_policy: agent-proposed
custom_extension:
  retention: 90d
related:
  - path: 01_Projects/dependency.md
    relation: depends_on
    confidence: 0.42
    evidence:
      source: human-review
timestamp: 2026-07-27T12:00:00+00:00
---

Body used to infer a description.
"""

    healed, changes = heal_frontmatter(content, filepath)
    parsed = validate_metadata(healed)

    assert any("Added missing description" in change for change in changes)
    assert parsed is not None
    assert parsed.memory is not None
    assert parsed.memory.evidence == ["sha256:abc123"]
    assert parsed.model_extra == {"custom_extension": {"retention": "90d"}}
    assert parsed.related[0].relation == "depends_on"
    assert parsed.related[0].confidence == 0.42
    assert parsed.related[0].model_extra == {"evidence": {"source": "human-review"}}


def test_temporal_chain_uses_inclusive_dates_and_preserves_history() -> None:
    records = {
        "03_Resources/old.md": TemporalRecord("03_Resources/old.md", _memory()),
        "03_Resources/new.md": TemporalRecord(
            "03_Resources/new.md",
            _memory(valid_from=date(2026, 7, 10), supersedes=["03_Resources/old.md"]),
        ),
    }

    before = resolve_temporal_statuses(records, date(2026, 7, 9))
    boundary = resolve_temporal_statuses(records, date(2026, 7, 10))

    assert before["03_Resources/old.md"] == TemporalStatus.CURRENT
    assert before["03_Resources/new.md"] == TemporalStatus.HISTORICAL
    assert boundary["03_Resources/old.md"] == TemporalStatus.HISTORICAL
    assert boundary["03_Resources/new.md"] == TemporalStatus.CURRENT


def test_competing_supersession_is_explicitly_conflicted() -> None:
    records = {
        "03_Resources/old.md": TemporalRecord("03_Resources/old.md", _memory()),
        "03_Resources/a.md": TemporalRecord(
            "03_Resources/a.md", _memory(supersedes=["03_Resources/old.md"])
        ),
        "03_Resources/b.md": TemporalRecord(
            "03_Resources/b.md", _memory(supersedes=["03_Resources/old.md"])
        ),
    }

    statuses = resolve_temporal_statuses(records, date(2026, 7, 10))

    assert set(statuses.values()) == {TemporalStatus.CONFLICTED}


def test_incomplete_temporal_projection_fails_closed_to_disk_fallback(tmp_path) -> None:
    database = tmp_path / "search.db"
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.execute("INSERT INTO file_metadata(rel_path, mtime) VALUES (?, ?)", ("note.md", 0))
        conn.commit()

    assert load_temporal_records(database) is None


def test_temporal_projection_with_same_count_but_wrong_path_fails_closed(tmp_path) -> None:
    database = tmp_path / "search.db"
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.execute("INSERT INTO file_metadata(rel_path, mtime) VALUES (?, ?)", ("note.md", 0))
        conn.execute(
            "INSERT INTO temporal_records(rel_path, memory_json) VALUES (?, ?)",
            ("stale.md", None),
        )
        conn.commit()

    assert load_temporal_records(database) is None


def test_temporal_projection_updates_when_a_note_changes(tmp_path) -> None:
    note = tmp_path / "03_Resources" / "temporal.md"
    note.parent.mkdir()
    note.write_text(
        "---\n"
        "type: Resource\n"
        'title: "Temporal"\n'
        'description: "Temporal projection"\n'
        "timestamp: 2026-07-10T00:00:00Z\n"
        "memory:\n"
        "  kind: semantic\n"
        "  valid_from: 2026-01-01\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    database = tmp_path / "search.db"

    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        _sync_vault_to_db(tmp_path, conn, sync_embeddings=False)
        first = load_temporal_records(database)
        assert first is not None
        assert first["03_Resources/temporal.md"].memory is not None
        assert first["03_Resources/temporal.md"].memory.valid_from == date(2026, 1, 1)

        original_mtime = note.stat().st_mtime
        note.write_text(
            note.read_text(encoding="utf-8").replace("2026-01-01", "2027-01-01"),
            encoding="utf-8",
        )
        os.utime(note, (original_mtime + 1, original_mtime + 1))
        _sync_vault_to_db(tmp_path, conn, sync_embeddings=False)
        second = load_temporal_records(database)

    assert second is not None
    assert second["03_Resources/temporal.md"].memory is not None
    assert second["03_Resources/temporal.md"].memory.valid_from == date(2027, 1, 1)
