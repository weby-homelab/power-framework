"""Fault-injection evidence for the unified maintenance transaction boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import power_framework.core.maintenance as maintenance_module
from power_framework.core.maintenance import apply_maintenance_plan, build_maintenance_plan

if TYPE_CHECKING:
    from pathlib import Path


def _write_incomplete_notes(vault: Path, count: int) -> list[Path]:
    note_dir = vault / "01_Projects"
    note_dir.mkdir(parents=True, exist_ok=True)
    notes = []
    for number in range(count):
        note = note_dir / f"Fault-{number}.md"
        note.write_text(f"# Fault {number}\n", encoding="utf-8")
        notes.append(note)
    return notes


@pytest.mark.parametrize("failure_at", [1, 2, 3])
def test_injected_disk_failure_restores_every_source(
    sample_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_at: int,
) -> None:
    """A failure at any write boundary restores all notes touched so far."""
    notes = _write_incomplete_notes(sample_vault, 3)
    before = {note: note.read_bytes() for note in notes}
    plan = build_maintenance_plan(sample_vault)
    assert len(plan.actions) == len(notes)

    original_atomic_write = maintenance_module.atomic_write
    writes = 0

    def fail_at_selected_write(path: Path, content: str, encoding: str = "utf-8") -> None:
        nonlocal writes
        writes += 1
        if writes == failure_at:
            raise OSError(f"injected disk failure at write {failure_at}")
        original_atomic_write(path, content, encoding)

    monkeypatch.setattr(maintenance_module, "atomic_write", fail_at_selected_write)
    with pytest.raises(OSError, match="injected disk failure"):
        apply_maintenance_plan(sample_vault, plan, approved=True)

    assert {note: note.read_bytes() for note in notes} == before


def test_injected_permission_failure_is_write_free(
    sample_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A permission failure before the first write cannot mutate source notes."""
    notes = _write_incomplete_notes(sample_vault, 2)
    before = {note: note.read_bytes() for note in notes}
    plan = build_maintenance_plan(sample_vault)

    def refuse_backup(*args: object, **kwargs: object) -> None:
        raise PermissionError("injected backup permission failure")

    monkeypatch.setattr(maintenance_module, "create_backup", refuse_backup)
    with pytest.raises(PermissionError, match="injected backup permission failure"):
        apply_maintenance_plan(sample_vault, plan, approved=True)

    assert {note: note.read_bytes() for note in notes} == before


def test_stale_writer_rejection_is_a_zero_write_transaction(sample_vault: Path) -> None:
    """A writer changing a planned source causes rejection before mutation."""
    notes = _write_incomplete_notes(sample_vault, 2)
    plan = build_maintenance_plan(sample_vault)
    notes[1].write_bytes(notes[1].read_bytes() + b"concurrent writer\n")
    before = {note: note.read_bytes() for note in notes}

    with pytest.raises(RuntimeError, match="stale"):
        apply_maintenance_plan(sample_vault, plan, approved=True)

    assert {note: note.read_bytes() for note in notes} == before
