"""Visible control-plane idempotence and conflict contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from power_framework.core.control_plane import (
    OBSIDIAN_BASE_MARKER,
    build_control_plane,
    build_obsidian_base,
    remove_obsidian_base,
    write_control_plane,
    write_obsidian_base,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_control_plane_is_visible_and_idempotent(sample_vault: Path) -> None:
    first = write_control_plane(sample_vault)
    content = first.read_text(encoding="utf-8")
    second = write_control_plane(sample_vault)

    assert first.name == "POWER_STATUS.md"
    assert second == first
    assert second.read_text(encoding="utf-8") == content
    assert "## Active Work" in content
    assert "## Needs Review" in content
    assert "## Stale Evidence" in content
    assert "## Degraded" in content
    assert "## Recent Change Receipts" in content


def test_control_plane_refuses_manual_file_overwrite(sample_vault: Path) -> None:
    target = sample_vault / "POWER_STATUS.md"
    target.write_text("# human-owned\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="manual control-plane"):
        write_control_plane(sample_vault)


def test_control_plane_render_is_deterministic(sample_vault: Path) -> None:
    assert build_control_plane(sample_vault) == build_control_plane(sample_vault)


def test_obsidian_base_is_valid_optional_asset_and_idempotent(sample_vault: Path) -> None:
    rendered = build_obsidian_base()
    payload = yaml.safe_load(rendered)

    assert rendered.startswith(OBSIDIAN_BASE_MARKER + "\n")
    assert [view["name"] for view in payload["views"]] == [
        "Active Work",
        "Needs Human Decision",
        "Stale Evidence",
        "Recent Changes",
    ]

    first = write_obsidian_base(sample_vault)
    content = first.read_text(encoding="utf-8")
    second = write_obsidian_base(sample_vault)
    assert second == first
    assert second.read_text(encoding="utf-8") == content


def test_obsidian_base_conflict_and_uninstall_never_touch_user_notes(sample_vault: Path) -> None:
    user_note = sample_vault / "Projects" / "human-note.md"
    user_note.parent.mkdir(parents=True)
    user_note.write_text("# human-owned\n", encoding="utf-8")
    write_obsidian_base(sample_vault)

    assert remove_obsidian_base(sample_vault) is True
    assert not (sample_vault / "POWER Control.base").exists()
    assert user_note.read_text(encoding="utf-8") == "# human-owned\n"
    assert remove_obsidian_base(sample_vault) is False

    manual = sample_vault / "POWER Control.base"
    manual.write_text("# human-owned\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="manual Obsidian Base"):
        write_obsidian_base(sample_vault)
    with pytest.raises(FileExistsError, match="manual Obsidian Base"):
        remove_obsidian_base(sample_vault)
