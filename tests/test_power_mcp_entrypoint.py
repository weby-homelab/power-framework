"""Public power-mcp launcher and fail-closed preflight contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from power_framework.mcp.entrypoint import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_console_script_points_to_public_entrypoint() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["scripts"]["power-mcp"] == "power_framework.mcp.entrypoint:main"


def test_mcp_extra_is_explicit_and_official_sdk_is_not_fastmcp() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    extras = project["optional-dependencies"]
    assert any(str(item).startswith("mcp>=2.0") for item in extras["mcp"])
    assert any(str(item).startswith("mcp>=2.0") for item in extras["remote"])
    assert all("fastmcp" not in str(item).lower() for item in extras["remote"])


def test_preflight_requires_an_explicit_existing_vault(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("POWER_VAULT_DIR", raising=False)
    monkeypatch.delenv("POWER_VAULT_PATH", raising=False)
    assert main(["preflight"]) == 2

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("POWER_VAULT_DIR", str(vault))
    assert main(["preflight"]) == 0


def test_console_preflight_is_available_in_a_subprocess(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["POWER_VAULT_DIR"] = str(vault)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "power_framework.mcp.entrypoint", "preflight"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["vault_root"] == str(vault.resolve())
    assert result.stderr == ""
