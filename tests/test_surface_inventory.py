"""Public-surface inventory stays aligned with the executable manifest."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from power_framework.core.capabilities import manifest
from scripts.generate_surface_inventory import build_inventory

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "generate_surface_inventory.py"


def test_surface_inventory_matches_current_runtime_and_packaging(tmp_path: Path) -> None:
    output = tmp_path / "surface-inventory-v1.json"
    result = subprocess.run(  # noqa: S603 -- invokes the repository-local generator.
        [sys.executable, str(GENERATOR), "--output", str(output)],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads(output.read_text(encoding="utf-8"))
    assert inventory == build_inventory()

    runtime = manifest()["interfaces"]
    assert inventory["interfaces"] == {
        "cli_commands": runtime["cli_commands"],
        "mcp_tools": runtime["mcp_tools"],
    }

    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        extras = tomllib.load(handle)["project"]["optional-dependencies"]
    for name, track in inventory["optional_tracks"].items():
        assert track["extra_declared"] is (name in extras)
        assert track["base_dependency"] is False
        for field in (
            "status",
            "owner",
            "slo",
            "benchmark",
            "threat_model",
            "expiry",
            "kill_criterion",
        ):
            assert isinstance(track[field], str)
            assert track[field]
        if track["status"] == "optional":
            assert isinstance(track["named_consumer"], str)
            assert track["named_consumer"]
        else:
            assert track["status"] == "quarantined"
            assert track["named_consumer"] is None
