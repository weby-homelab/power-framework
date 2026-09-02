"""Tests for dry-run, idempotent suite integration contracts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from power_framework.core.integrations import (
    apply_mcp_config_integration_plan,
    apply_skill_install_plan,
    build_integrations_doctor,
    build_mcp_config_integration_plan,
    build_skill_check_plan,
    packaged_skill_tree,
)

if TYPE_CHECKING:
    from pathlib import Path


def _managed_mcp_launcher(tmp_path: Path) -> str:
    """Create the exact native-launcher topology required by config plans."""
    home = tmp_path / "managed-home"
    managed = home / ".local" / "share" / "power"
    release = managed / "releases" / "3.7.11-test"
    executable = release / "venv" / "bin" / "power-mcp"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    power_executable = release / "venv" / "bin" / "power"
    power_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    current = managed / "current"
    current.symlink_to(release.relative_to(managed), target_is_directory=True)
    launcher_dir = home / ".local" / "bin"
    launcher_dir.mkdir(parents=True)
    launcher = launcher_dir / "power-mcp"
    launcher.symlink_to(executable)
    (launcher_dir / "power").symlink_to(power_executable)
    (managed / "install.json").write_text(
        json.dumps(
            {
                "status": "applied",
                "current": str(current),
                "release_slot": str(release),
                "venv": str(release / "venv"),
                "launchers": [str(launcher_dir / "power"), str(launcher)],
            }
        ),
        encoding="utf-8",
    )
    return str(launcher)


def test_packaged_skill_tree_is_content_addressed() -> None:
    skill = packaged_skill_tree()
    assert "SKILL.md" in skill.files
    assert len(skill.sha256) == 64
    assert all("__pycache__" not in path and not path.endswith(".pyc") for path in skill.files)
    assert skill.files == packaged_skill_tree().files


def test_skill_install_is_dry_run_atomic_and_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "agent" / "skills" / "power"
    plan = build_skill_check_plan(target)
    assert plan["status"] == "ready"
    assert not target.exists()

    receipt = apply_skill_install_plan(plan, approved=True)
    assert receipt["status"] == "applied"
    assert (target / "SKILL.md").is_file()
    assert build_skill_check_plan(target)["status"] == "no_change"
    second = apply_skill_install_plan(build_skill_check_plan(target), approved=True)
    assert second["status"] == "no_change"


def test_skill_install_ignores_generated_bytecode_cache(tmp_path: Path) -> None:
    target = tmp_path / "agent" / "skills" / "power"
    plan = build_skill_check_plan(target)
    apply_skill_install_plan(plan, approved=True)

    cache = target / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "generated.cpython-314.pyc").write_bytes(b"not skill content")

    cached_plan = build_skill_check_plan(target)
    assert cached_plan["status"] == "no_change"
    assert cached_plan["source"]["tree_sha256"] == plan["source"]["tree_sha256"]


def test_skill_install_never_overwrites_nonmatching_target(tmp_path: Path) -> None:
    target = tmp_path / "skill"
    target.mkdir()
    (target / "user-file.txt").write_text("user content\n", encoding="utf-8")
    plan = build_skill_check_plan(target)
    assert plan["status"] == "manual_review"


def test_skill_install_can_upgrade_only_a_hash_bound_managed_tree(tmp_path: Path) -> None:
    target = tmp_path / "skill"
    source = packaged_skill_tree()
    target.mkdir()
    for relative, content in source.files.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            content + (b"\n" if relative == "references/runtime-contract.md" else b"")
        )

    plan = build_skill_check_plan(target)
    assert plan["status"] == "upgrade_ready"
    receipt = apply_skill_install_plan(plan, approved=True)
    assert receipt["status"] == "applied"
    assert build_skill_check_plan(target)["status"] == "no_change"


def test_mcp_config_integration_uses_public_launcher_and_is_hash_bound(
    sample_vault: Path, tmp_path: Path
) -> None:
    config = tmp_path / "settings.json"
    executable = _managed_mcp_launcher(tmp_path)
    plan = build_mcp_config_integration_plan(
        sample_vault,
        client="gemini",
        config_path=config,
        executable=executable,
    )
    assert plan["integration"] == "mcp-config"
    assert plan["status"] == "ready"
    assert plan["desired_sha256"]
    assert not config.exists()

    receipt = apply_mcp_config_integration_plan(plan, approved=True)
    assert receipt["status"] == "applied"
    configured = json.loads(config.read_text(encoding="utf-8"))
    assert configured["mcpServers"]["power"]["command"] == executable
    assert configured["mcpServers"]["power"]["args"] == []
    second = build_mcp_config_integration_plan(
        sample_vault,
        client="gemini",
        config_path=config,
        executable=executable,
    )
    assert second["status"] == "no_change"


def test_integrations_doctor_is_read_only() -> None:
    report = build_integrations_doctor()
    assert report["schema"] == "power.integrations.v1"
    assert report["mcp"]["entry_point"] == "power-mcp"
    assert report["skill"]["tree_sha256"]
