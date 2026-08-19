"""Unit and property tests for Task Manager v2, state transitions, and event chaining."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from power_framework.core.task_models import TaskEvent
from power_framework.core.task_service import TaskService
from power_framework.core.task_store import TaskStore

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


@pytest.mark.parametrize(
    "task_id",
    ["../escape", "nested/task", "nested\\task", ".hidden", "task id"],
)
def test_task_ids_reject_filesystem_metacharacters(temp_vault: Path, task_id: str) -> None:
    """Task identifiers must never escape or introduce nested store paths."""
    service = TaskService(temp_vault)

    with pytest.raises(ValueError, match="task_id must be a safe token"):
        service.create_task(task_id=task_id, title="Unsafe task")

    assert not (temp_vault / ".power" / "escape.json").exists()


def test_task_store_revalidates_ids_at_filesystem_boundary(temp_vault: Path) -> None:
    """Direct store callers cannot bypass the domain model's task ID validation."""
    store = TaskStore(temp_vault)

    with pytest.raises(ValueError, match="task_id must be a safe token"):
        store.get_task("../../outside")


def test_malformed_task_event_journal_fails_closed(temp_vault: Path) -> None:
    """Corrupt event records are errors, never silently discarded history."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_corrupt", title="Corrupt journal")
    event_file = temp_vault / ".power" / "tasks" / "events" / "task_corrupt.jsonl"
    event_file.write_text(event_file.read_text(encoding="utf-8") + "{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed task event journal"):
        service.get_events("task_corrupt")


def test_malformed_task_snapshot_fails_closed(temp_vault: Path) -> None:
    """A corrupt snapshot is not reported as an absent task."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_snapshot", title="Corrupt snapshot")
    snapshot_file = temp_vault / ".power" / "tasks" / "task_snapshot.json"
    snapshot_file.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed task snapshot"):
        service.get_task("task_snapshot")


def test_task_snapshot_rolls_back_when_event_append_fails(temp_vault: Path) -> None:
    """Snapshot and journal remain unchanged when the second write fails."""
    service = TaskService(temp_vault)
    task = service.create_task(task_id="task_atomic", title="Atomic task")
    snapshot_file = temp_vault / ".power" / "tasks" / "task_atomic.json"
    event_file = temp_vault / ".power" / "tasks" / "events" / "task_atomic.jsonl"
    before_snapshot = snapshot_file.read_bytes()
    before_events = event_file.read_bytes()

    store = service.store
    original_append = store._append_event_unlocked

    def fail_append(event: TaskEvent) -> None:
        raise OSError("injected event append failure")

    store._append_event_unlocked = fail_append  # type: ignore[method-assign]
    try:
        updated = task.model_copy(update={"revision": 2})
        event = TaskEvent.create(
            task_id="task_atomic",
            sequence=2,
            actor="test",
            event_type="state_transition",
            payload={"to_state": "ready"},
        )
        with pytest.raises(OSError, match="injected event append failure"):
            store.save_task(updated, event=event)
    finally:
        store._append_event_unlocked = original_append  # type: ignore[method-assign]

    assert snapshot_file.read_bytes() == before_snapshot
    assert event_file.read_bytes() == before_events


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
    with pytest.raises(ValueError, match="requires a verified postcondition"):
        service.transition_task("task_002", "completed", expected_revision=3)

    artifact = temp_vault / "01_Projects" / "completion.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("verified result", encoding="utf-8")
    t_completed = service.transition_task(
        "task_002",
        "completed",
        expected_revision=3,
        completion_postcondition="The completion artifact exists and is readable.",
        completion_artifact_refs=["01_Projects/completion.md"],
    )
    assert t_completed.state == "completed"
    assert t_completed.revision == 4
    assert len(t_completed.receipt_ids) == 1
    receipt = service.store.get_completion_receipt(t_completed.receipt_ids[0])
    assert receipt is not None
    assert receipt.task_id == "task_002"
    assert receipt.task_revision == 4
    assert receipt.artifact_digests["01_Projects/completion.md"]

    # Terminal state cannot be transitioned
    with pytest.raises(ValueError, match="Cannot transition terminal task"):
        service.transition_task("task_002", "working")


def test_completion_rejects_fabricated_or_missing_artifacts(temp_vault: Path) -> None:
    """A caller-provided token cannot stand in for durable completion evidence."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_receipt", title="Receipt binding", state="working")

    with pytest.raises(ValueError, match="Completion receipt does not exist"):
        service.transition_task(
            "task_receipt",
            "completed",
            expected_revision=1,
            receipt_id="tcr_" + "a" * 64,
        )

    with pytest.raises(FileNotFoundError):
        service.transition_task(
            "task_receipt",
            "completed",
            expected_revision=1,
            completion_postcondition="Missing artifact should fail.",
            completion_artifact_refs=["01_Projects/missing.md"],
        )


def test_optimistic_concurrency_conflict(temp_vault: Path) -> None:
    """Ensure stale writer gets revision conflict error."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_concurrency", title="Concurrency Check")

    # Advance revision
    service.transition_task("task_concurrency", "ready", expected_revision=1)

    # Attempt transition with stale expected_revision=1
    with pytest.raises(ValueError, match="Revision conflict"):
        service.transition_task("task_concurrency", "working", expected_revision=1)


def test_task_transition_idempotency_replays_exact_result(temp_vault: Path) -> None:
    """Duplicate transport delivery returns the original result without a new event."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_idempotent", title="Idempotent transition")

    first = service.transition_task(
        "task_idempotent",
        "ready",
        expected_revision=1,
        idempotency_key="transition-ready-1",
    )
    replay = service.transition_task(
        "task_idempotent",
        "ready",
        expected_revision=1,
        idempotency_key="transition-ready-1",
    )

    assert replay == first
    assert len(service.get_events("task_idempotent")) == 2

    with pytest.raises(ValueError, match="reused for a different task command"):
        service.transition_task(
            "task_idempotent",
            "working",
            expected_revision=2,
            idempotency_key="transition-ready-1",
        )


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


@pytest.mark.parametrize(
    "tamper",
    [
        "payload",
        "payload_digest",
        "prev_event_digest",
        "duplicate_sequence",
        "skipped_sequence",
        "wrong_task_id",
        "truncated_final_line",
        "unexpected_schema_field",
    ],
)
def test_event_hash_chain_rejects_tampering(temp_vault: Path, tamper: str) -> None:
    """Payload, link, sequence, identity, and schema tampering fail closed on read."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_tamper", title="Tamper check")
    service.transition_task("task_tamper", "ready")
    event_file = temp_vault / ".power" / "tasks" / "events" / "task_tamper.jsonl"
    raw = event_file.read_text(encoding="utf-8")
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if tamper == "payload":
        records[1]["payload"]["to_state"] = "working"
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"hash|digest"
    elif tamper == "payload_digest":
        records[1]["payload_digest"] = "0" * 64
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"hash|digest"
    elif tamper == "prev_event_digest":
        records[1]["prev_event_digest"] = "0" * 64
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"hash|digest|chain"
    elif tamper == "duplicate_sequence":
        records[1]["sequence"] = records[0]["sequence"]
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"sequence|monotonic"
    elif tamper == "skipped_sequence":
        records[1]["sequence"] = records[0]["sequence"] + 2
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"sequence|monotonic"
    elif tamper == "wrong_task_id":
        records[1]["task_id"] = "other_task"
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"task_id|Task"
    elif tamper == "truncated_final_line":
        event_file.write_text(raw.rstrip("\n")[:-8] + "\n", encoding="utf-8")
        match = r"Malformed|JSON|journal|event"
    else:  # unexpected_schema_field
        records[1]["unexpected_field"] = "nope"
        event_file.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        match = r"extra|unexpected|Forbidden|validation|Malformed|journal|event"

    with pytest.raises(ValueError, match=match):
        service.get_events("task_tamper")


def test_migrated_task_uses_event_cursor_not_revision(temp_vault: Path) -> None:
    """Migration revision and the subsequent journal sequence remain independent."""
    v1_dir = temp_vault / ".power" / "work-packets"
    v1_dir.mkdir(parents=True)
    packet = {
        "task_id": "wp_cursor",
        "state": "working",
        "checkpoints": ["cp1", "cp2", "cp3"],
    }
    (v1_dir / "wp_cursor.json").write_text(json.dumps(packet), encoding="utf-8")
    service = TaskService(temp_vault)

    assert service.migrate_v1_work_packets()["migrated"] == 1
    migrated = service.get_task("wp_cursor")
    assert migrated is not None
    assert migrated.revision == 4
    service.transition_task("wp_cursor", "ready", expected_revision=4)
    service.transition_task("wp_cursor", "working", expected_revision=5)
    assert [event.sequence for event in service.get_events("wp_cursor")] == [1, 2, 3]
    assert service.migrate_v1_work_packets()["skipped"] == 1


@pytest.mark.parametrize("field", ["task_id", "revision", "state", "authority", "attempt"])
def test_task_values_cannot_mutate_invariants(temp_vault: Path, field: str) -> None:
    """Generic compatibility updates cannot bypass task identity or state rules."""
    service = TaskService(temp_vault)
    task = service.create_task(task_id="task_values", title="Bounded update")
    with pytest.raises(ValueError, match="immutable or unknown"):
        service.transition_task(
            "task_values",
            "ready",
            expected_revision=task.revision,
            values={field: "working" if field == "state" else 99},
        )
    unchanged = service.get_task("task_values")
    assert unchanged is not None
    assert unchanged.revision == task.revision
    assert unchanged.state == task.state


def test_task_values_are_revalidated_before_persistence(temp_vault: Path) -> None:
    """Whitelisted compatibility fields still pass complete model validation."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_bounds", title="Bounded update")
    with pytest.raises(ValueError, match="less than or equal to 10"):
        service.transition_task(
            "task_bounds", "ready", expected_revision=1, values={"max_attempts": 11}
        )


def test_task_values_reject_malformed_refs_and_unknown_state(temp_vault: Path) -> None:
    """Malformed whitelisted refs and unknown transition targets fail closed."""
    service = TaskService(temp_vault)
    service.create_task(task_id="task_refs", title="Refs check")
    with pytest.raises((ValueError, TypeError), match=r"list|type|artifact|validation|Input"):
        service.transition_task(
            "task_refs",
            "ready",
            expected_revision=1,
            values={"artifact_refs": "not-a-list"},
        )
    with pytest.raises(
        (ValueError, TypeError), match=r"dict|mapping|type|external|validation|Input"
    ):
        service.transition_task(
            "task_refs",
            "ready",
            expected_revision=1,
            values={"external_refs": ["not-a-mapping"]},
        )
    with pytest.raises(ValueError, match=r"Invalid state transition|not-a-real-state|state"):
        service.transition_task("task_refs", "not-a-real-state", expected_revision=1)


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


def test_direct_backlog_to_working_transition(temp_vault: Path) -> None:
    """Test direct transition from backlog to working state."""
    service = TaskService(temp_vault)
    service.create_task(
        task_id="task_direct_working",
        title="Direct Work Task",
        state="backlog",
    )

    t_working = service.transition_task("task_direct_working", "working", expected_revision=1)
    assert t_working.state == "working"
    assert t_working.revision == 2

    # Verify transition back to ready or backlog
    t_ready = service.transition_task("task_direct_working", "ready", expected_revision=2)
    assert t_ready.state == "ready"
    assert t_ready.revision == 3

    t_backlog = service.transition_task("task_direct_working", "backlog", expected_revision=3)
    assert t_backlog.state == "backlog"
    assert t_backlog.revision == 4
