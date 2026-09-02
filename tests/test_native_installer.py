"""Hermetic acceptance tests for the managed native POWER installer."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import power_framework.core.integrations as integrations


def _tree_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[relative]).digest())
    return digest.hexdigest()


def _write_release_fixture(root: Path, version: str, marker: str) -> dict[str, Path]:
    wheel = root / f"power_framework-{version}-py3-none-any.whl"
    lock = root / "power-native-requirements.txt"
    manifest = root / f"manifest-{version}-{marker[:6]}.json"
    skill = {"SKILL.md": b"---\nname: power\n---\n"}
    mcp = {"__init__.py": b"\n", "contract.py": f"{marker}\n".encode()}
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"power_framework-{version}.dist-info/METADATA",
            "Metadata-Version: 2.3\n"
            "Name: power-framework\n"
            f"Version: {version}\n"
            "Requires-Python: >=3.13,<3.15\n",
        )
        for relative, content in skill.items():
            archive.writestr("power_framework/data/skills/power/" + relative, content)
        for relative, content in mcp.items():
            archive.writestr("power_framework/mcp/" + relative, content)
    lock.write_text("example==1.0 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    payload = {
        "schema": "power.release.manifest.v1",
        "repository": "weby-homelab/power-framework",
        "version": version,
        "commit": marker * 40,
        "requires_python": ">=3.13,<3.15",
        "application_schema": "power.application.v2",
        "profiles": {
            "native": ["power", "power-mcp"],
            "web": ["power-web"],
            "skill": ["power"],
        },
        "mcp": {"entry_point": "power-mcp", "transport": "stdio"},
        "web": {"entry_point": "power-web", "port": 8080},
        "skill_tree_sha256": _tree_hash(skill),
        "mcp_contract_sha256": _tree_hash(mcp),
        "artifacts": {
            "power_wheel": {"filename": wheel.name, "sha256": _sha256(wheel)},
            "native_dependency_lock": {"filename": lock.name, "sha256": _sha256(lock)},
        },
    }
    manifest.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return {"wheel": wheel, "lock": lock, "manifest": manifest}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_native_runtime(monkeypatch: pytest.MonkeyPatch):
    """Create venv-shaped files and bypass only pip/process execution."""

    class FakeBuilder:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def create(self, path: Path) -> None:
            bin_dir = path / "bin"
            bin_dir.mkdir(parents=True)
            for name in ("power", "power-mcp"):
                executable = bin_dir / name
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o755)

    def fake_run(_command: list[str], **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(stdout="power-framework 3.7.10 3.7.11", stderr="")

    monkeypatch.setattr(integrations.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(integrations.subprocess, "run", fake_run)


def _plan(home: Path, fixture: dict[str, Path]) -> dict[str, object]:
    return integrations.build_native_install_plan(
        home=home,
        power_wheel=fixture["wheel"],
        manifest=fixture["manifest"],
        dependency_lock=fixture["lock"],
    )


def test_native_install_fresh_upgrade_and_noop(tmp_path: Path, fake_native_runtime: None) -> None:
    home = tmp_path / "home"
    first = _write_release_fixture(tmp_path, "3.7.10", "a")
    first_receipt = integrations.apply_native_install_plan(_plan(home, first), approved=True)
    assert first_receipt["status"] == "applied"
    current = home / ".local" / "share" / "power" / "current"
    first_target = current.resolve()
    assert first_target.is_dir()
    assert (home / ".local" / "bin" / "power-mcp").resolve() == (
        current / "venv" / "bin" / "power-mcp"
    ).resolve()

    second = _write_release_fixture(tmp_path, "3.7.11", "b")
    second_receipt = integrations.apply_native_install_plan(_plan(home, second), approved=True)
    assert second_receipt["status"] == "applied"
    assert current.resolve() != first_target
    assert first_target.is_dir()
    assert integrations.apply_native_install_plan(_plan(home, second), approved=True)["status"] == (
        "no_change"
    )


def test_native_install_failure_preserves_previous_runtime(
    tmp_path: Path, fake_native_runtime: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    first = _write_release_fixture(tmp_path, "3.7.10", "a")
    integrations.apply_native_install_plan(_plan(home, first), approved=True)
    current = home / ".local" / "share" / "power" / "current"
    previous_target = current.resolve()
    second = _write_release_fixture(tmp_path, "3.7.11", "b")

    def fail_run(_command: list[str], **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.setattr(integrations.subprocess, "run", fail_run)
    with pytest.raises(subprocess.CalledProcessError):
        integrations.apply_native_install_plan(_plan(home, second), approved=True)
    assert current.resolve() == previous_target
    assert (home / ".local" / "bin" / "power-mcp").resolve() == (
        current / "venv" / "bin" / "power-mcp"
    ).resolve()


def test_native_install_post_activation_failure_rolls_back_launchers_and_pointer(
    tmp_path: Path, fake_native_runtime: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    first = _write_release_fixture(tmp_path, "3.7.10", "a")
    integrations.apply_native_install_plan(_plan(home, first), approved=True)
    current = home / ".local" / "share" / "power" / "current"
    previous_target = current.resolve()
    second = _write_release_fixture(tmp_path, "3.7.11", "b")
    original_verify = integrations._verify_installed_launcher
    calls = 0

    def fail_after_public_activation(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("synthetic post-activation failure")
        original_verify(*args, **kwargs)

    monkeypatch.setattr(integrations, "_verify_installed_launcher", fail_after_public_activation)
    with pytest.raises(RuntimeError, match="post-activation"):
        integrations.apply_native_install_plan(_plan(home, second), approved=True)
    assert current.resolve() == previous_target
    assert (home / ".local" / "bin" / "power-mcp").resolve() == (
        current / "venv" / "bin" / "power-mcp"
    ).resolve()
    release_dirs = [
        path
        for path in (home / ".local" / "share" / "power" / "releases").iterdir()
        if path.is_dir()
    ]
    assert len(release_dirs) == 1


def test_native_install_rejects_release_slot_symlink_race(
    tmp_path: Path, fake_native_runtime: None
) -> None:
    home = tmp_path / "home"
    fixture = _write_release_fixture(tmp_path, "3.7.11", "a")
    plan = _plan(home, fixture)
    release_slot = Path(plan["native"]["release_slot"])
    release_slot.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    release_slot.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="release slot"):
        integrations.apply_native_install_plan(plan, approved=True)
    assert not (outside / "venv").exists()


def test_native_install_rejects_foreign_launcher_without_overwrite(
    tmp_path: Path, fake_native_runtime: None
) -> None:
    home = tmp_path / "home"
    fixture = _write_release_fixture(tmp_path, "3.7.11", "a")
    plan = _plan(home, fixture)
    launcher = home / ".local" / "bin" / "power-mcp"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("foreign launcher\n", encoding="utf-8")

    with pytest.raises(PermissionError, match="not POWER-managed"):
        integrations.apply_native_install_plan(plan, approved=True)
    assert launcher.read_text(encoding="utf-8") == "foreign launcher\n"


def test_native_plan_rejects_root_alias_and_external_current(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="filesystem root"):
        integrations.build_native_install_plan(home=Path(os.sep) / "tmp" / "..")

    home = tmp_path / "home"
    fixture = _write_release_fixture(tmp_path, "3.7.11", "a")
    managed = home / ".local" / "share" / "power"
    managed.mkdir(parents=True)
    (managed / "releases").mkdir()
    (managed / "current").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError, match="current pointer"):
        _plan(home, fixture)
