"""Regression tests for the additive OKF Memory Contract v0.2."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from power_framework.core.healer import heal_frontmatter
from power_framework.core.models import MemoryMetadata, OKFMetadata
from power_framework.core.parser import build_frontmatter, validate_metadata
from power_framework.core.temporal import (
    TemporalRecord,
    TemporalStatus,
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
<<<<<<< HEAD


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
=======
>>>>>>> 6fee2bc (fix: preserve typed relation semantics)
