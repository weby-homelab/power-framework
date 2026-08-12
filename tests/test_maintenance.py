"""Unified maintenance plan/apply safety contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from power_framework.core import (
    apply_maintenance_plan,
    build_maintenance_plan,
)
from power_framework.core import (
    maintenance as maintenance_module,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_incomplete_note(vault: Path, name: str, body: str) -> Path:
    path = vault / "01_Projects" / name
    path.write_text(body, encoding="utf-8")
    return path


def test_maintenance_plan_is_read_only_and_apply_is_hash_bound(sample_vault: Path) -> None:
    note = _write_incomplete_note(sample_vault, "NeedsHealing.md", "# Needs healing\n\nA note.\n")
    before = note.read_text(encoding="utf-8")

    plan = build_maintenance_plan(sample_vault)

    assert note.read_text(encoding="utf-8") == before
    assert len(plan.actions) == 1
    assert plan.actions[0].action_class == "safe_auto"
    assert plan.actions[0].reversible is True

    note.write_text(before + "changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        apply_maintenance_plan(sample_vault, plan, approved=True)
    assert note.read_text(encoding="utf-8") == before + "changed\n"


def test_maintenance_apply_repairs_and_is_idempotent(sample_vault: Path) -> None:
    note = _write_incomplete_note(sample_vault, "Repairable.md", "# Repairable\n")
    plan = build_maintenance_plan(sample_vault)

    receipt = apply_maintenance_plan(sample_vault, plan, approved=True)

    assert receipt.status == "ok"
    assert receipt.applied_action_ids == (plan.actions[0].action_id,)
    assert "type:" in note.read_text(encoding="utf-8")
    assert build_maintenance_plan(sample_vault).actions == ()


def test_retention_findings_remain_plan_only(sample_vault: Path) -> None:
    source = _write_incomplete_note(sample_vault, "BackupSource.md", "original\n")
    backup_dir = source.parent / ".backups"
    backup_dir.mkdir()
    (backup_dir / "BackupSource.20200101_000000_000000.md").write_text("old", encoding="utf-8")

    plan = build_maintenance_plan(
        sample_vault,
        backup_max_count=0,
        backup_max_age_days=None,
        backup_max_bytes=None,
    )

    assert any(action.action_class == "approval_required" for action in plan.actions)
    with pytest.raises(PermissionError, match="plan-only"):
        apply_maintenance_plan(sample_vault, plan, approved=True)


def test_maintenance_restores_prior_action_after_later_write_failure(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _write_incomplete_note(sample_vault, "First.md", "# First\n")
    second = _write_incomplete_note(sample_vault, "Second.md", "# Second\n")
    plan = build_maintenance_plan(sample_vault)
    first_before = first.read_text(encoding="utf-8")
    second_before = second.read_text(encoding="utf-8")
    original_atomic_write = maintenance_module.atomic_write
    writes = 0

    def fail_on_second_write(path: Path, content: str, encoding: str = "utf-8") -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("injected disk fault")
        original_atomic_write(path, content, encoding)

    monkeypatch.setattr(maintenance_module, "atomic_write", fail_on_second_write)
    with pytest.raises(OSError, match="injected disk fault"):
        apply_maintenance_plan(sample_vault, plan, approved=True)

    assert first.read_text(encoding="utf-8") == first_before
    assert second.read_text(encoding="utf-8") == second_before
