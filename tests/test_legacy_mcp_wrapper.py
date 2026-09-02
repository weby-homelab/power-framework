"""Regression checks for the deprecated MCP compatibility wrapper."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / ".agents" / "mcp_servers" / "power_server.py"


def test_legacy_wrapper_does_not_load_host_environment_files() -> None:
    """Compatibility must delegate only; it may not import arbitrary host secrets."""
    source = WRAPPER.read_text(encoding="utf-8")

    assert "from power_framework.mcp.entrypoint import main" in source
    assert "os.environ" not in source
    assert 'open("' not in source
    assert "/root/" not in source
    assert "raise SystemExit(main())" in source


def test_legacy_wrapper_preserves_canonical_preflight_failure(tmp_path: Path) -> None:
    """A legacy invocation must keep the public launcher's fail-closed exit code."""
    environment = os.environ.copy()
    environment.pop("POWER_VAULT_DIR", None)
    environment["POWER_VAULT_PATH"] = str(tmp_path)

    result = subprocess.run(  # noqa: S603 - exact repository compatibility shim.
        [sys.executable, str(WRAPPER), "preflight"],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "POWER_VAULT_DIR" in result.stderr
