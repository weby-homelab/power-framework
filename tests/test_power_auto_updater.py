from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "power_auto_updater.py"
SPEC = importlib.util.spec_from_file_location("power_auto_updater", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load updater module")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["power_auto_updater"] = MODULE
SPEC.loader.exec_module(MODULE)


class TestPowerAutoUpdater:
    def test_parse_stable_versions(self) -> None:
        assert MODULE.parse_version("v3.6.6") == (3, 6, 6)
        assert MODULE.parse_version("3.6.10") == (3, 6, 10)
        with pytest.raises(ValueError, match="unsupported stable version"):
            MODULE.parse_version("v3.6.6-rc1")

    def test_redact_credentials(self) -> None:
        message = "token=ghp_abcdefghijklmnop123456 password=hidden"
        redacted = MODULE.redact(message)
        assert "ghp_abcdefghijklmnop123456" not in redacted
        assert "hidden" not in redacted
        assert "token=<redacted>" in redacted

    def test_compose_replacement_is_narrow(self) -> None:
        compose = "services:\n  power-gui:\n    image: webyhomelab/power-gui:0.7.4\n"
        updated = MODULE.replace_compose_image(compose, "local/power-gui:3.6.6")
        assert "image: local/power-gui:3.6.6" in updated
        assert "0.7.4" not in updated

    def test_compose_replacement_rejects_ambiguous_input(self) -> None:
        compose = "services:\n  one:\n    image: one:latest\n  two:\n    image: two:latest\n"
        with pytest.raises(RuntimeError):
            MODULE.replace_compose_image(compose, "local/power-gui:3.6.6")

    def test_python_discovery_uses_only_explicit_allowlist(self, tmp_path: Path) -> None:
        target = Path(sys.executable)
        config = MODULE.Config(
            repo="weby-homelab/power-framework",
            python_targets=(target,),
            state_dir=tmp_path,
            update_gui=False,
            gui_compose_dir=tmp_path,
            gui_service="power-gui",
            gui_base_image="webyhomelab/power-gui:0.7.4",
            gui_bind_address="127.0.0.1",
            skill_targets=(),
            dry_run=True,
        )
        assert MODULE.discover_python_targets(config) == (target,)

    def test_python_discovery_fails_for_missing_allowlist_target(self, tmp_path: Path) -> None:
        config = MODULE.Config(
            repo="weby-homelab/power-framework",
            python_targets=(tmp_path / "missing-python",),
            state_dir=tmp_path,
            update_gui=False,
            gui_compose_dir=tmp_path,
            gui_service="power-gui",
            gui_base_image="webyhomelab/power-gui:0.7.4",
            gui_bind_address="127.0.0.1",
            skill_targets=(),
            dry_run=True,
        )
        with pytest.raises(RuntimeError, match="configured POWER Python target is missing"):
            MODULE.discover_python_targets(config)
