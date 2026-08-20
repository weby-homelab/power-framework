"""Reversible / idempotent v1 -> v2 migration tests (Phase I)."""

from __future__ import annotations

import json
from pathlib import Path

from power_framework.core.task_service import TaskService


def _write_packet(vault: Path, name: str, data: dict) -> None:
    d = vault / ".power" / "work-packets"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")


def test_migration_is_idempotent_and_reversible(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write_packet(vault, "wp1.json", {"task_id": "wp1", "state": "working", "objective": "do x"})
    _write_packet(vault, "wp2.json", {"task_id": "wp2", "state": "submitted", "objective": "do y"})
    svc = TaskService(vault)

    res1 = svc.migrate_v1_work_packets()
    assert res1["migrated"] == 2
    assert res1["skipped"] == 0
    assert svc.get_task("wp1").state == "working"
    assert svc.get_task("wp2") is not None

    # Idempotent re-run.
    res2 = svc.migrate_v1_work_packets()
    assert res2["migrated"] == 0
    assert res2["skipped"] == 2

    # Manifest is content-free (no objective/body).
    manifest = json.loads(Path(res1["manifest"]).read_text(encoding="utf-8"))
    assert all("objective" not in e for e in manifest["entries"])
    assert all("do x" not in json.dumps(e) for e in manifest["entries"])

    # Rollback restores originals and removes migrated tasks.
    rb = svc.rollback_v1_migration()
    assert rb["rolled_back"] == 2
    assert rb["restored"] == 2
    assert svc.get_task("wp1") is None
    assert (vault / ".power" / "work-packets" / "wp1.json").is_file()


def test_migration_manifest_retains_original_bytes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write_packet(vault, "wp1.json", {"task_id": "wp1", "state": "ready"})
    svc = TaskService(vault)
    svc.migrate_v1_work_packets()
    backup = vault / ".power" / "migration" / "v1-backup" / "wp1.json"
    assert backup.is_file()
    # Original evidence preserved verbatim.
    assert backup.read_bytes() == (vault / ".power" / "work-packets" / "wp1.json").read_bytes()
