"""Tests for tag-bound release baseline generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_release_baseline.py"
VERIFY = REPO_ROOT / "scripts" / "verify_release_contract.py"


def test_generated_baseline_binds_v330_tag(tmp_path: Path) -> None:
    output = tmp_path / "release-baseline.json"
    result = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [sys.executable, str(SCRIPT), "--tag", "v3.3.0", "--output", str(output)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    baseline = json.loads(output.read_text(encoding="utf-8"))
    assert baseline["release"] == "3.3.0"
    assert baseline["source"]["commit"] == "343e61a6f733d1954e667bf9df0c0eb6a813ce54"
    assert baseline["source"]["tree"] == "cdc8dd963def030ad8363366c64d5e581b129343"

    verified = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [
            sys.executable,
            str(VERIFY),
            "--require-tag",
            "--baseline",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
