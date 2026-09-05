"""Phase 2 Event Ledger, Ingestion Boundary, and Integrity Verification Tests.

Validates all Phase 2 requirements and gates G2.1 - G2.7:
1. append/read
2. deterministic replay
3. duplicate delivery & idempotency
4. concurrent append under Level 3 project lock
5. interrupted append / torn-tail crash recovery
6. malformed record detection
7. unsupported schema version rejection
8. integrity failure (payload, envelope, sequence, prev_event_hash tampering)
9. project isolation, path traversal, and symlink escape rejection
10. safe ledger rotation across multiple files
11. disposable derived SQLite index rebuild and status markdown materialization
12. secret redaction fixtures & RedactionRecord
13. privacy modes (metadata-only, structured-events, full-content)
14. cross-subsystem sagas and reconciliation
"""

from __future__ import annotations

import re
import sqlite3
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from pydantic import ValidationError

from power_framework.core.canonical_json import (
    canonical_json_dumps,
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.lock_tracker import LockHierarchyViolationError
from power_framework.core.mutation import vault_mutation
from power_framework.core.project_ingestion import (
    _get_raw_evidence_dir,
    _get_sqlite_path,
    _reconciliation_attempts,
    append_project_event,
    import_project_events,
    materialize_status_markdown,
    rebuild_derived_index,
    reconcile_project_subsystems,
    redact_secrets,
    replay_project,
    store_raw_evidence,
    update_derived_index_for_event,
)
from power_framework.core.project_models import (
    EVENT_ID_REGEX,
    AppendCommand,
    IdempotencyConflictError,
    LedgerIntegrityError,
    PrivacyMode,
    ProjectEvent,
    RedactionRecord,
    generate_deterministic_event_id,
    validate_event_id,
    validate_project_id,
)
from power_framework.core.project_store import (
    LockAcquisitionTimeoutError,
    ProjectEventStore,
    get_project_dir,
    project_lock,
    recover_torn_tail,
)
from power_framework.core.task_store import TaskStore


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    """Create an isolated temporary vault root for testing."""
    root = tmp_path / "test_vault"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ==============================================================================
# 1. Append / Read Tests
# ==============================================================================


def test_append_and_read_event(vault_root: Path) -> None:
    store = ProjectEventStore("prj_alpha", vault_root)
    cmd = AppendCommand(
        project_id="prj_alpha",
        event_type="project.created",
        payload={"name": "Alpha Project", "charter": "Build PSE Phase 2"},
        actor="user:rekvizitor",
        source="cli",
    )
    event = store.append(cmd)

    assert event.schema_version == "power.project-event.v1"
    assert event.project_id == "prj_alpha"
    assert event.sequence == 1
    assert event.prev_event_hash == ""
    assert event.payload_digest == compute_payload_digest(cmd.payload)
    assert event.event_hash == compute_event_hash(event.model_dump())

    replayed = list(store.replay(from_sequence=1))
    assert len(replayed) == 1
    assert replayed[0] == event


# ==============================================================================
# 2. Deterministic Replay Tests (Gate G2.1)
# ==============================================================================


def test_deterministic_replay(vault_root: Path) -> None:
    store = ProjectEventStore("prj_deterministic", vault_root)

    events_created: list[ProjectEvent] = []
    for seq in range(1, 6):
        cmd = AppendCommand(
            project_id="prj_deterministic",
            event_type="project.updated",
            payload={"step": seq, "note": f"Step {seq}"},
            actor="agent:agy",
            source="internal_engine",
        )
        ev = store.append(cmd)
        assert ev.sequence == seq
        events_created.append(ev)

    # Replay all
    replayed_1 = list(store.replay(from_sequence=1))
    assert len(replayed_1) == 5
    assert [e.sequence for e in replayed_1] == [1, 2, 3, 4, 5]
    for orig, rep in zip(events_created, replayed_1, strict=True):
        assert orig.event_id == rep.event_id
        assert orig.event_hash == rep.event_hash
        assert orig.prev_event_hash == rep.prev_event_hash

    # Partial replay from sequence 3
    replayed_from_3 = list(store.replay(from_sequence=3))
    assert len(replayed_from_3) == 3
    assert [e.sequence for e in replayed_from_3] == [3, 4, 5]

    # Multiple runs produce identical hashes and byte representations
    replayed_2 = list(store.replay(from_sequence=1))
    assert [e.event_hash for e in replayed_1] == [e.event_hash for e in replayed_2]


# ==============================================================================
# 3. Duplicate Delivery & Idempotency Tests (Gate G2.2)
# ==============================================================================


def test_duplicate_delivery_idempotency(vault_root: Path) -> None:
    store = ProjectEventStore("prj_idempotent", vault_root)

    cmd1 = AppendCommand(
        project_id="prj_idempotent",
        event_type="project.created",
        payload={"name": "Idempotent Project"},
        actor="user:rekvizitor",
        source="cli",
        idempotency_key="unique_key_001",
    )
    ev1 = store.append(cmd1)
    assert ev1.sequence == 1

    # Repeat delivery with the same idempotency key
    ev2 = store.append(cmd1)
    assert ev2.event_id == ev1.event_id
    assert ev2.sequence == 1
    assert ev2.event_hash == ev1.event_hash

    # Ledger must strictly contain 1 event
    replayed = list(store.replay(from_sequence=1))
    assert len(replayed) == 1

    # Repeat with deterministic event_id
    cmd3 = AppendCommand(
        project_id="prj_idempotent",
        event_type="project.updated",
        payload={"field": "value"},
        actor="user:rekvizitor",
        source="cli",
        event_id="evt_prj_idempotent_custom_fixed_id",
    )
    ev3 = store.append(cmd3)
    assert ev3.sequence == 2
    assert ev3.event_id == "evt_prj_idempotent_custom_fixed_id"

    # Redeliver with same event_id
    ev4 = store.append(cmd3)
    assert ev4 == ev3
    assert len(list(store.replay(from_sequence=1))) == 2


# ==============================================================================
# 4. Concurrent Append Under Project Lock Tests (Gate G2.3)
# ==============================================================================


def test_concurrent_append_under_project_lock(vault_root: Path) -> None:
    store = ProjectEventStore("prj_concurrent", vault_root)
    num_threads = 8
    events_per_thread = 5
    total_events = num_threads * events_per_thread

    def worker(worker_id: int) -> list[ProjectEvent]:
        events = []
        for i in range(events_per_thread):
            cmd = AppendCommand(
                project_id="prj_concurrent",
                event_type="project.updated",
                payload={"worker": worker_id, "iter": i},
                actor=f"worker:{worker_id}",
                source="test",
            )
            ev = store.append(cmd)
            events.append(ev)
        return events

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for f in futures:
            f.result()

    replayed = list(store.replay(from_sequence=1))
    assert len(replayed) == total_events

    # Verify strict sequence monotonicity without gaps or duplicates
    sequences = [e.sequence for e in replayed]
    assert sequences == list(range(1, total_events + 1))

    # Verify cryptographic ledger validity
    ver_res = store.verify()
    assert ver_res.valid is True
    assert ver_res.event_count == total_events
    assert len(ver_res.errors) == 0


def test_independent_projects_concurrency_isolation(vault_root: Path) -> None:
    """Project A and Project B acquire independent locks and do not contend."""
    store_a = ProjectEventStore("prj_isolated_a", vault_root)
    store_b = ProjectEventStore("prj_isolated_b", vault_root)

    def write_a() -> None:
        for i in range(10):
            store_a.append(
                AppendCommand(
                    project_id="prj_isolated_a",
                    event_type="project.updated",
                    payload={"val": i},
                    actor="actor:a",
                    source="cli",
                )
            )

    def write_b() -> None:
        for i in range(10):
            store_b.append(
                AppendCommand(
                    project_id="prj_isolated_b",
                    event_type="project.updated",
                    payload={"val": i},
                    actor="actor:b",
                    source="cli",
                )
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_a = pool.submit(write_a)
        f_b = pool.submit(write_b)
        f_a.result()
        f_b.result()

    assert store_a.verify().valid is True
    assert store_b.verify().valid is True
    assert len(list(store_a.replay())) == 10
    assert len(list(store_b.replay())) == 10


def test_lock_hierarchy_violation_rejection(vault_root: Path) -> None:
    """Holding higher level lock and attempting to acquire lower level raises LockHierarchyViolationError (ADR-PSE-007)."""
    task_store = TaskStore(vault_root)
    proj_store = ProjectEventStore("prj_lock_hierarchy", vault_root)

    # 1. Project lock held (Level 3) -> acquiring Task lock (Level 2) raises LockHierarchyViolationError
    with (
        proj_store.lock(),
        pytest.raises(LockHierarchyViolationError, match="Lock hierarchy violation"),
        task_store.lock(),
    ):
        pass

    # 2. Project lock held (Level 3) -> acquiring Vault Mutation lock (Level 1) raises LockHierarchyViolationError
    with (
        proj_store.lock(),
        pytest.raises(LockHierarchyViolationError, match="Lock hierarchy violation"),
        vault_mutation(vault_root),
    ):
        pass

    # 3. Task lock held (Level 2) -> acquiring Vault Mutation lock (Level 1) raises LockHierarchyViolationError
    with (
        task_store.lock(),
        pytest.raises(LockHierarchyViolationError, match="Lock hierarchy violation"),
        vault_mutation(vault_root),
    ):
        pass

    # 4. Strictly ascending order: Level 1 -> Level 2 -> Level 3 succeeds!
    with vault_mutation(vault_root), task_store.lock(), proj_store.lock():
        assert True


def test_complete_last_record_hash_tamper_is_not_truncated(vault_root: Path) -> None:
    """Torn-tail recovery must NOT truncate complete records with invalid hash (fails closed)."""
    store = ProjectEventStore("prj_tamper_last_hash", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_tamper_last_hash",
            event_type="project.created",
            payload={"name": "Event 1"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    store.append(
        AppendCommand(
            project_id="prj_tamper_last_hash",
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    lines = store.active_events_file.read_text(encoding="utf-8").splitlines(keepends=True)
    assert len(lines) == 2
    import json

    rec2 = json.loads(lines[1])
    rec2["event_hash"] = "deadbeef" * 8
    lines[1] = json.dumps(rec2) + "\n"
    store.active_events_file.write_text("".join(lines), encoding="utf-8")

    size_before = store.active_events_file.stat().st_size

    with pytest.raises(LedgerIntegrityError, match=r"Corruption detected"):
        recover_torn_tail(store.active_events_file)

    assert store.active_events_file.stat().st_size == size_before


def test_complete_last_record_payload_tamper_is_not_truncated(vault_root: Path) -> None:
    """Torn-tail recovery must NOT truncate complete records with tampered payload."""
    store = ProjectEventStore("prj_tamper_last_payload", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_tamper_last_payload",
            event_type="project.created",
            payload={"name": "Event 1"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    store.append(
        AppendCommand(
            project_id="prj_tamper_last_payload",
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    lines = store.active_events_file.read_text(encoding="utf-8").splitlines(keepends=True)
    import json

    rec2 = json.loads(lines[1])
    rec2["payload"]["step"] = 999
    lines[1] = json.dumps(rec2) + "\n"
    store.active_events_file.write_text("".join(lines), encoding="utf-8")

    size_before = store.active_events_file.stat().st_size

    with pytest.raises(LedgerIntegrityError, match=r"Corruption detected"):
        recover_torn_tail(store.active_events_file)

    assert store.active_events_file.stat().st_size == size_before


def test_complete_last_record_bad_schema_is_not_truncated(vault_root: Path) -> None:
    """Torn-tail recovery must NOT truncate complete records with schema corruption."""
    store = ProjectEventStore("prj_tamper_last_schema", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_tamper_last_schema",
            event_type="project.created",
            payload={"name": "Event 1"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write('{"invalid":"json_missing_fields"}\n')

    size_before = store.active_events_file.stat().st_size

    with pytest.raises(LedgerIntegrityError, match=r"Corruption detected"):
        recover_torn_tail(store.active_events_file)

    assert store.active_events_file.stat().st_size == size_before


def test_unterminated_tail_is_truncated(vault_root: Path) -> None:
    """Torn-tail recovery truncates unterminated trailing bytes from mid-write crash."""
    store = ProjectEventStore("prj_unterminated_tail", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_unterminated_tail",
            event_type="project.created",
            payload={"name": "Event 1"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    valid_size = store.active_events_file.stat().st_size

    with open(store.active_events_file, "ab") as f:
        f.write(b'{"event_id":"evt_crash_partial","sequence":2')

    assert store.active_events_file.stat().st_size > valid_size

    truncated = recover_torn_tail(store.active_events_file)
    assert truncated > 0
    assert store.active_events_file.stat().st_size == valid_size
    assert store.verify().valid is True


def test_append_refuses_corrupted_middle_record(vault_root: Path) -> None:
    """Append must fail closed and refuse writing if an earlier record is corrupted."""
    store = ProjectEventStore("prj_corrupt_middle", vault_root)
    for i in range(1, 4):
        store.append(
            AppendCommand(
                project_id="prj_corrupt_middle",
                event_type="project.updated",
                payload={"step": i},
                actor="user:rekvizitor",
                source="cli",
            )
        )

    lines = store.active_events_file.read_text(encoding="utf-8").splitlines(keepends=True)
    import json

    rec2 = json.loads(lines[1])
    rec2["payload"]["step"] = 999
    lines[1] = json.dumps(rec2) + "\n"
    store.active_events_file.write_text("".join(lines), encoding="utf-8")

    cmd4 = AppendCommand(
        project_id="prj_corrupt_middle",
        event_type="project.updated",
        payload={"step": 4},
        actor="user:rekvizitor",
        source="cli",
    )
    with pytest.raises(LedgerIntegrityError, match="verification failed"):
        store.append(cmd4)


def test_append_refuses_corrupted_last_complete_record(vault_root: Path) -> None:
    """Append must fail closed if the last complete record is tampered."""
    store = ProjectEventStore("prj_corrupt_last", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_corrupt_last",
            event_type="project.created",
            payload={"name": "Event 1"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    store.append(
        AppendCommand(
            project_id="prj_corrupt_last",
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    lines = store.active_events_file.read_text(encoding="utf-8").splitlines(keepends=True)
    import json

    rec2 = json.loads(lines[1])
    rec2["event_hash"] = "00" * 32
    lines[1] = json.dumps(rec2) + "\n"
    store.active_events_file.write_text("".join(lines), encoding="utf-8")

    cmd3 = AppendCommand(
        project_id="prj_corrupt_last",
        event_type="project.updated",
        payload={"step": 3},
        actor="user:rekvizitor",
        source="cli",
    )
    with pytest.raises(LedgerIntegrityError, match=r"Corruption detected|verification failed"):
        store.append(cmd3)


def test_append_after_valid_torn_tail_recovery_succeeds(vault_root: Path) -> None:
    """Append recovers unterminated bytes and cleanly writes next sequence."""
    store = ProjectEventStore("prj_append_torn_recovery", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_append_torn_recovery",
            event_type="project.created",
            payload={"name": "Event 1"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    with open(store.active_events_file, "ab") as f:
        f.write(b'{"partial":"bytes"')

    ev2 = store.append(
        AppendCommand(
            project_id="prj_append_torn_recovery",
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    assert ev2.sequence == 2
    assert store.verify().valid is True


def test_lock_timeout_raises_exception(vault_root: Path) -> None:
    """If another process/thread holds the lock past the timeout, raises LockAcquisitionTimeoutError."""
    project_id = "prj_timeout"

    lock_acquired_event = threading.Event()
    release_lock_event = threading.Event()

    def lock_holder() -> None:
        with project_lock(project_id, vault_root, timeout=5.0):
            lock_acquired_event.set()
            release_lock_event.wait(timeout=5.0)

    t = threading.Thread(target=lock_holder, daemon=True)
    t.start()
    assert lock_acquired_event.wait(timeout=2.0)

    try:
        with (
            pytest.raises(LockAcquisitionTimeoutError),
            project_lock(project_id, vault_root, timeout=0.2),
        ):
            pass
    finally:
        release_lock_event.set()
        t.join(timeout=2.0)


# ==============================================================================
# 5. Torn-Tail Crash Recovery Tests (Gate G2.4)
# ==============================================================================


def test_interrupted_append_torn_tail_recovery(vault_root: Path) -> None:
    store = ProjectEventStore("prj_torn_tail", vault_root)

    # Append 3 valid events
    for i in range(1, 4):
        store.append(
            AppendCommand(
                project_id="prj_torn_tail",
                event_type="project.updated",
                payload={"index": i},
                actor="user:rekvizitor",
                source="cli",
            )
        )

    assert len(list(store.replay())) == 3
    valid_size = store.active_events_file.stat().st_size

    # Simulate an abrupt crash / torn write (kill -9 mid-write)
    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write(
            '{"event_id":"evt_prj_torn_tail_4_corrupted","sequence":4,"payload":{"partial":"corrupt'
        )

    # Verify file is larger
    assert store.active_events_file.stat().st_size > valid_size

    # Next append or recovery truncates the torn tail
    truncated = recover_torn_tail(store.active_events_file)
    assert truncated > 0
    assert store.active_events_file.stat().st_size == valid_size

    # Replay returns exactly the 3 valid events
    replayed = list(store.replay())
    assert len(replayed) == 3
    assert [e.sequence for e in replayed] == [1, 2, 3]

    # Append sequence 4 cleanly
    ev4 = store.append(
        AppendCommand(
            project_id="prj_torn_tail",
            event_type="project.updated",
            payload={"index": 4},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    assert ev4.sequence == 4
    assert ev4.prev_event_hash == replayed[-1].event_hash
    assert store.verify().valid is True


# ==============================================================================
# 6. Malformed Record Detection (Gate G2.4)
# ==============================================================================


def test_malformed_record_detection(vault_root: Path) -> None:
    store = ProjectEventStore("prj_malformed", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_malformed",
            event_type="project.created",
            payload={"name": "Malformed Test"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Inject malformed line followed by a valid line
    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write("THIS_IS_NOT_VALID_JSON\n")

    res = store.verify()
    assert res.valid is False
    assert any("Malformed JSON" in err for err in res.errors)


# ==============================================================================
# 7. Unsupported Schema Version Rejection
# ==============================================================================


def test_unsupported_schema_version_rejection(vault_root: Path) -> None:
    store = ProjectEventStore("prj_bad_schema", vault_root)
    ev = store.append(
        AppendCommand(
            project_id="prj_bad_schema",
            event_type="project.created",
            payload={"name": "Bad Schema Test"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Corrupt schema_version
    bad_dict = ev.model_dump()
    bad_dict["schema_version"] = "power.project-event.v2"
    bad_dict["event_id"] = "evt_prj_bad_schema_2_abcdef"
    bad_dict["sequence"] = 2
    bad_dict["prev_event_hash"] = ev.event_hash
    bad_dict["event_hash"] = compute_event_hash(bad_dict)

    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write(canonical_json_dumps(bad_dict) + "\n")

    res = store.verify()
    assert res.valid is False
    assert any("Schema validation error" in err for err in res.errors)


# ==============================================================================
# 8. Cryptographic Integrity Failure Tests (Gate G2.4)
# ==============================================================================


def test_integrity_failure_payload_tampering(vault_root: Path) -> None:
    store = ProjectEventStore("prj_tamper_payload", vault_root)
    ev = store.append(
        AppendCommand(
            project_id="prj_tamper_payload",
            event_type="project.created",
            payload={"amount": 100},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Tamper payload in place without updating payload_digest
    tampered = ev.model_dump()
    tampered["payload"]["amount"] = 999999
    # Update event_hash so only payload_digest is mismatched
    tampered["event_hash"] = compute_event_hash(tampered)

    with open(store.active_events_file, "w", encoding="utf-8") as f:
        f.write(canonical_json_dumps(tampered) + "\n")

    res = store.verify()
    assert res.valid is False
    assert any("Payload digest mismatch" in err for err in res.errors)


def test_integrity_failure_envelope_tampering(vault_root: Path) -> None:
    store = ProjectEventStore("prj_tamper_envelope", vault_root)
    ev = store.append(
        AppendCommand(
            project_id="prj_tamper_envelope",
            event_type="project.created",
            payload={"status": "initial"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Tamper actor in place without updating event_hash
    tampered = ev.model_dump()
    tampered["actor"] = "attacker:fake_admin"

    with open(store.active_events_file, "w", encoding="utf-8") as f:
        f.write(canonical_json_dumps(tampered) + "\n")

    res = store.verify()
    assert res.valid is False
    assert any("Event hash mismatch" in err for err in res.errors)


def test_integrity_failure_sequence_break(vault_root: Path) -> None:
    store = ProjectEventStore("prj_tamper_seq", vault_root)
    ev1 = store.append(
        AppendCommand(
            project_id="prj_tamper_seq",
            event_type="project.created",
            payload={"name": "Seq Test"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Append event with skipped sequence 3 instead of 2
    cmd2 = AppendCommand(
        project_id="prj_tamper_seq",
        event_type="project.updated",
        payload={"step": 2},
        actor="user:rekvizitor",
        source="cli",
    )
    raw_ev2 = {
        "event_id": "evt_prj_tamper_seq_3_test",
        "schema_version": "power.project-event.v1",
        "project_id": "prj_tamper_seq",
        "sequence": 3,  # Skipped sequence!
        "timestamp": "2026-09-03T18:00:00Z",
        "actor": cmd2.actor,
        "source": cmd2.source,
        "session_id": None,
        "event_type": cmd2.event_type,
        "payload": cmd2.payload,
        "payload_digest": compute_payload_digest(cmd2.payload),
        "prev_event_hash": ev1.event_hash,
        "artifact_refs": [],
        "evidence_refs": [],
        "correlation_id": None,
        "causation_id": None,
        "idempotency_key": None,
    }
    raw_ev2["event_hash"] = compute_event_hash(raw_ev2)

    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write(canonical_json_dumps(raw_ev2) + "\n")

    res = store.verify()
    assert res.valid is False
    assert any("Broken sequence" in err for err in res.errors)


def test_integrity_failure_prev_event_hash_break(vault_root: Path) -> None:
    store = ProjectEventStore("prj_tamper_hash_chain", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_tamper_hash_chain",
            event_type="project.created",
            payload={"name": "Chain Test"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    cmd2 = AppendCommand(
        project_id="prj_tamper_hash_chain",
        event_type="project.updated",
        payload={"step": 2},
        actor="user:rekvizitor",
        source="cli",
    )
    raw_ev2 = {
        "event_id": "evt_prj_tamper_hash_chain_2_test",
        "schema_version": "power.project-event.v1",
        "project_id": "prj_tamper_hash_chain",
        "sequence": 2,
        "timestamp": "2026-09-03T18:00:00Z",
        "actor": cmd2.actor,
        "source": cmd2.source,
        "session_id": None,
        "event_type": cmd2.event_type,
        "payload": cmd2.payload,
        "payload_digest": compute_payload_digest(cmd2.payload),
        "prev_event_hash": "0000000000000000000000000000000000000000000000000000000000000000",  # Fake!
        "artifact_refs": [],
        "evidence_refs": [],
        "correlation_id": None,
        "causation_id": None,
        "idempotency_key": None,
    }
    raw_ev2["event_hash"] = compute_event_hash(raw_ev2)

    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write(canonical_json_dumps(raw_ev2) + "\n")

    res = store.verify()
    assert res.valid is False
    assert any("Broken prev_event_hash" in err for err in res.errors)


# ==============================================================================
# 9. Project Isolation, Path Traversal & Symlink Escape Tests (Gate G2.5)
# ==============================================================================


def test_path_traversal_rejection(vault_root: Path) -> None:
    bad_project_ids = [
        "../escape",
        "prj_../../escape",
        "prj_nested/project",
        "prj_nested\\project",
        "prj_UPPERCASE",
        "prj_with space",
        "invalid_without_prefix",
    ]
    for bad_id in bad_project_ids:
        with pytest.raises(ValueError, match=r"project_id|traversal|format|prefix"):
            validate_project_id(bad_id)

        with pytest.raises(ValueError, match=r"project_id|traversal|format|prefix"):
            get_project_dir(bad_id, vault_root)

        with pytest.raises(ValueError, match=r"project_id|traversal|format|prefix"):
            ProjectEventStore(bad_id, vault_root)


def test_symlink_escape_rejection(vault_root: Path, tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()

    # 1. Symlink on vault_root itself
    symlink_vault = tmp_path / "symlink_vault"
    symlink_vault.symlink_to(vault_root)
    with pytest.raises(ValueError, match="symlink"):
        ProjectEventStore("prj_symlink_root", symlink_vault)

    # 2. Symlink on .power
    vault_root_2 = tmp_path / "vault_2"
    vault_root_2.mkdir()
    (vault_root_2 / ".power").symlink_to(outside_dir)
    with pytest.raises(ValueError, match="symlink"):
        ProjectEventStore("prj_symlink_power", vault_root_2)

    # 3. Symlink on .power/projects
    vault_root_3 = tmp_path / "vault_3"
    (vault_root_3 / ".power").mkdir(parents=True)
    (vault_root_3 / ".power" / "projects").symlink_to(outside_dir)
    with pytest.raises(ValueError, match="symlink"):
        ProjectEventStore("prj_symlink_projects", vault_root_3)

    # 4. Symlink directory for project
    projects_dir = vault_root / ".power" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    symlink_proj = projects_dir / "prj_symlink"
    symlink_proj.symlink_to(outside_dir)
    with pytest.raises(ValueError, match="symlink"):
        get_project_dir("prj_symlink", vault_root)

    # 5. Symlink lock file rejection
    real_proj = projects_dir / "prj_real"
    real_proj.mkdir()
    outside_lock = outside_dir / "fake.lock"
    outside_lock.touch()
    (real_proj / ".lock").symlink_to(outside_lock)
    with pytest.raises(ValueError, match="symlink"), project_lock("prj_real", vault_root):
        pass


def test_rotation_rejects_path_traversal_and_invalid_names(vault_root: Path) -> None:
    """rotate() must reject path traversal (..), path separators, and non-conforming names."""
    store = ProjectEventStore("prj_rotate_security", vault_root)
    store.append(
        AppendCommand(
            project_id="prj_rotate_security",
            event_type="project.created",
            payload={"name": "Rotation Security"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Path traversal ../
    with pytest.raises(ValueError, match=r"Invalid archive_name"):
        store.rotate(archive_name="../../events_000001.jsonl")

    # Separator
    with pytest.raises(ValueError, match=r"Invalid archive_name"):
        store.rotate(archive_name="sub/events_000001.jsonl")

    # Non-conforming filename
    with pytest.raises(ValueError, match=r"Invalid archive_name"):
        store.rotate(archive_name="events_custom.jsonl")


# ==============================================================================
# 10. Rotation Tests
# ==============================================================================


def test_ledger_rotation_and_seamless_replay(vault_root: Path) -> None:
    store = ProjectEventStore("prj_rotation", vault_root)

    # Write 5 events to active ledger
    for i in range(1, 6):
        store.append(
            AppendCommand(
                project_id="prj_rotation",
                event_type="project.updated",
                payload={"iter": i},
                actor="user:rekvizitor",
                source="cli",
            )
        )

    assert len(list(store.replay())) == 5

    # Rotate active ledger
    archived_file = store.rotate()
    assert archived_file is not None
    assert archived_file.exists()
    assert "events_000001.jsonl" in archived_file.name

    # Write 5 more events to the new active ledger
    for i in range(6, 11):
        store.append(
            AppendCommand(
                project_id="prj_rotation",
                event_type="project.updated",
                payload={"iter": i},
                actor="user:rekvizitor",
                source="cli",
            )
        )

    # Replay must seamlessly span both files in order 1..10
    all_events = list(store.replay(from_sequence=1))
    assert len(all_events) == 10
    assert [e.sequence for e in all_events] == list(range(1, 11))

    # Verify cryptographic integrity across rotated files
    res = store.verify()
    assert res.valid is True
    assert res.event_count == 10
    assert res.last_sequence == 10


# ==============================================================================
# 11. Disposable Derived Index Rebuild Tests (Gate G2.6)
# ==============================================================================


def test_derived_index_rebuild_from_canonical_ledger(vault_root: Path) -> None:
    pid = "prj_rebuild"
    store = ProjectEventStore(pid, vault_root)
    cmd1 = AppendCommand(
        project_id=pid,
        event_type="project.created",
        payload={"name": "Rebuild Target Project", "description": "Derived index test"},
        actor="user:rekvizitor",
        source="cli",
    )
    update_derived_index_for_event(vault_root, store.append_untrusted(cmd1))

    cmd2 = AppendCommand(
        project_id=pid,
        event_type="project.phase.changed",
        payload={"new_phase": "phase_1_discovery"},
        actor="user:rekvizitor",
        source="cli",
    )
    update_derived_index_for_event(vault_root, store.append_untrusted(cmd2))

    cmd3 = AppendCommand(
        project_id=pid,
        event_type="raci.assigned",
        payload={"role": "Accountable", "actor": "user:rekvizitor"},
        actor="user:rekvizitor",
        source="cli",
    )
    update_derived_index_for_event(vault_root, store.append_untrusted(cmd3))

    cmd4 = AppendCommand(
        project_id=pid,
        event_type="dod.evaluated",
        payload={"phase": "phase_1_discovery", "passed": True, "criteria": ["tests pass"]},
        actor="agent:agy",
        source="internal_engine",
    )
    update_derived_index_for_event(vault_root, store.append_untrusted(cmd4))

    db_path = vault_root / ".power" / "project-state" / "indexes" / "project_state.sqlite3"
    assert db_path.exists()

    # Delete the SQLite database file completely
    db_path.unlink()
    assert not db_path.exists()

    # Rebuild from canonical events
    rebuilt_count = rebuild_derived_index(vault_root, project_id=pid)
    assert rebuilt_count == 4
    assert db_path.exists()

    # Verify tables in recreated SQLite
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT project_id, name, current_phase, last_sequence FROM projects WHERE project_id = ?",
            (pid,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == pid
        assert row[1] == "Rebuild Target Project"
        assert row[2] == "phase_1_discovery"
        assert row[3] == 4

        cur.execute("SELECT role, actor FROM raci_assignments WHERE project_id = ?", (pid,))
        raci_row = cur.fetchone()
        assert raci_row == ("Accountable", "user:rekvizitor")

        cur.execute("SELECT gate_type, passed FROM gate_evaluations WHERE project_id = ?", (pid,))
        gate_row = cur.fetchone()
        assert gate_row == ("dod", 1)
    finally:
        conn.close()

    # Verify materialized status markdown
    status_md = vault_root / ".power" / "projects" / pid / "status.md"
    assert status_md.exists()
    content = status_md.read_text(encoding="utf-8")
    assert "<!-- GENERATED BY POWER PSE - DO NOT EDIT MANUALLY -->" in content
    assert pid in content
    assert "Last Sequence:** 4" in content


# ==============================================================================
# 12. Secret Redaction Pipeline Fixtures & RedactionRecord
# ==============================================================================


def test_secret_redaction_pipeline_fixtures() -> None:
    raw_payload = {
        "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA\n-----END OPENSSH PRIVATE KEY-----",
        "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMC6Y5",
        "gh_token": "ghp_AbCdEf0123456789AbCdEf0123456789",
        "aws_key": "AKIAIOSFODNN7EXAMPLE",
        "env_content": "PASSWORD=super_secret_password_123\nGITHUB_TOKEN=ghp_secret_token_123456789",
        "config": {"api_key": "my_super_secret_api_key_value_12345"},
        "clean_field": "Normal public text with zero secrets",
    }

    sanitized, record = redact_secrets(raw_payload)

    assert isinstance(record, RedactionRecord)
    assert record.replacements_count >= 6
    assert "private_key" in record.detected_secret_classes
    assert "bearer_token" in record.detected_secret_classes
    assert "github_token" in record.detected_secret_classes
    assert "aws_access_key" in record.detected_secret_classes
    assert "env_secret" in record.detected_secret_classes

    # Ensure no actual secrets are in sanitized output
    assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in str(sanitized)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in str(sanitized)
    assert "ghp_AbCdEf0123456789AbCdEf0123456789" not in str(sanitized)
    assert "AKIAIOSFODNN7EXAMPLE" not in str(sanitized)
    assert "super_secret_password_123" not in str(sanitized)
    assert "my_super_secret_api_key_value_12345" not in str(sanitized)

    # Clean field preserved
    assert sanitized["clean_field"] == "Normal public text with zero secrets"


# ==============================================================================
# 13. Privacy Modes Verification (Gate G2.7)
# ==============================================================================


def test_privacy_modes_verification(vault_root: Path) -> None:
    pid = "prj_privacy"

    # 1. Metadata-Only Mode
    cmd_meta = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload={
            "name": "Secret Project",
            "confidential_rationale": "Deep proprietary strategy",
            "internal_ip": "10.0.0.1",
        },
        actor="user:rekvizitor",
        source="cli",
    )
    ev_meta = append_project_event(vault_root, cmd_meta, privacy_mode=PrivacyMode.METADATA_ONLY)
    assert ev_meta.payload["_privacy_mode"] == "metadata-only"
    assert "confidential_rationale" not in ev_meta.payload
    assert ev_meta.payload["keys"] == ["confidential_rationale", "internal_ip", "name"]

    # 2. Structured-Events Mode (Default): dialogue buffers purged
    cmd_struct = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload={
            "summary": "Phase milestone achieved",
            "raw_dialogue": "Agent: How are you? User: Please fix this bug.",
            "transcript": "Turn 1... Turn 2...",
        },
        actor="agent:agy",
        source="internal_engine",
    )
    ev_struct = append_project_event(
        vault_root, cmd_struct, privacy_mode=PrivacyMode.STRUCTURED_EVENTS
    )
    assert ev_struct.payload["summary"] == "Phase milestone achieved"
    assert "raw_dialogue" not in ev_struct.payload
    assert "transcript" not in ev_struct.payload

    # 3. Full-Content Mode (Explicit Opt-In): stores evidence locally under 0600
    cmd_full = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload={"note": "Full evidence audit"},
        actor="user:rekvizitor",
        source="cli",
    )
    raw_dialogue = {"turns": ["User: Hello", "Agent: Initialized"]}
    ev_full = append_project_event(
        vault_root,
        cmd_full,
        privacy_mode=PrivacyMode.FULL_CONTENT,
        raw_content=raw_dialogue,
        raw_evidence_ttl_days=14,
    )
    assert len(ev_full.evidence_refs) == 1
    evidence_ref = ev_full.evidence_refs[0]
    assert evidence_ref.startswith("sha256:")

    evidence_file = vault_root / ".power" / "raw-evidence" / pid / f"{ev_full.event_id}.json"
    assert evidence_file.exists()
    # Check permissions 0600
    stat_mode = evidence_file.stat().st_mode & 0o777
    assert stat_mode == 0o600


# ==============================================================================
# 14. Cross-Subsystem Association Sagas and Reconciliation (ADR-PSE-008)
# ==============================================================================


class MockTaskService:
    def __init__(self, existing_task_ids: set[str]) -> None:
        self.existing_task_ids = existing_task_ids

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if task_id in self.existing_task_ids:
            return {"task_id": task_id, "state": "working"}
        return None


class MockDecisionService:
    def __init__(self, existing_decision_ids: set[str]) -> None:
        self.existing_decision_ids = existing_decision_ids

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        if decision_id in self.existing_decision_ids:
            return {"decision_id": decision_id, "status": "approved"}
        return None


def test_cross_subsystem_reconciliation_saga(vault_root: Path) -> None:
    pid = "prj_sagas"

    # 1. Request task association for existing task
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid,
            event_type="task.association.requested",
            payload={"project_id": pid, "task_id": "tsk_valid_123", "relation": "contributes_to"},
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_task_1",
            idempotency_key="idem_task_1",
        ),
    )

    # 2. Request task association for missing task
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid,
            event_type="task.association.requested",
            payload={"project_id": pid, "task_id": "tsk_missing_999", "relation": "contributes_to"},
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_task_2",
            idempotency_key="idem_task_2",
        ),
    )

    # 3. Request decision association for existing decision
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid,
            event_type="decision.association.requested",
            payload={"project_id": pid, "decision_id": "dec_valid_456", "relation": "governs"},
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_dec_1",
            idempotency_key="idem_dec_1",
        ),
    )

    task_service = MockTaskService(existing_task_ids={"tsk_valid_123"})
    decision_service = MockDecisionService(existing_decision_ids={"dec_valid_456"})

    report = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        decision_service=decision_service,
        max_attempts=1,
    )

    assert report["reconciled_tasks"] == 1
    assert report["failed_tasks"] == 1
    assert report["reconciled_decisions"] == 1
    assert report["failed_decisions"] == 0

    events = list(replay_project(vault_root, pid))
    event_types = [e.event_type for e in events]
    assert "task.associated" in event_types
    assert "task.association.failed" in event_types
    assert "decision.associated" in event_types

    # Running reconciliation again is fully idempotent (0 pending)
    report_2 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        decision_service=decision_service,
        max_attempts=1,
    )
    assert report_2["reconciled_tasks"] == 0
    assert report_2["failed_tasks"] == 0
    assert report_2["reconciled_decisions"] == 0
    assert report_2["failed_decisions"] == 0


def test_raw_dialogue_prohibited_across_all_privacy_modes(vault_root: Path) -> None:
    """Raw dialogue/transcripts must never enter event payload in any privacy mode (Gate G2.7)."""
    pid = "prj_raw_ban"

    raw_dialogue_payload = {
        "title": "Discussion notes",
        "raw_dialogue": "Secret dialogue line",
        "dialogue_buffer": "Buffer data",
        "transcript": "Full raw transcript",
        "turns": ["turn1", "turn2"],
        "prompt_text": "System prompt",
        "completion_text": "AI completion",
        "messages": [{"role": "user", "content": "secret"}],
        "reasoning": "internal chain of thought",
        "thinking": "hidden thinking block",
        "nested": {
            "transcript": "nested transcript",
            "safe_field": "ok_value",
        },
    }

    # 1. Full-Content mode: extracts dialogue to raw-evidence, keeps payload clean
    cmd_full = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload=raw_dialogue_payload,
        actor="user:rekvizitor",
        source="cli",
    )
    ev_full = append_project_event(vault_root, cmd_full, privacy_mode=PrivacyMode.FULL_CONTENT)

    assert "raw_dialogue" not in ev_full.payload
    assert "dialogue_buffer" not in ev_full.payload
    assert "transcript" not in ev_full.payload
    assert "turns" not in ev_full.payload
    assert "prompt_text" not in ev_full.payload
    assert "completion_text" not in ev_full.payload
    assert "messages" not in ev_full.payload
    assert "reasoning" not in ev_full.payload
    assert "thinking" not in ev_full.payload
    assert ev_full.payload["title"] == "Discussion notes"
    assert ev_full.payload["nested"] == {"safe_field": "ok_value"}
    assert len(ev_full.evidence_refs) == 1

    ev_file = vault_root / ".power" / "raw-evidence" / pid / f"{ev_full.event_id}.json"
    assert ev_file.exists()
    ev_content = ev_file.read_text(encoding="utf-8")
    assert "Full raw transcript" in ev_content
    assert "nested transcript" in ev_content

    # 2. Structured-Events mode: strips dialogue, no raw evidence file
    cmd_struct = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload=raw_dialogue_payload,
        actor="user:rekvizitor",
        source="cli",
    )
    ev_struct = append_project_event(
        vault_root, cmd_struct, privacy_mode=PrivacyMode.STRUCTURED_EVENTS
    )
    assert "transcript" not in ev_struct.payload
    assert ev_struct.payload["title"] == "Discussion notes"
    assert ev_struct.payload["nested"] == {"safe_field": "ok_value"}

    # 3. Metadata-Only mode
    cmd_meta = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload=raw_dialogue_payload,
        actor="user:rekvizitor",
        source="cli",
    )
    ev_meta = append_project_event(vault_root, cmd_meta, privacy_mode=PrivacyMode.METADATA_ONLY)
    assert ev_meta.payload["_privacy_mode"] == "metadata-only"
    assert "transcript" not in ev_meta.payload["keys"]


def test_saga_payload_mandatory_contracts_and_rejections(vault_root: Path) -> None:
    """Mandatory schema validation for all 6 saga event types; rejects empty or invalid payloads."""
    pid = "prj_saga_contracts"

    saga_events_empty = [
        "task.association.requested",
        "task.associated",
        "task.association.failed",
        "decision.association.requested",
        "decision.associated",
        "decision.association.failed",
    ]

    for evt in saga_events_empty:
        # Empty payload must be rejected
        with pytest.raises((ValueError, ValidationError)):
            append_project_event(
                vault_root,
                AppendCommand(
                    project_id=pid,
                    event_type=evt,
                    payload={},
                    actor="user:rekvizitor",
                    source="cli",
                ),
            )

    # Missing mandatory fields
    # task.association.requested missing task_id
    with pytest.raises((ValueError, ValidationError)):
        append_project_event(
            vault_root,
            AppendCommand(
                project_id=pid,
                event_type="task.association.requested",
                payload={"relation": "contributes_to"},
                actor="user:rekvizitor",
                source="cli",
            ),
        )

    # task.association.failed missing reason
    with pytest.raises((ValueError, ValidationError)):
        append_project_event(
            vault_root,
            AppendCommand(
                project_id=pid,
                event_type="task.association.failed",
                payload={"task_id": "tsk_123"},
                actor="user:rekvizitor",
                source="cli",
            ),
        )

    # decision.association.requested missing decision_id
    with pytest.raises((ValueError, ValidationError)):
        append_project_event(
            vault_root,
            AppendCommand(
                project_id=pid,
                event_type="decision.association.requested",
                payload={"relation": "governs"},
                actor="user:rekvizitor",
                source="cli",
            ),
        )

    # decision.association.failed missing reason
    with pytest.raises((ValueError, ValidationError)):
        append_project_event(
            vault_root,
            AppendCommand(
                project_id=pid,
                event_type="decision.association.failed",
                payload={"decision_id": "dec_123"},
                actor="user:rekvizitor",
                source="cli",
            ),
        )


def test_reconciliation_retry_policy_semantics(vault_root: Path) -> None:
    """Test retry policy semantics: attempt < max_attempts stays pending, exhaustion fails, appearance resolves."""
    pid = "prj_reconcile_retry"

    # Request task association for missing task with max_attempts=3
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid,
            event_type="task.association.requested",
            payload={
                "project_id": pid,
                "task_id": "tsk_retry_missing",
                "relation": "contributes_to",
                "max_attempts": 3,
            },
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_retry_task_1",
            idempotency_key="idem_retry_task_1",
        ),
    )

    task_service = MockTaskService(existing_task_ids=set())
    decision_service = MockDecisionService(existing_decision_ids=set())
    attempts_map: dict[str, int] = {}

    # Case 1: First reconciliation run - task is missing, attempt 1 < 3 -> stays pending!
    rep1 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        decision_service=decision_service,
        max_attempts=3,
        attempt_tracker=attempts_map,
    )
    assert rep1["pending_tasks"] == 1
    assert rep1["failed_tasks"] == 0
    assert rep1["reconciled_tasks"] == 0

    # Ensure no failure event was written to ledger
    events = list(replay_project(vault_root, pid))
    assert not any(e.event_type == "task.association.failed" for e in events)

    # Second reconciliation run - task still missing, attempt 2 < 3 -> stays pending!
    rep2 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        decision_service=decision_service,
        max_attempts=3,
        attempt_tracker=attempts_map,
    )
    assert rep2["pending_tasks"] == 1
    assert rep2["failed_tasks"] == 0
    assert not any(
        e.event_type == "task.association.failed" for e in replay_project(vault_root, pid)
    )

    # Case 3: Third reconciliation run - attempt limit reached -> appends task.association.failed!
    rep3 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        decision_service=decision_service,
        max_attempts=3,
        attempt_tracker=attempts_map,
    )
    assert rep3["pending_tasks"] == 0
    assert rep3["failed_tasks"] == 1

    events_after = list(replay_project(vault_root, pid))
    assert any(e.event_type == "task.association.failed" for e in events_after)

    # Case 2: Entity appears before attempt limit is reached
    pid2 = "prj_reconcile_success"
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid2,
            event_type="task.association.requested",
            payload={
                "project_id": pid2,
                "task_id": "tsk_late_arrival",
                "relation": "contributes_to",
                "max_attempts": 3,
            },
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_late_task",
            idempotency_key="idem_late_task",
        ),
    )
    attempts_map2: dict[str, int] = {}
    # Run 1: missing -> pending
    r1 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid2,
        task_service=task_service,
        max_attempts=3,
        attempt_tracker=attempts_map2,
    )
    assert r1["pending_tasks"] == 1
    assert r1["reconciled_tasks"] == 0

    # Task is now registered in task service
    task_service.existing_task_ids.add("tsk_late_arrival")

    # Run 2: task is present -> successfully associates!
    r2 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid2,
        task_service=task_service,
        max_attempts=3,
        attempt_tracker=attempts_map2,
    )
    assert r2["pending_tasks"] == 0
    assert r2["reconciled_tasks"] == 1

    events2 = list(replay_project(vault_root, pid2))
    assert any(e.event_type == "task.associated" for e in events2)
    assert not any(e.event_type == "task.association.failed" for e in events2)


def test_rebuild_derived_index_fails_closed_on_corrupted_ledger(vault_root: Path) -> None:
    """Secondary index rebuild must fail closed (LedgerIntegrityError) if ledger is corrupted."""
    pid = "prj_rebuild_fail_closed"
    store = ProjectEventStore(pid, vault_root)
    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.created",
            payload={"name": "Fail Closed Test"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Tamper event in ledger
    lines = store.active_events_file.read_text(encoding="utf-8").splitlines(keepends=True)
    import json

    rec2 = json.loads(lines[1])
    rec2["event_hash"] = "deadbeef" * 8
    lines[1] = json.dumps(rec2) + "\n"
    store.active_events_file.write_text("".join(lines), encoding="utf-8")

    with pytest.raises(LedgerIntegrityError, match="ledger verification failed"):
        rebuild_derived_index(vault_root, project_id=pid)


def test_idempotency_conflict_raises_error(vault_root: Path) -> None:
    """Appending with the same idempotency_key but different command payload raises IdempotencyConflictError."""
    pid = "prj_idem_conflict"
    store = ProjectEventStore(pid, vault_root)

    cmd1 = AppendCommand(
        project_id=pid,
        event_type="project.updated",
        payload={"action": "start"},
        actor="user:rekvizitor",
        source="cli",
        idempotency_key="key_123",
    )
    store.append(cmd1)

    # Same idempotency_key, different payload
    cmd2 = AppendCommand(
        project_id=pid,
        event_type="project.updated",
        payload={"action": "different_payload"},
        actor="user:rekvizitor",
        source="cli",
        idempotency_key="key_123",
    )
    with pytest.raises(IdempotencyConflictError, match="Idempotency conflict"):
        store.append(cmd2)


def test_materialize_status_markdown_diagnostic_summary(vault_root: Path) -> None:
    """Status markdown must be labeled Diagnostic Ledger Summary and not claim event_type is Current Phase."""
    pid = "prj_status_md"
    cmd = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload={"name": "Status Test"},
        actor="user:rekvizitor",
        source="cli",
    )
    ev = append_project_event(vault_root, cmd)
    status_file = materialize_status_markdown(vault_root, pid, ev)

    assert status_file.exists()
    content = status_file.read_text(encoding="utf-8")

    assert "# Diagnostic Ledger Summary:" in content
    assert "Current Phase:" not in content
    assert f"Last Event Type:** {ev.event_type}" in content
    assert f"Last Sequence:** {ev.sequence}" in content


# ==============================================================================
# 15. Phase 2 Closure Correction Round 2 Regression Tests
# ==============================================================================


def test_import_refuses_corrupted_existing_ledger_with_zero_mutation(vault_root: Path) -> None:
    """import_project_events must call verify() fail-closed and leave disk 100% untouched if ledger is corrupted."""
    pid = "prj_import_corrupt"
    store = ProjectEventStore(pid, vault_root)
    cmd = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload={"name": "Corrupt Import Test"},
        actor="user:rekvizitor",
        source="cli",
    )
    store.append(cmd)

    # Tamper with ledger by appending corrupted JSON
    with open(store.active_events_file, "a", encoding="utf-8") as f:
        f.write('{"broken_json": true\n')

    corrupted_bytes = store.active_events_file.read_bytes()

    next_event = {
        "event_id": f"evt_{pid}_2_1234567890ab",
        "schema_version": "power.project-event.v1",
        "project_id": pid,
        "sequence": 2,
        "timestamp": "2026-09-03T12:00:00Z",
        "actor": "user:rekvizitor",
        "source": "cli",
        "event_type": "observation.recorded",
        "payload": {"name": "Should Not Import"},
        "payload_digest": compute_payload_digest({"name": "Should Not Import"}),
        "prev_event_hash": "a" * 64,
        "event_hash": "b" * 64,
    }

    with pytest.raises(LedgerIntegrityError):
        import_project_events(vault_root, pid, [next_event])

    # Zero mutation on disk
    assert store.active_events_file.read_bytes() == corrupted_bytes


def test_import_all_or_nothing_batch_rejection(vault_root: Path) -> None:
    """If any event in import batch is invalid, reject all with zero disk mutation."""
    pid = "prj_import_batch"
    store = ProjectEventStore(pid, vault_root)
    ev1 = store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.created",
            payload={"name": "Batch Test"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    initial_bytes = store.active_events_file.read_bytes()

    # Valid next event 2
    raw2_cmd = {
        "event_id": f"evt_{pid}_2_000000000002",
        "schema_version": "power.project-event.v1",
        "project_id": pid,
        "sequence": 2,
        "timestamp": "2026-09-03T12:00:01Z",
        "actor": "user:rekvizitor",
        "source": "cli",
        "event_type": "observation.recorded",
        "payload": {"update": 2},
        "payload_digest": compute_payload_digest({"update": 2}),
        "prev_event_hash": ev1.event_hash,
        "event_hash": "0" * 64,
    }
    ev2_obj = ProjectEvent.model_validate(raw2_cmd)
    raw2 = ev2_obj.model_dump()
    raw2["event_hash"] = compute_event_hash(raw2)

    # Invalid event 3 (sequence gap: sequence 4 instead of 3)
    raw3_cmd = {
        "event_id": f"evt_{pid}_4_000000000004",
        "schema_version": "power.project-event.v1",
        "project_id": pid,
        "sequence": 4,
        "timestamp": "2026-09-03T12:00:02Z",
        "actor": "user:rekvizitor",
        "source": "cli",
        "event_type": "observation.recorded",
        "payload": {"update": 4},
        "payload_digest": compute_payload_digest({"update": 4}),
        "prev_event_hash": raw2["event_hash"],
        "event_hash": "0" * 64,
    }
    ev3_obj = ProjectEvent.model_validate(raw3_cmd)
    raw3 = ev3_obj.model_dump()
    raw3["event_hash"] = compute_event_hash(raw3)

    with pytest.raises(ValueError, match="Import sequence gap"):
        import_project_events(vault_root, pid, [raw2, raw3])

    # Assert ev2 was NOT written: zero disk mutation
    assert store.active_events_file.read_bytes() == initial_bytes
    assert list(store.replay()) == [ev1]


def test_import_rejects_raw_dialogue_payload(vault_root: Path) -> None:
    """import_project_events must reject any event containing raw dialogue or LLM transcript data."""
    pid = "prj_import_dialogue"
    store = ProjectEventStore(pid, vault_root)

    forbidden_keys = [
        "raw_dialogue",
        "dialogue_buffer",
        "transcript",
        "turns",
        "prompt_text",
        "completion_text",
        "messages",
        "reasoning",
        "thinking",
    ]
    for key in forbidden_keys:
        bad_event = {
            "event_id": f"evt_{pid}_1_{key}",
            "schema_version": "power.project-event.v1",
            "project_id": pid,
            "sequence": 1,
            "timestamp": "2026-09-03T12:00:00Z",
            "actor": "user:rekvizitor",
            "source": "cli",
            "event_type": "observation.recorded",
            "payload": {key: "leaked conversation transcript"},
            "payload_digest": compute_payload_digest({key: "leaked conversation transcript"}),
            "prev_event_hash": "",
        }
        bad_event["event_hash"] = compute_event_hash(bad_event)

        with pytest.raises(ValueError, match="prohibited raw dialogue"):
            import_project_events(vault_root, pid, [bad_event])

    assert not store.active_events_file.exists() or store.active_events_file.stat().st_size == 0


def test_import_rejects_invalid_saga_payload(vault_root: Path) -> None:
    """import_project_events must validate saga event payloads against SAGA_PAYLOAD_MODELS."""
    pid = "prj_import_saga"
    store = ProjectEventStore(pid, vault_root)

    invalid_saga_event = {
        "event_id": f"evt_{pid}_1_saga",
        "schema_version": "power.project-event.v1",
        "project_id": pid,
        "sequence": 1,
        "timestamp": "2026-09-03T12:00:00Z",
        "actor": "user:rekvizitor",
        "source": "cli",
        "event_type": "task.association.requested",
        "payload": {"project_id": pid},  # missing required task_id!
        "payload_digest": compute_payload_digest({"project_id": pid}),
        "prev_event_hash": "",
    }
    invalid_saga_event["event_hash"] = compute_event_hash(invalid_saga_event)

    with pytest.raises((ValueError, ValidationError)):
        import_project_events(vault_root, pid, [invalid_saga_event])

    assert not store.active_events_file.exists() or store.active_events_file.stat().st_size == 0


GOVERNANCE_BEARING_EVENT_TYPES = (
    "project.created",
    "project.updated",
    "project.phase.changed",
    "project.reopened",
    "raci.assigned",
    "raci.revoked",
    "evidence.attached",
    "artifact.created",
    "artifact.updated",
    "task.associated",
    "task.disassociated",
    "decision.associated",
    "decision.disassociated",
    "dor.evaluated",
    "dod.evaluated",
    "gate.overridden",
)


def _governance_payload(project_id: str, event_type: str) -> dict[str, Any]:
    if event_type == "task.associated":
        return {"project_id": project_id, "task_id": "tsk_import_01"}
    if event_type == "decision.associated":
        return {"project_id": project_id, "decision_id": "dec_import_01"}
    if event_type in {"task.disassociated", "task.lifecycle.observed"}:
        return {"task_id": "tsk_import_01"}
    if event_type in {"decision.disassociated", "decision.lifecycle.observed"}:
        return {"decision_id": "dec_import_01"}
    if event_type == "raci.assigned" or event_type == "raci.revoked":
        return {"role": "Accountable", "actor": "user:importer"}
    if event_type == "evidence.attached":
        return {"evidence_id": "evi_import_01", "evidence_type": "artifact"}
    if event_type in {"artifact.created", "artifact.updated"}:
        return {"artifact_id": "art_import_01", "evidence_type": "artifact"}
    if event_type in {"project.phase.changed", "project.reopened"}:
        return {"target_phase": "PLANNING"}
    if event_type in {"dor.evaluated", "dod.evaluated"}:
        return {"evaluation_type": event_type.removesuffix(".evaluated"), "result": "passed"}
    if event_type == "gate.overridden":
        return {"gate": "gate_import_01", "reason": "import test", "approved_by": "user:importer"}
    return {"name": "import test"}


def _make_import_event(
    project_id: str,
    sequence: int,
    prev_event_hash: str,
    event_type: str,
    payload: dict[str, Any],
) -> ProjectEvent:
    raw: dict[str, Any] = {
        "event_id": f"evt_{project_id}_{sequence:04d}_round3",
        "schema_version": "power.project-event.v1",
        "project_id": project_id,
        "sequence": sequence,
        "timestamp": f"2026-09-05T03:00:{sequence:02d}Z",
        "actor": "user:importer",
        "source": "pse_governance",
        "event_type": event_type,
        "payload": payload,
        "payload_digest": compute_payload_digest(payload),
        "prev_event_hash": prev_event_hash,
        "event_hash": "0" * 64,
    }
    event = ProjectEvent.model_validate(raw)
    event.event_hash = compute_event_hash(event.model_dump())
    return event


def test_import_rejects_self_consistent_governance_chain_before_mutation(
    vault_root: Path,
) -> None:
    """A self-consistent PSE chain is not a generic migration authority."""
    pid = "prj_import_authority"
    store = ProjectEventStore(pid, vault_root)
    existing = store.append(
        AppendCommand(
            project_id=pid,
            event_type="session.started",
            payload={"session": "existing"},
            actor="user:importer",
            source="cli",
        )
    )
    before_bytes = store.active_events_file.read_bytes()
    before_count = store.verify().event_count

    events: list[ProjectEvent] = []
    prev_hash = existing.event_hash
    for sequence, event_type in enumerate(
        ("project.created", "evidence.attached", "dor.evaluated", "project.phase.changed"),
        start=2,
    ):
        event = _make_import_event(
            pid,
            sequence,
            prev_hash,
            event_type,
            _governance_payload(pid, event_type),
        )
        events.append(event)
        prev_hash = event.event_hash

    with pytest.raises(PermissionError, match="governance-bearing"):
        import_project_events(vault_root, pid, events)

    assert store.verify().event_count == before_count
    assert store.active_events_file.read_bytes() == before_bytes
    assert [event.sequence for event in store.replay()] == [1]


@pytest.mark.parametrize("event_type", GOVERNANCE_BEARING_EVENT_TYPES)
def test_import_rejects_every_governance_type_before_append(
    vault_root: Path, event_type: str
) -> None:
    """The generic import boundary rejects every canonical governance event type."""
    pid = f"prj_import_{event_type.replace('.', '_')}"
    event = _make_import_event(pid, 1, "", event_type, _governance_payload(pid, event_type))
    store = ProjectEventStore(pid, vault_root)

    with pytest.raises(PermissionError, match="governance-bearing"):
        import_project_events(vault_root, pid, [event])

    assert store.verify().event_count == 0
    assert not store.active_events_file.exists()


@pytest.mark.parametrize("event_type", GOVERNANCE_BEARING_EVENT_TYPES)
def test_generic_append_rejects_every_governance_type_before_append(
    vault_root: Path, event_type: str
) -> None:
    """Generic append cannot place governance claims into the authoritative ledger."""
    pid = f"prj_append_{event_type.replace('.', '_')}"
    command = AppendCommand(
        project_id=pid,
        event_type=event_type,
        payload=_governance_payload(pid, event_type),
        actor="user:importer",
        source="cli",
    )

    with pytest.raises(PermissionError, match="governance-bearing"):
        append_project_event(
            vault_root,
            command,
            privacy_mode=PrivacyMode.FULL_CONTENT,
            raw_content={"transcript": "must not be stored"},
        )

    store = ProjectEventStore(pid, vault_root)
    assert store.verify().event_count == 0
    assert not store.active_events_file.exists()
    assert not (vault_root / ".power" / "raw-evidence" / pid).exists()


def test_evidence_retry_with_changed_content_raises_idempotency_conflict(vault_root: Path) -> None:
    """If a retry comes in with the same idempotency_key but different raw content/evidence, raise IdempotencyConflictError."""
    pid = "prj_ev_retry"
    cmd1 = AppendCommand(
        project_id=pid,
        event_type="observation.recorded",
        payload={"name": "Evidence Test"},
        actor="user:rekvizitor",
        source="cli",
        idempotency_key="key_ev_retry",
    )
    ev1 = append_project_event(
        vault_root,
        cmd1,
        privacy_mode=PrivacyMode.FULL_CONTENT,
        raw_content={"chat": "original content"},
    )
    assert ev1.idempotency_key == "key_ev_retry"
    assert len(ev1.evidence_refs) == 1

    # Retry with identical content succeeds idempotently
    ev1_retry = append_project_event(
        vault_root,
        cmd1,
        privacy_mode=PrivacyMode.FULL_CONTENT,
        raw_content={"chat": "original content"},
    )
    assert ev1_retry.event_id == ev1.event_id

    # Retry with same idempotency_key but CHANGED raw content raises IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        append_project_event(
            vault_root,
            cmd1,
            privacy_mode=PrivacyMode.FULL_CONTENT,
            raw_content={"chat": "MODIFIED content"},
        )


def test_evidence_atomic_0600_permissions_and_durability(vault_root: Path) -> None:
    """store_raw_evidence creates files with 0600 mode and protects against overwrite."""
    pid = "prj_ev_perm"
    ref = store_raw_evidence(vault_root, pid, "evt_perm_1", {"unredacted_field": "data"})
    assert ref.startswith("sha256:")

    ev_dir = _get_raw_evidence_dir(vault_root, pid)
    ev_file = ev_dir / "evt_perm_1.json"
    assert ev_file.exists()
    assert stat.S_IMODE(ev_file.stat().st_mode) == 0o600

    # Idempotent re-store with same content succeeds
    ref2 = store_raw_evidence(vault_root, pid, "evt_perm_1", {"unredacted_field": "data"})
    assert ref2 == ref

    # Attempt to re-store with different content raises IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        store_raw_evidence(vault_root, pid, "evt_perm_1", {"unredacted_field": "tampered"})


def test_rotation_rejects_gapped_or_invalid_partition_numbers(vault_root: Path) -> None:
    """rotate() must reject gapped archive names and enforce monotonic partition numbering."""
    pid = "prj_rot_gaps"
    store = ProjectEventStore(pid, vault_root)
    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.created",
            payload={"name": "Rot Gaps"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Attempt gapped archive name
    with pytest.raises(ValueError, match="sequential without gaps"):
        store.rotate(archive_name="events_000003.jsonl")

    # Attempt non-conforming or huge gap
    with pytest.raises(ValueError, match="sequential without gaps"):
        store.rotate(archive_name="events_999999.jsonl")

    # Valid rotation
    p1 = store.rotate()
    assert p1 is not None
    assert p1.name == "events_000001.jsonl"

    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Attempt gap at partition 2
    with pytest.raises(ValueError, match="sequential without gaps"):
        store.rotate(archive_name="events_000003.jsonl")

    # Explicit matching name succeeds
    p2 = store.rotate(archive_name="events_000002.jsonl")
    assert p2 is not None
    assert p2.name == "events_000002.jsonl"


def test_replay_enforces_strict_rotation_filename_pattern(vault_root: Path) -> None:
    """list_event_files and replay must match strict ^events_[0-9]{6}\\.jsonl$ pattern and ignore foreign files."""
    pid = "prj_rot_pattern"
    store = ProjectEventStore(pid, vault_root)

    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.created",
            payload={"name": "Replay Pattern"},
            actor="user:rekvizitor",
            source="cli",
        )
    )
    store.rotate()
    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.updated",
            payload={"step": 2},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # Drop foreign files into project directory
    (store.project_dir / "events_fake.jsonl").write_text("invalid json\n", encoding="utf-8")
    (store.project_dir / "events_999999_backup.jsonl").write_text(
        "invalid json\n", encoding="utf-8"
    )
    (store.project_dir / "events_12.jsonl").write_text("invalid json\n", encoding="utf-8")
    (store.project_dir / "random_notes.txt").write_text("notes\n", encoding="utf-8")

    files = store.list_event_files()
    assert len(files) == 2
    assert files[0].name == "events_000001.jsonl"
    assert files[1].name == "events.jsonl"

    events = list(store.replay())
    assert len(events) == 2
    assert [e.sequence for e in events] == [1, 2]


def test_reconciliation_retry_state_survives_process_restart(vault_root: Path) -> None:
    """True crash/restart scenario: each retry appends a new requested event to canonical ledger.

    Reconciliation retry count must survive complete in-memory state wipes across multiple attempts.
    """
    pid = "prj_recon_restart"
    # Initial task.association.requested (attempt=1)
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid,
            event_type="task.association.requested",
            payload={
                "project_id": pid,
                "task_id": "tsk_missing_restart",
                "relation": "contributes_to",
                "max_attempts": 3,
            },
            actor="system:test",
            source="cli",
            correlation_id="corr_restart_task_1",
        ),
    )

    task_service = MockTaskService(existing_task_ids=set())

    # Run #1 -> returns pending and writes requested attempt=2 to canonical ledger
    report_1 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        max_attempts=3,
    )
    assert report_1["pending_tasks"] == 1
    assert report_1["failed_tasks"] == 0
    assert report_1["reconciled_tasks"] == 0

    events_after_1 = list(replay_project(vault_root, pid))
    assert len(events_after_1) == 2
    assert events_after_1[1].event_type == "task.association.requested"
    assert events_after_1[1].payload.get("attempt") == 2

    # Simulate process crash / restart: wipe ALL in-memory tracker state
    _reconciliation_attempts.clear()

    # Run #2 -> reads 2 attempts from canonical ledger, returns pending, writes requested attempt=3
    report_2 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        max_attempts=3,
    )
    assert report_2["pending_tasks"] == 1
    assert report_2["failed_tasks"] == 0
    assert report_2["reconciled_tasks"] == 0

    events_after_2 = list(replay_project(vault_root, pid))
    assert len(events_after_2) == 3
    assert events_after_2[2].event_type == "task.association.requested"
    assert events_after_2[2].payload.get("attempt") == 3

    # Simulate process crash / restart again: wipe ALL in-memory tracker state
    _reconciliation_attempts.clear()

    # Run #3 -> attempts exhausted (3 >= 3), appends task.association.failed
    report_3 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        task_service=task_service,
        max_attempts=3,
    )
    assert report_3["failed_tasks"] == 1
    assert report_3["pending_tasks"] == 0
    assert report_3["reconciled_tasks"] == 0

    events_after_3 = list(replay_project(vault_root, pid))
    assert len(events_after_3) == 4
    assert events_after_3[3].event_type == "task.association.failed"
    assert "after 3 attempts" in events_after_3[3].payload.get("reason", "")


def test_reconciliation_decision_retry_state_survives_process_restart(vault_root: Path) -> None:
    """Decision saga true crash/restart scenario surviving in-memory state wipes."""
    pid = "prj_recon_restart_dec"
    # Initial decision.association.requested (attempt=1)
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid,
            event_type="decision.association.requested",
            payload={
                "project_id": pid,
                "decision_id": "dec_missing_restart",
                "relation": "governs",
                "max_attempts": 3,
            },
            actor="system:test",
            source="cli",
            correlation_id="corr_restart_dec_1",
        ),
    )

    decision_service = MockDecisionService(existing_decision_ids=set())

    # Run #1 -> returns pending and writes requested attempt=2 to canonical ledger
    report_1 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        decision_service=decision_service,
        max_attempts=3,
    )
    assert report_1["pending_decisions"] == 1
    assert report_1["failed_decisions"] == 0
    assert report_1["reconciled_decisions"] == 0

    events_after_1 = list(replay_project(vault_root, pid))
    assert len(events_after_1) == 2
    assert events_after_1[1].event_type == "decision.association.requested"
    assert events_after_1[1].payload.get("attempt") == 2

    # Simulate process crash / restart
    _reconciliation_attempts.clear()

    # Run #2 -> reads 2 attempts from ledger, returns pending, writes requested attempt=3
    report_2 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        decision_service=decision_service,
        max_attempts=3,
    )
    assert report_2["pending_decisions"] == 1
    assert report_2["failed_decisions"] == 0
    assert report_2["reconciled_decisions"] == 0

    events_after_2 = list(replay_project(vault_root, pid))
    assert len(events_after_2) == 3
    assert events_after_2[2].event_type == "decision.association.requested"
    assert events_after_2[2].payload.get("attempt") == 3

    # Simulate process crash / restart
    _reconciliation_attempts.clear()

    # Run #3 -> attempts exhausted (3 >= 3), appends decision.association.failed
    report_3 = reconcile_project_subsystems(
        vault_root=vault_root,
        project_id=pid,
        decision_service=decision_service,
        max_attempts=3,
    )
    assert report_3["failed_decisions"] == 1
    assert report_3["pending_decisions"] == 0
    assert report_3["reconciled_decisions"] == 0

    events_after_3 = list(replay_project(vault_root, pid))
    assert len(events_after_3) == 4
    assert events_after_3[3].event_type == "decision.association.failed"
    assert "after 3 attempts" in events_after_3[3].payload.get("reason", "")


def test_reconciliation_correlation_id_isolation_across_projects(vault_root: Path) -> None:
    """Reconciliation retry tracking must isolate (project_id, kind, entity_id, correlation_id)."""
    pid_a = "prj_iso_a"
    pid_b = "prj_iso_b"

    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid_a,
            event_type="task.association.requested",
            payload={"project_id": pid_a, "task_id": "tsk_a", "relation": "contributes_to"},
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_shared",
        ),
    )
    append_project_event(
        vault_root,
        AppendCommand(
            project_id=pid_b,
            event_type="task.association.requested",
            payload={"project_id": pid_b, "task_id": "tsk_b", "relation": "contributes_to"},
            actor="user:rekvizitor",
            source="cli",
            correlation_id="corr_shared",
        ),
    )

    task_service = MockTaskService(existing_task_ids={"tsk_a"})

    rep_a = reconcile_project_subsystems(
        vault_root, pid_a, task_service=task_service, max_attempts=3
    )
    assert rep_a["reconciled_tasks"] == 1

    rep_b = reconcile_project_subsystems(
        vault_root, pid_b, task_service=task_service, max_attempts=3
    )
    assert rep_b["pending_tasks"] == 1
    assert rep_b["reconciled_tasks"] == 0


def test_nested_distinct_level3_project_locks_rejected(vault_root: Path) -> None:
    """Acquiring a Level 3 lock for project_B while holding project_A must raise LockHierarchyViolationError."""
    with project_lock("prj_lock_a", vault_root):
        # Reentrancy for same project succeeds
        with project_lock("prj_lock_a", vault_root):
            pass

        # Acquiring distinct Level 3 project lock is rejected to prevent cross-project deadlocks
        with (
            pytest.raises(
                LockHierarchyViolationError, match="Cross-project nested locks are forbidden"
            ),
            project_lock("prj_lock_b", vault_root),
        ):
            pass


def test_metadata_only_saga_preserves_structural_contracts(vault_root: Path) -> None:
    """Saga events under metadata-only privacy mode must preserve structural identifiers."""
    pid = "prj_meta_saga"
    cmd = AppendCommand(
        project_id=pid,
        event_type="task.association.requested",
        payload={"project_id": pid, "task_id": "tsk_meta_1", "relation": "contributes_to"},
        actor="user:rekvizitor",
        source="cli",
    )
    ev = append_project_event(vault_root, cmd, privacy_mode=PrivacyMode.METADATA_ONLY)
    assert ev.payload["task_id"] == "tsk_meta_1"
    assert ev.payload["relation"] == "contributes_to"

    # Ledger integrity passes without contract failure
    store = ProjectEventStore(pid, vault_root)
    assert store.verify().valid is True


def test_symlink_escape_audit_across_all_phase2_writable_paths(
    vault_root: Path, tmp_path: Path
) -> None:
    """Verify symlink defenses across all Phase 2 writable paths and files."""
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "target.txt"
    outside_file.touch()

    pid = "prj_symlink_audit"
    store = ProjectEventStore(pid, vault_root)
    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.created",
            payload={"name": "Symlink Audit"},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # 1. Active events file as symlink
    active_file = store.active_events_file
    active_file.unlink()
    active_file.symlink_to(outside_file)
    with pytest.raises(ValueError, match="symlink"):
        store.append(
            AppendCommand(
                project_id=pid,
                event_type="project.updated",
                payload={"update": 1},
                actor="user:rekvizitor",
                source="cli",
            )
        )
    active_file.unlink()
    store.append(
        AppendCommand(
            project_id=pid,
            event_type="project.updated",
            payload={"update": 1},
            actor="user:rekvizitor",
            source="cli",
        )
    )

    # 2. Rotated archive path as symlink
    symlink_archive = store.project_dir / "events_000001.jsonl"
    symlink_archive.symlink_to(outside_file)
    with pytest.raises(ValueError, match="symlink"):
        store.rotate(archive_name="events_000001.jsonl")
    symlink_archive.unlink()

    # 3. Raw evidence file as symlink
    ev_dir = _get_raw_evidence_dir(vault_root, pid)
    symlink_ev = ev_dir / "evt_symlink.json"
    symlink_ev.symlink_to(outside_file)
    with pytest.raises(ValueError, match="symlink"):
        store_raw_evidence(vault_root, pid, "evt_symlink", {"data": "test"})
    symlink_ev.unlink()

    # 4. Status markdown as symlink
    status_file = store.project_dir / "status.md"
    status_file.symlink_to(outside_file)
    ev = next(iter(store.replay()))
    with pytest.raises(ValueError, match="symlink"):
        materialize_status_markdown(vault_root, pid, ev)
    status_file.unlink()

    # 5. SQLite database file as symlink
    db_path = _get_sqlite_path(vault_root)
    if db_path.exists():
        db_path.unlink()
    db_path.symlink_to(outside_file)
    with pytest.raises(ValueError, match="symlink"):
        _get_sqlite_path(vault_root)
    db_path.unlink()


def test_deterministic_event_id_generation_and_regex_safety() -> None:
    """Test deterministic event_id generation from arbitrary complex idempotency keys."""
    pid = "prj_evt_id_test"
    # Idempotency key with ':', '/', spaces, Unicode, and max length 128
    complex_key_1 = "action:create/entity:тест 🚀 123 " + "x" * 80
    assert len(complex_key_1) <= 128

    complex_key_2 = "action:create/entity:тест 🚀 123 " + "y" * 80
    assert len(complex_key_2) <= 128

    # 1. Determinism: same key produces identical ID
    id_1a = generate_deterministic_event_id(pid, complex_key_1)
    id_1b = generate_deterministic_event_id(pid, complex_key_1)
    assert id_1a == id_1b

    # 2. Distinctness: two different keys produce different IDs
    id_2 = generate_deterministic_event_id(pid, complex_key_2)
    assert id_1a != id_2

    # 3. Regex safety: matches ^evt_[a-z0-9_-]{8,64}$ and canonical EVENT_ID_REGEX
    pattern = re.compile(r"^evt_[a-z0-9_-]{8,64}$")
    assert pattern.match(id_1a)
    assert pattern.match(id_2)
    assert re.match(EVENT_ID_REGEX, id_1a)
    assert re.match(EVENT_ID_REGEX, id_2)
    validate_event_id(id_1a)
    validate_event_id(id_2)


def test_command_validation_failure_leaves_zero_orphan_raw_evidence(vault_root: Path) -> None:
    """Failed command or saga validation must not create orphan raw evidence files."""
    pid = "prj_no_orphan_evidence"
    evidence_dir = vault_root / ".power" / "raw-evidence" / pid

    # Invalid saga payload (missing mandatory task_id) with full-content privacy mode
    cmd_invalid = AppendCommand.model_construct(
        project_id=pid,
        event_type="task.association.requested",
        payload={"relation": "contributes_to"},  # missing task_id
        actor="user:rekvizitor",
        source="cli",
        idempotency_key="idem_invalid_saga_key",
    )

    with pytest.raises((ValueError, ValidationError)):
        append_project_event(
            vault_root,
            cmd_invalid,
            privacy_mode=PrivacyMode.FULL_CONTENT,
            raw_content={"transcript": "sensitive dialogue that should not leak as orphan"},
        )

    # Verify zero files created in raw evidence directory
    if evidence_dir.exists():
        files = list(evidence_dir.glob("*.json"))
        assert len(files) == 0, f"Orphan evidence files were created: {files}"
