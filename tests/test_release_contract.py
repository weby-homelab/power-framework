"""Hermetic checks for the unified POWER release and runtime contract."""

from __future__ import annotations

import json
from pathlib import Path

from power_framework.core.integrations import build_integrations_doctor, build_native_install_plan

ROOT = Path(__file__).resolve().parents[1]


def test_release_manifest_has_one_native_profile_and_web_adapter() -> None:
    manifest = json.loads(
        (ROOT / "release" / "power-release-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "power.release.manifest.template.v1"
    assert manifest["authority"] == "candidate-only"
    assert manifest["generated_manifest"] == "dist/power-release-manifest.json"
    assert manifest["version"] == "3.7.11"
    assert manifest["artifacts"] == {}
    assert manifest["profiles"]["native"] == ["power", "power-mcp"]
    assert manifest["profiles"]["web"] == ["power-web"]
    assert manifest["profiles"]["profile_a"]["status"] == "mcp-required"
    assert manifest["profiles"]["profile_b"]["capabilities"] == [
        "web",
        "semantic",
        "rerank",
    ]
    assert manifest["mcp"] == {
        "entry_point": "power-mcp",
        "transport": "stdio",
        "vault_environment": "POWER_VAULT_DIR",
    }
    assert manifest["web"]["entry_point"] == "power-web"
    assert "power-gui" not in json.dumps(manifest, sort_keys=True)


def test_native_install_requires_exact_release_inputs(tmp_path: Path) -> None:
    plan = build_native_install_plan(home=tmp_path)
    assert plan["schema"] == "power.native-install.v2"
    assert plan["installer_version"] == 2
    assert len(plan["plan_hash"]) == 64
    assert plan["status"] == "blocked"
    assert "release manifest" in plan["reason"]


def test_integrations_doctor_does_not_require_retired_gui_launcher() -> None:
    report = build_integrations_doctor()
    assert set(report["native"]["launchers"]) == {"power", "power-mcp"}
    assert "power-gui" not in report["native"]["launchers"]
