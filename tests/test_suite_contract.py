"""Fail-closed Suite manifest and installer preflight contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

import power_framework.core.integrations as integrations
from power_framework.core.integrations import apply_native_install_plan, build_native_install_plan
from power_framework.core.suite_contract import _wheel_skill_tree_sha256, validate_suite_artifacts


def _wheel(
    root: Path,
    filename: str,
    *,
    distribution: str,
    version: str,
    requirements: tuple[str, ...] = (),
    include_skill: bool = False,
) -> Path:
    path = root / filename
    dist_info = filename.removesuffix(".whl").split("-", 3)[0] + ".dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        metadata = (
            "Metadata-Version: 2.3\n"
            f"Name: {distribution}\n"
            f"Version: {version}\n"
            "Requires-Python: >=3.13,<3.15\n"
        )
        metadata += "".join(f"Requires-Dist: {requirement}\n" for requirement in requirements)
        archive.writestr(
            f"{dist_info}/METADATA",
            metadata,
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        if include_skill:
            archive.writestr(
                "power_framework/data/skills/power/SKILL.md",
                f"---\nname: power\nversion: {version}\n---\n",
            )
    return path


def _manifest(root: Path, power: Path, gui: Path) -> Path:
    constraints = root / "power-suite.constraints.txt"
    constraints.write_text("# disposable test constraints\n", encoding="utf-8")

    def component(path: Path, distribution: str, version: str) -> dict[str, str]:
        return {
            "distribution": distribution,
            "version": version,
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "requires_python": ">=3.13,<3.15",
        }

    document = {
        "schema": "power.suite.manifest.v1",
        "status": "candidate",
        "suite_version": "3.7.3",
        "application_schema": "power.application.v2",
        "power": component(power, "power-framework", "3.7.3"),
        "gui": component(gui, "power-gui", "0.7.8"),
        "skill": {"tree_sha256": "a" * 64, "compatible_power_version": "3.7.3"},
        "python": {"requires_python": ">=3.13,<3.15"},
        "dependencies": {
            "constraints": constraints.name,
            "sha256": hashlib.sha256(constraints.read_bytes()).hexdigest(),
        },
    }
    path = root / "power.suite.manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    power = _wheel(
        tmp_path,
        "power_framework-3.7.3-py3-none-any.whl",
        distribution="power-framework",
        version="3.7.3",
    )
    gui = _wheel(
        tmp_path,
        "power_gui-0.7.8-py3-none-any.whl",
        distribution="power-gui",
        version="0.7.8",
    )
    return power, gui, _manifest(tmp_path, power, gui)


def _v2_fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    power = _wheel(
        tmp_path,
        "power_framework-3.7.4-py3-none-any.whl",
        distribution="power-framework",
        version="3.7.4",
        include_skill=True,
    )
    requires_power = "power-framework==3.7.4"
    gui = _wheel(
        tmp_path,
        "power_gui-0.7.10-py3-none-any.whl",
        distribution="power-gui",
        version="0.7.10",
        requirements=(requires_power,),
    )
    constraints = tmp_path / "power-suite-v2.constraints.txt"
    constraints.write_text("power-framework==3.7.4\npower-gui==0.7.10\n", encoding="utf-8")
    document = {
        "schema": "power.suite.manifest.v2",
        "status": "candidate",
        "suite_version": "3.7.4",
        "application_schema": "power.application.v2",
        "power": {
            "distribution": "power-framework",
            "version": "3.7.4",
            "filename": power.name,
            "sha256": hashlib.sha256(power.read_bytes()).hexdigest(),
            "requires_python": ">=3.13,<3.15",
        },
        "gui": {
            "distribution": "power-gui",
            "version": "0.7.10",
            "filename": gui.name,
            "sha256": hashlib.sha256(gui.read_bytes()).hexdigest(),
            "requires_python": ">=3.13,<3.15",
            "expected_power_version": "3.7.4",
            "requires_power": requires_power,
            "application_schema": "power.application.v2",
        },
        "skill": {
            "tree_sha256": _wheel_skill_tree_sha256(power),
            "compatible_power_version": "3.7.4",
        },
        "python": {"requires_python": ">=3.13,<3.15"},
        "dependencies": {
            "constraints": constraints.name,
            "sha256": hashlib.sha256(constraints.read_bytes()).hexdigest(),
        },
    }
    manifest = tmp_path / "power.suite.v2.manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return power, gui, manifest


def _fake_native_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    state_path: Path,
    calls: list[tuple[str, ...]],
    fail_user_launcher: dict[str, bool] | None = None,
) -> list[Path]:
    created_venvs: list[Path] = []

    def fake_create(_builder: object, path: str | Path) -> None:
        venv_path = Path(path)
        created_venvs.append(venv_path)
        bin_dir = venv_path / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("python", "power", "power-mcp", "power-gui"):
            script = bin_dir / name
            script.write_text(f"#!{bin_dir / 'python'}\n", encoding="utf-8")
            script.chmod(0o755)

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check
        assert capture_output
        assert text
        command_tuple = tuple(map(str, command))
        calls.append(command_tuple)
        executable = Path(command_tuple[0])
        is_user_launcher = (
            executable.parent.name == "bin" and executable.parent.parent.name == ".local"
        )
        if (
            fail_user_launcher
            and fail_user_launcher.get("enabled", False)
            and is_user_launcher
            and executable.name == "power"
        ):
            raise subprocess.CalledProcessError(1, command_tuple)
        stdout = "P.O.W.E.R. 3.7.3\n" if "--version" in command_tuple else "usage\n"
        return subprocess.CompletedProcess(command_tuple, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(integrations.venv.EnvBuilder, "create", fake_create)
    monkeypatch.setattr(integrations.subprocess, "run", fake_run)
    return created_venvs


def test_exact_pair_manifest_preflight_passes(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)

    contract = validate_suite_artifacts(manifest, power, gui)

    assert contract["suite_version"] == "3.7.3"
    assert contract["application_schema"] == "power.application.v2"
    assert contract["components"]["power"]["metadata"]["name"] == "power-framework"


def test_v2_exact_pair_binds_gui_requirement_and_packaged_skill(tmp_path: Path) -> None:
    power, gui, manifest = _v2_fixtures(tmp_path)

    contract = validate_suite_artifacts(manifest, power, gui)

    assert contract["suite_version"] == "3.7.4"
    assert contract["components"]["gui"]["metadata"]["requires_dist"] == ["power-framework==3.7.4"]


def test_v2_wrong_gui_power_binding_is_rejected(tmp_path: Path) -> None:
    power, gui, manifest = _v2_fixtures(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["gui"]["expected_power_version"] = "3.7.3"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="expected POWER version"):
        validate_suite_artifacts(manifest, power, gui)


def test_v2_tampered_packaged_skill_is_rejected_even_with_updated_wheel_hash(
    tmp_path: Path,
) -> None:
    power, gui, manifest = _v2_fixtures(tmp_path)
    with zipfile.ZipFile(power, "a") as archive:
        archive.writestr("power_framework/data/skills/power/references/new.md", "tampered\n")
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["power"]["sha256"] = hashlib.sha256(power.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="Skill tree hash"):
        validate_suite_artifacts(manifest, power, gui)


def test_stale_suite_version_is_rejected(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["suite_version"] = "3.7.2"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="Suite version"):
        validate_suite_artifacts(manifest, power, gui)


def test_tampered_gui_wheel_is_rejected(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    gui.write_bytes(gui.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="gui wheel hash"):
        validate_suite_artifacts(manifest, power, gui)


def test_tampered_constraints_are_rejected(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    (tmp_path / "power-suite.constraints.txt").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="constraints hash"):
        validate_suite_artifacts(manifest, power, gui)


def test_unsupported_python_is_rejected(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)

    with pytest.raises(ValueError, match="outside"):
        validate_suite_artifacts(manifest, power, gui, python_version=(3, 12, 10))


def test_missing_manifest_blocks_before_target_creation(tmp_path: Path) -> None:
    power, gui, _manifest_path = _fixtures(tmp_path)
    target_home = tmp_path / "home"

    plan = build_native_install_plan(
        home=target_home,
        power_wheel=power,
        gui_wheel=gui,
    )

    assert plan["status"] == "blocked"
    assert "manifest" in plan["reason"]
    assert not target_home.exists()


def test_tampered_wheel_is_rejected_and_target_is_untouched(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    plan = build_native_install_plan(
        home=tmp_path / "home",
        power_wheel=power,
        gui_wheel=gui,
        manifest=manifest,
    )
    power.write_bytes(power.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash"):
        apply_native_install_plan(plan, approved=True)

    assert not (tmp_path / "home" / ".local" / "share" / "power").exists()


def test_wrong_distribution_is_rejected_before_install(tmp_path: Path) -> None:
    _power, gui, manifest = _fixtures(tmp_path)
    foreign = _wheel(
        tmp_path,
        "foreign-3.7.3-py3-none-any.whl",
        distribution="foreign-package",
        version="3.7.3",
    )

    with pytest.raises(ValueError, match="distribution"):
        validate_suite_artifacts(manifest, foreign, gui)


def test_native_install_creates_venv_directly_in_final_release_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    home = tmp_path / "home with spaces-Ж"
    plan = build_native_install_plan(
        home=home,
        power_wheel=power,
        gui_wheel=gui,
        manifest=manifest,
    )
    state_path = Path(plan["native"]["state"])
    calls: list[tuple[str, ...]] = []
    created_venvs = _fake_native_runtime(monkeypatch, state_path=state_path, calls=calls)
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = integrations.os.replace
    real_atomic_write = integrations.atomic_write

    def recording_replace(source: str | Path, destination: str | Path) -> None:
        replace_calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    def recording_atomic_write(path: Path, content: str) -> None:
        calls.append(("atomic_write", str(path)))
        real_atomic_write(path, content)

    monkeypatch.setattr(integrations.os, "replace", recording_replace)
    monkeypatch.setattr(integrations, "atomic_write", recording_atomic_write)

    receipt = apply_native_install_plan(plan, approved=True, no_deps=True)

    slot_venv = Path(plan["native"]["slot_venv"])
    release_slot = Path(plan["native"]["release_slot"])
    current = Path(plan["native"]["current"])
    assert created_venvs == [slot_venv]
    assert ".venv.staging-" not in str(slot_venv)
    assert not any(
        source == slot_venv or destination == slot_venv for source, destination in replace_calls
    )
    assert current.is_symlink()
    assert current.resolve() == release_slot.resolve()
    assert receipt["status"] == "applied"
    assert receipt["release_slot"] == str(release_slot)
    assert state_path.is_file()
    assert all(
        str(slot_venv / "bin" / name) in {call[0] for call in calls}
        for name in ("power", "power-mcp", "power-gui")
    )
    assert all(
        str(home / ".local" / "bin" / name) in {call[0] for call in calls}
        for name in ("power", "power-mcp", "power-gui")
    )
    receipt_write_index = next(
        index for index, call in enumerate(calls) if call[0] == "atomic_write"
    )
    user_launcher_indexes = [
        index for index, call in enumerate(calls) if Path(call[0]).parent == home / ".local" / "bin"
    ]
    assert user_launcher_indexes
    assert max(user_launcher_indexes) < receipt_write_index


def test_previous_release_slot_is_retained_after_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    home = tmp_path / "home"
    first_plan = build_native_install_plan(
        home=home, power_wheel=power, gui_wheel=gui, manifest=manifest
    )
    calls: list[tuple[str, ...]] = []
    _fake_native_runtime(monkeypatch, state_path=Path(first_plan["native"]["state"]), calls=calls)
    first_receipt = apply_native_install_plan(first_plan, approved=True, no_deps=True)

    second_plan = build_native_install_plan(
        home=home, power_wheel=power, gui_wheel=gui, manifest=manifest
    )
    second_receipt = apply_native_install_plan(second_plan, approved=True, no_deps=True)

    first_slot = Path(first_receipt["release_slot"])
    second_slot = Path(second_receipt["release_slot"])
    assert first_slot.is_dir()
    assert second_slot.is_dir()
    assert second_receipt["previous_release_slot"] == str(first_slot.resolve())
    assert Path(second_plan["native"]["current"]).resolve() == second_slot.resolve()


def test_failed_user_launcher_readback_restores_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    home = tmp_path / "home"
    first_plan = build_native_install_plan(
        home=home, power_wheel=power, gui_wheel=gui, manifest=manifest
    )
    state_path = Path(first_plan["native"]["state"])
    failure = {"enabled": False}
    calls: list[tuple[str, ...]] = []
    _fake_native_runtime(
        monkeypatch,
        state_path=state_path,
        calls=calls,
        fail_user_launcher=failure,
    )
    first_receipt = apply_native_install_plan(first_plan, approved=True, no_deps=True)
    state_before = state_path.read_bytes()
    launcher_before = (home / ".local" / "bin" / "power").read_bytes()

    second_plan = build_native_install_plan(
        home=home, power_wheel=power, gui_wheel=gui, manifest=manifest
    )
    failure["enabled"] = True
    with pytest.raises(subprocess.CalledProcessError):
        apply_native_install_plan(second_plan, approved=True, no_deps=True)

    assert (
        Path(second_plan["native"]["current"]).resolve()
        == Path(first_receipt["release_slot"]).resolve()
    )
    assert state_path.read_bytes() == state_before
    assert (home / ".local" / "bin" / "power").read_bytes() == launcher_before
    assert not Path(second_plan["native"]["release_slot"]).exists()


def test_legacy_venv_is_preserved_during_release_slot_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    home = tmp_path / "home"
    legacy_marker = home / ".local" / "share" / "power" / "venv" / "legacy.txt"
    legacy_marker.parent.mkdir(parents=True)
    legacy_marker.write_text("preserve", encoding="utf-8")
    plan = build_native_install_plan(home=home, power_wheel=power, gui_wheel=gui, manifest=manifest)
    calls: list[tuple[str, ...]] = []
    _fake_native_runtime(monkeypatch, state_path=Path(plan["native"]["state"]), calls=calls)

    receipt = apply_native_install_plan(plan, approved=True, no_deps=True)

    assert legacy_marker.read_text(encoding="utf-8") == "preserve"
    assert receipt["legacy_venv_preserved"] is True
    assert Path(plan["native"]["current"]).is_symlink()


def test_existing_release_slot_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    power, gui, manifest = _fixtures(tmp_path)
    plan = build_native_install_plan(
        home=tmp_path / "home", power_wheel=power, gui_wheel=gui, manifest=manifest
    )
    marker = Path(plan["native"]["release_slot"]) / "venv" / "marker.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("preserve", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    _fake_native_runtime(monkeypatch, state_path=Path(plan["native"]["state"]), calls=calls)

    with pytest.raises(RuntimeError, match="will not be overwritten"):
        apply_native_install_plan(plan, approved=True, no_deps=True)

    assert marker.read_text(encoding="utf-8") == "preserve"
    assert calls == []
