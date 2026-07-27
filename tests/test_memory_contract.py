"""Regression tests for the additive OKF Memory Contract v0.2."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from power_framework.core.healer import heal_frontmatter
from power_framework.core.models import MemoryMetadata, OKFMetadata
from power_framework.core.parser import build_frontmatter, validate_metadata


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
