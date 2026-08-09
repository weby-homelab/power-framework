"""Tests for tag-bound release baseline generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_release_baseline.py"
VERIFY = REPO_ROOT / "scripts" / "verify_release_contract.py"


def test_generated_baseline_binds_current_release_tag(tmp_path: Path) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    tag_name = f"v{version}"
    tag = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local refs.
        [git_executable, "rev-parse", "--verify", f"refs/tags/{tag_name}^{{}}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if tag.returncode != 0:
        pytest.skip(f"{tag_name} is created only for the release tag gate")

    output = tmp_path / "release-baseline.json"
    result = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [sys.executable, str(SCRIPT), "--tag", tag_name, "--output", str(output)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    baseline = json.loads(output.read_text(encoding="utf-8"))
    assert baseline["release"] == version
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
