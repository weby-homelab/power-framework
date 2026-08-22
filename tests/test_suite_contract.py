"""Fail-closed Suite manifest and installer preflight contracts."""

from __future__ import annotations

import hashlib
import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from power_framework.core.integrations import (
    _rewrite_venv_shebangs,
    apply_native_install_plan,
    build_native_install_plan,
)
from power_framework.core.suite_contract import validate_suite_artifacts

if TYPE_CHECKING:
    from pathlib import Path


def _wheel(root: Path, filename: str, *, distribution: str, version: str) -> Path:
    path = root / filename
    dist_info = filename.removesuffix(".whl").split("-", 3)[0] + ".dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.3\n"
            f"Name: {distribution}\n"
            f"Version: {version}\n"
            "Requires-Python: >=3.13,<3.15\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
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
        "suite_version": "3.7.1",
        "application_schema": "power.application.v2",
        "power": component(power, "power-framework", "3.7.1"),
        "gui": component(gui, "power-gui", "0.7.6"),
        "skill": {"tree_sha256": "a" * 64, "compatible_power_version": "3.7.1"},
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
        "power_framework-3.7.1-py3-none-any.whl",
        distribution="power-framework",
        version="3.7.1",
    )
    gui = _wheel(
        tmp_path,
        "power_gui-0.7.6-py3-none-any.whl",
        distribution="power-gui",
        version="0.7.6",
    )
    return power, gui, _manifest(tmp_path, power, gui)


def test_exact_pair_manifest_preflight_passes(tmp_path: Path) -> None:
    power, gui, manifest = _fixtures(tmp_path)

    contract = validate_suite_artifacts(manifest, power, gui)

    assert contract["suite_version"] == "3.7.1"
    assert contract["application_schema"] == "power.application.v2"
    assert contract["components"]["power"]["metadata"]["name"] == "power-framework"


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
        "foreign-3.7.1-py3-none-any.whl",
        distribution="foreign-package",
        version="3.7.1",
    )

    with pytest.raises(ValueError, match="distribution"):
        validate_suite_artifacts(manifest, foreign, gui)


def test_moved_venv_console_scripts_use_active_interpreter(tmp_path: Path) -> None:
    venv_root = tmp_path / "active" / "venv"
    bin_dir = venv_root / "bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "power"
    script.write_text(
        "#!/tmp/staging-venv/bin/python\nprint('synthetic')\n",
        encoding="utf-8",
    )

    _rewrite_venv_shebangs(venv_root)

    assert script.read_text(encoding="utf-8").startswith(f"#!{venv_root}/bin/python\n")
