"""Lifecycle adapter conformance and no-silent-write invariants."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

import pytest

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.lifecycle import LifecycleAdapter, capability_matrix

if TYPE_CHECKING:
    from pathlib import Path


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_all_four_events_are_portable_for_every_client() -> None:
    matrix = capability_matrix()

    assert len(matrix) == 20
    assert {item.event for item in matrix} == {
        "session-start",
        "post-write",
        "pre-compact",
        "stop",
    }
    assert all(item.supported for item in matrix)
    assert {item.maturity for item in matrix} == {"portable-mcp-skill"}


@pytest.mark.parametrize("event", ["session-start", "post-write", "pre-compact", "stop"])
def test_lifecycle_events_are_read_only_and_bounded(sample_vault: Path, event: str) -> None:
    before = _snapshot(sample_vault)
    result = LifecycleAdapter(ApplicationService(sample_vault), client="opencode").handle(
        event,  # type: ignore[arg-type]
        task_id="missing-task" if event in {"pre-compact", "stop"} else None,
    )

    assert result.schema_version == "power.lifecycle.v1"
    assert result.capability.maturity == "portable-mcp-skill"
    assert result.write_performed is False
    proposal = result.data.get("checkpoint_proposal")
    assert not isinstance(proposal, dict) or proposal.get("write_performed", False) is False
    assert _snapshot(sample_vault) == before


def test_pre_compact_proposal_requires_separate_approval(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    service.task(
        action="create",
        task_id="pending-task",
        values={
            "objective": "Keep the current bounded task",
            "owner": "test",
            "state": "working",
        },
        context=RequestContext(actor="test", authority="propose"),
    )
    result = LifecycleAdapter(service).handle("pre-compact", task_id="pending-task")

    proposal = result.data["checkpoint_proposal"]
    assert isinstance(proposal, dict)
    assert proposal["approval_required"] is True
    assert proposal["action"] == "checkpoint"
    assert proposal["expected_revision"] == 1


def test_unknown_client_is_explicitly_rejected(sample_vault: Path) -> None:
    with pytest.raises(ValueError, match="unsupported lifecycle client"):
        LifecycleAdapter(ApplicationService(sample_vault), client="unknown")  # type: ignore[arg-type]
