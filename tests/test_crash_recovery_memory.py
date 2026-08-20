"""Crash-recovery for memory apply / proposal mutation (Phase E)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from power_framework.core.memory_api import commit_note_change
from power_framework.core.task_store import TaskStore

if TYPE_CHECKING:
    from pathlib import Path

OKF = "---\ntype: Resource\ntitle: N\ndescription: d\ntimestamp: 2026-01-01T00:00:00\n---\n\n"
OLD = OKF + "old\n"
NEW = OKF + "new\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_memory_apply_crash_without_receipt_rolls_back(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    note = vault / "01_Projects" / "n.md"
    note.write_text(OLD, encoding="utf-8")
    store = TaskStore(vault)

    # Simulate a hard kill: note already = NEW on disk, receipt never appended.
    note.write_text(NEW, encoding="utf-8")
    tx_dir = store.tx_dir / "txm"
    tx_dir.mkdir(parents=True)
    manifest = {
        "tx_id": "txm",
        "op": "memory_apply",
        "idempotency_key": "m1",
        "command_sha256": None,
        "stage": "prepared",
        "created_at": datetime.now(UTC).isoformat(),
        "vault": str(vault),
        "touched": [
            {
                "label": "note",
                "rel": "01_Projects/n.md",
                "preimage_digest": _sha256(OLD),
            },
            {
                "label": "history",
                "rel": ".power/memory-history.jsonl",
                "preimage_digest": None,
            },
        ],
    }
    (tx_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (tx_dir / "note.bak").write_bytes(OLD.encode("utf-8"))

    store.recover()
    # Note reverted to preimage; no orphaned mutation.
    assert note.read_text() == OLD

    # Retry with the same idempotency key -> exactly one receipt, no duplicate.
    commit_note_change(vault, "01_Projects/n.md", NEW, idempotency_key="m1")
    history = vault / ".power" / "memory-history.jsonl"
    lines = [line for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
    m1 = [line for line in lines if "m1" in line]
    assert len(m1) == 1
    assert note.read_text() == NEW


def test_memory_happy_path_leaves_no_manifest(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    note = vault / "01_Projects" / "n.md"
    note.write_text(OLD, encoding="utf-8")
    commit_note_change(vault, "01_Projects/n.md", NEW, idempotency_key="m2")
    store = TaskStore(vault)
    assert not list(store.tx_dir.iterdir())
    assert note.read_text() == NEW
