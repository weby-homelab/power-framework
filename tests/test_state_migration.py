"""Read-only state-plane migration contracts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from power_framework.core.state_migration import (
    STATE_MIGRATION_SCHEMA,
    apply_state_migration_plan,
    build_state_migration_plan,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_state_plan_is_bounded_content_free_and_idempotent(sample_vault: Path) -> None:
    note = sample_vault / "03_Resources" / "state note.md"
    note.write_text(
        "---\ntype: Resource\ntitle: State\ndescription: Hash\ntimestamp: 2026-01-01\n---\nsecret body\n",
        encoding="utf-8",
    )

    first = build_state_migration_plan(sample_vault).as_dict()
    second = build_state_migration_plan(sample_vault).as_dict()

    assert first == second
    assert first["schema_version"] == STATE_MIGRATION_SCHEMA
    assert first["estimated_copy_bytes"] == 0
    assert "secret body" not in json.dumps(first)
    assert all("/root" not in str(entry) for entry in first["entries"])


def test_state_plan_marks_symlink_for_manual_review(sample_vault: Path, tmp_path: Path) -> None:
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = sample_vault / "03_Resources" / "outside.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")

    entries = build_state_migration_plan(sample_vault).entries
    entry = next(item for item in entries if item.relative_path == "03_Resources/outside.txt")
    assert entry.action == "manual-review"
    assert entry.sha256 is None


def test_state_plan_apply_is_fail_closed() -> None:
    with pytest.raises(PermissionError, match="inventory-only"):
        apply_state_migration_plan(object())
