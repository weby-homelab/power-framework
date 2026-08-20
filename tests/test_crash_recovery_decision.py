"""Crash-recovery for Decision canonical state (Phase D)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from power_framework.core.decision_service import DecisionService, _serialize
from power_framework.core.task_service import TaskService

if TYPE_CHECKING:
    from pathlib import Path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_resolve_crash_without_receipt_rolls_back(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    TaskService(vault).create_task(task_id="T1", title="x")
    d = DecisionService(vault)
    d.create_decision(decision_id="dec_D1", task_id="T1", title="approve?", requested_by="a")
    store = d.store

    dfile = d._decision_file("dec_D1")
    pending_bytes = dfile.read_bytes()
    # Simulate a hard kill during resolve: resolved decision written, receipt not.
    resolved = d.get_decision("dec_D1").model_copy(
        update={"status": "approved", "resolved_by": "a", "resolution_action": "approve"}
    )
    dfile.write_text(_serialize(resolved), encoding="utf-8")

    receipt_id = "dcr_" + "0" * 64
    rfile = d._receipt_file(receipt_id)
    tx_dir = store.tx_dir / "txd"
    tx_dir.mkdir(parents=True)
    manifest = {
        "tx_id": "txd",
        "op": "decision_resolve",
        "idempotency_key": None,
        "command_sha256": None,
        "stage": "prepared",
        "created_at": datetime.now(UTC).isoformat(),
        "vault": str(vault),
        "touched": [
            {
                "label": "decision",
                "rel": ".power/tasks/decisions/dec_D1.json",
                "preimage_digest": _sha256(pending_bytes),
            },
            {
                "label": "receipt",
                "rel": f".power/tasks/decisions/receipts/{receipt_id}.json",
                "preimage_digest": None,
            },
        ],
    }
    (tx_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (tx_dir / "decision.bak").write_bytes(pending_bytes)
    # Ensure the crafted receipt rel actually maps to the receipt file path.
    assert (vault / manifest["touched"][1]["rel"]).resolve() == rfile.resolve()

    store.recover()
    assert d.get_decision("dec_D1").status == "pending"
    assert not list(store.tx_dir.iterdir())


def test_decision_happy_path_leaves_no_manifest(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    TaskService(vault).create_task(task_id="T1", title="x")
    d = DecisionService(vault)
    d.create_decision(decision_id="dec_D2", task_id="T1", title="approve?", requested_by="a")
    d.resolve_decision("dec_D2", action="approve", actor="a", authority="apply")
    assert not list(d.store.tx_dir.iterdir())
    assert d.get_decision("dec_D2").status == "approved"
