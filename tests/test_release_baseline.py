"""Tests for tag-bound release baseline generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_release_baseline.py"
VERIFY = REPO_ROOT / "scripts" / "verify_release_contract.py"


def test_generated_baseline_binds_v331_tag(tmp_path: Path) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    tag = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local refs.
        [git_executable, "rev-parse", "--verify", "refs/tags/v3.3.1^{}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if tag.returncode != 0:
        pytest.skip("v3.3.1 is created only for the release tag gate")

    output = tmp_path / "release-baseline.json"
    result = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [sys.executable, str(SCRIPT), "--tag", "v3.3.1", "--output", str(output)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    baseline = json.loads(output.read_text(encoding="utf-8"))
    assert baseline["release"] == "3.3.1"
    expected_commit = tag.stdout.strip()
    expected_tree = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local object.
        [git_executable, "show", "-s", "--format=%T", expected_commit],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert baseline["source"]["commit"] == expected_commit
    assert baseline["source"]["tree"] == expected_tree

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
