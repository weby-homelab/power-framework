"""Crash-recovery transaction manifest tests for Task canonical state (Phase B/C/J).

These prove that a hard process kill leaving a ``prepared`` manifest with a
partially-written artifact is deterministically rolled back on the next process
start, and that a ``committed`` leftover manifest is reconciled without data loss.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from power_framework.core.task_service import TaskService

if TYPE_CHECKING:
    from pathlib import Path

    from power_framework.core.task_store import TaskStore


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(store: TaskStore, tx_id: str, stage: str, touched: list[dict]) -> Path:
    tx_dir = store.tx_dir / tx_id
    tx_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "tx_id": tx_id,
        "op": "task_created",
        "idempotency_key": "k1",
        "command_sha256": "deadbeef",
        "stage": stage,
        "created_at": datetime.now(UTC).isoformat(),
        "vault": str(store.vault_dir),
        "touched": touched,
    }
    (tx_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return tx_dir


def test_prepared_orphan_snapshot_is_rolled_back(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    svc = TaskService(vault)
    # Normal create (manifest cleaned up on success).
    svc.create_task(task_id="T1", title="x", idempotency_key="k1")
    store = svc.store

    # Simulate a hard kill: snapshot present, event never written.
    store._events_file("T1").unlink(missing_ok=True)
    assert store.get_task("T1") is not None
    assert len(store.get_task_events("T1")) == 0

    # Leave a prepared manifest referencing the partial write.
    _write_manifest(
        store,
        "tx_sim",
        "prepared",
        [
            {"label": "snapshot", "rel": ".power/tasks/T1.json", "preimage_digest": None},
            {"label": "event", "rel": ".power/tasks/events/T1.jsonl", "preimage_digest": None},
        ],
    )

    results = store.recover()
    assert any(r["status"] == "reconciled_rollback" for r in results)
    # Orphan reclaimed deterministically.
    assert store.get_task("T1") is None
    assert not list(store.tx_dir.iterdir())


def test_committed_leftover_loses_no_data(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    svc = TaskService(vault)
    svc.create_task(task_id="T2", title="y")
    store = svc.store

    snap = store._task_file("T2")
    ev = store._events_file("T2")
    _write_manifest(
        store,
        "tx_done",
        "committed",
        [
            {
                "label": "snapshot",
                "rel": ".power/tasks/T2.json",
                "preimage_digest": None,
                "postimage_digest": _sha256(snap),
            },
            {
                "label": "event",
                "rel": ".power/tasks/events/T2.jsonl",
                "preimage_digest": None,
                "postimage_digest": _sha256(ev),
            },
        ],
    )

    results = store.recover()
    assert any(r["status"] == "committed" for r in results)
    # No data loss, manifest cleaned up.
    assert store.get_task("T2") is not None
    assert len(store.get_task_events("T2")) == 1
    assert not list(store.tx_dir.iterdir())


def test_recovery_runs_on_next_process_lock_and_allows_retry(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    svc = TaskService(vault)
    svc.create_task(task_id="T1", title="x", idempotency_key="k1")
    store = svc.store

    # Partial write + prepared manifest, but DO NOT recover manually.
    store._events_file("T1").unlink(missing_ok=True)
    _write_manifest(
        store,
        "tx_sim2",
        "prepared",
        [
            {"label": "snapshot", "rel": ".power/tasks/T1.json", "preimage_digest": None},
            {"label": "event", "rel": ".power/tasks/events/T1.jsonl", "preimage_digest": None},
        ],
    )

    # A fresh "process" reuses the vault; first lock triggers automatic recovery.
    svc2 = TaskService(vault)
    t = svc2.create_task(task_id="T1", title="x", idempotency_key="k1")
    assert t is not None  # recovery reclaimed the orphan, then created cleanly
    # Idempotent retry with same key returns the same logical result.
    t2 = svc2.create_task(task_id="T1", title="x", idempotency_key="k1")
    assert t2.revision == t.revision
    # Recovery observability record written (Phase K), redacted.
    log = store.recovery_log.read_text(encoding="utf-8").strip().splitlines()
    assert log
    for line in log:
        rec = json.loads(line)
        assert "note" not in rec
        assert "proposal" not in rec


def test_no_manifest_leftover_on_happy_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    svc = TaskService(vault)
    svc.create_task(task_id="T3", title="z")
    svc.transition_task("T3", "ready", expected_revision=1)
    svc.transition_task("T3", "working", expected_revision=2)
    store = svc.store
    # Happy path cleans up every transaction manifest.
    assert not list(store.tx_dir.iterdir())
    assert store.get_task("T3").state == "working"
    assert len(store.get_task_events("T3")) == 3
