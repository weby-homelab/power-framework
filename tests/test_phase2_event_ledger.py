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

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from power_framework.core.canonical_json import (
    canonical_json_dumps,
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.project_ingestion import (
    append_project_event,
    rebuild_derived_index,
    reconcile_project_subsystems,
    redact_secrets,
    replay_project,
)
from power_framework.core.project_models import (
    AppendCommand,
    PrivacyMode,
    ProjectEvent,
    RedactionRecord,
    validate_project_id,
)
from power_framework.core.project_store import (
    LockAcquisitionTimeoutError,
    LockHierarchyTracker,
    ProjectEventStore,
    get_project_dir,
    project_lock,
    recover_torn_tail,
)


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
    """Holding Level 3 lock and attempting to acquire Level 1 or 2 raises RuntimeError."""
    try:
        LockHierarchyTracker.push_level(LockHierarchyTracker.LEVEL_PROJECT)
        with pytest.raises(RuntimeError, match="Lock hierarchy violation"):
            LockHierarchyTracker.push_level(LockHierarchyTracker.LEVEL_TASK)

        with pytest.raises(RuntimeError, match="Lock hierarchy violation"):
            LockHierarchyTracker.push_level(LockHierarchyTracker.LEVEL_MUTATION)
    finally:
        LockHierarchyTracker.pop_level(LockHierarchyTracker.LEVEL_PROJECT)


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
        with pytest.raises(LockAcquisitionTimeoutError), project_lock(project_id, vault_root, timeout=0.2):
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
        f.write('{"event_id":"evt_prj_torn_tail_4_corrupted","sequence":4,"payload":{"partial":"corrupt')

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

    projects_dir = vault_root / ".power" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    # Attempt to create a symlink directory for project
    symlink_proj = projects_dir / "prj_symlink"
    symlink_proj.symlink_to(outside_dir)

    with pytest.raises(ValueError, match="symlink"):
        get_project_dir("prj_symlink", vault_root)

    # Symlink lock file rejection
    real_proj = projects_dir / "prj_real"
    real_proj.mkdir()
    outside_lock = outside_dir / "fake.lock"
    outside_lock.touch()
    (real_proj / ".lock").symlink_to(outside_lock)

    with pytest.raises(ValueError, match="symlink"), project_lock("prj_real", vault_root):
        pass


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
    cmd1 = AppendCommand(
        project_id=pid,
        event_type="project.created",
        payload={"name": "Rebuild Target Project", "description": "Derived index test"},
        actor="user:rekvizitor",
        source="cli",
    )
    append_project_event(vault_root, cmd1)

    cmd2 = AppendCommand(
        project_id=pid,
        event_type="project.phase.changed",
        payload={"new_phase": "phase_1_discovery"},
        actor="user:rekvizitor",
        source="cli",
    )
    append_project_event(vault_root, cmd2)

    cmd3 = AppendCommand(
        project_id=pid,
        event_type="raci.assigned",
        payload={"role": "Accountable", "actor": "user:rekvizitor"},
        actor="user:rekvizitor",
        source="cli",
    )
    append_project_event(vault_root, cmd3)

    cmd4 = AppendCommand(
        project_id=pid,
        event_type="dod.evaluated",
        payload={"phase": "phase_1_discovery", "passed": True, "criteria": ["tests pass"]},
        actor="agent:agy",
        source="internal_engine",
    )
    append_project_event(vault_root, cmd4)

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
        cur.execute("SELECT project_id, name, current_phase, last_sequence FROM projects WHERE project_id = ?", (pid,))
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
        event_type="project.created",
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
        event_type="project.updated",
        payload={
            "summary": "Phase milestone achieved",
            "raw_dialogue": "Agent: How are you? User: Please fix this bug.",
            "transcript": "Turn 1... Turn 2...",
        },
        actor="agent:agy",
        source="internal_engine",
    )
    ev_struct = append_project_event(vault_root, cmd_struct, privacy_mode=PrivacyMode.STRUCTURED_EVENTS)
    assert ev_struct.payload["summary"] == "Phase milestone achieved"
    assert "raw_dialogue" not in ev_struct.payload
    assert "transcript" not in ev_struct.payload

    # 3. Full-Content Mode (Explicit Opt-In): stores evidence locally under 0600
    cmd_full = AppendCommand(
        project_id=pid,
        event_type="project.updated",
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
    )
    assert report_2["reconciled_tasks"] == 0
    assert report_2["failed_tasks"] == 0
    assert report_2["reconciled_decisions"] == 0
    assert report_2["failed_decisions"] == 0
