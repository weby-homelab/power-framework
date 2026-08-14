"""Unit and property tests for Task Manager v2, state transitions, and event chaining."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from power_framework.core.task_service import TaskService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".power").mkdir()
    return vault


def test_task_creation_and_events(temp_vault: Path) -> None:
    """Test task creation and initial event logging."""
    service = TaskService(temp_vault)
    task = service.create_task(
        task_id="task_001",
        title="Initial Task",
        objective="Verify task creation",
        owner="test_actor",
        state="backlog",
    )
    assert task.task_id == "task_001"
    assert task.state == "backlog"
    assert task.revision == 1

    events = service.get_events("task_001")
    assert len(events) == 1
    assert events[0].sequence == 1
    assert events[0].event_type == "task_created"
    assert events[0].payload_digest


def test_task_state_transitions(temp_vault: Path) -> None:
    """Test standard progression: backlog -> ready -> working -> completed."""
    service = TaskService(temp_vault)
    service.create_task(
        task_id="task_002",
        title="Lifecycle Task",
        state="backlog",
    )

    # Transition to ready
    t_ready = service.transition_task("task_002", "ready", expected_revision=1)
    assert t_ready.state == "ready"
    assert t_ready.revision == 2

    # Transition to working
    t_working = service.transition_task("task_002", "working", expected_revision=2)
    assert t_working.state == "working"
    assert t_working.revision == 3

    # Transition to completed requires receipt_id
    with pytest.raises(ValueError, match="requires a terminal receipt"):
        service.transition_task("task_002", "completed", expected_revision=3)

    t_completed = service.transition_task(
        "task_002", "completed", expected_revision=3, receipt_id="rec_12345"
    )
    assert t_completed.state == "completed"
    assert t_completed.revision == 4
    assert "rec_12345" in t_completed.receipt_ids

    # Terminal state cannot be transitioned
    with pytest.raises(ValueError, match="Cannot transition terminal task"):
        service.transition_task("task_002", "working")


def test_optimistic_concurrency_conflict(temp_vault: Path) -> None:
    """Ensure stale writer gets revision conflict error."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_concurrency", title="Concurrency Check")

    # Advance revision
    service.transition_task("task_concurrency", "ready", expected_revision=1)

    # Attempt transition with stale expected_revision=1
    with pytest.raises(ValueError, match="Revision conflict"):
        service.transition_task("task_concurrency", "working", expected_revision=1)


def test_event_hash_chaining(temp_vault: Path) -> None:
    """Verify that event digests form an unbroken hash chain."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_chain", title="Chain Check")
    service.transition_task("task_chain", "ready")
    service.transition_task("task_chain", "working")

    events = service.get_events("task_chain")
    assert len(events) == 3
    assert events[0].prev_event_digest == ""
    assert events[1].prev_event_digest == events[0].payload_digest
    assert events[2].prev_event_digest == events[1].payload_digest


def test_v1_work_packet_migration(temp_vault: Path) -> None:
    """Test migrating v1 JSON work packets into PowerTask v2."""
    v1_dir = temp_vault / ".power" / "work-packets"
    v1_dir.mkdir(parents=True)
    packet_data = {
        "task_id": "wp_legacy_01",
        "objective": "Legacy task objective",
        "owner": "legacy_agent",
        "state": "working",
        "scope": ["01_Projects/"],
        "authority": "propose",
        "created_at": "2026-08-10T10:00:00+00:00",
        "updated_at": "2026-08-10T11:00:00+00:00",
        "checkpoints": ["cp1", "cp2"],
    }
    (v1_dir / "wp_legacy_01.json").write_text(json.dumps(packet_data), encoding="utf-8")

    service = TaskService(temp_vault)
    summary = service.migrate_v1_work_packets()
    assert summary["migrated"] == 1
    assert summary["errors"] == 0

    task = service.get_task("wp_legacy_01")
    assert task is not None
    assert task.task_id == "wp_legacy_01"
    assert task.state == "working"
    assert task.objective == "Legacy task objective"
    assert task.authority == "propose"
