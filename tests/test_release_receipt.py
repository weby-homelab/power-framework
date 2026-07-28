"""Regression tests for tagged release receipt generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_release_receipt.py"


def test_receipt_binds_tag_tree_workflow_and_asset_digest(tmp_path: Path) -> None:
    assets = tmp_path / "dist"
    assets.mkdir()
    artifact = assets / "power-framework-test.whl"
    artifact.write_bytes(b"release artifact")
    output = tmp_path / "receipt.json"

    result = subprocess.run(  # noqa: S603 -- invokes the repository-local receipt generator.
        [
            sys.executable,
            str(SCRIPT),
            "--tag",
            "v3.2.5",
            "--git-repo",
            str(REPO_ROOT),
            "--assets-dir",
            str(assets),
            "--output",
            str(output),
            "--repository",
            "weby-homelab/power-framework",
            "--workflow-run-id",
            "12345",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["release"]["tag"] == "v3.2.5"
    assert receipt["release"]["commit"] == "3f2e2b9687f96a6fc52c634a13bd75205af7dd96"
    assert receipt["release"]["tree"] == "83fd4c776ffea2c81f89d456183e4ba6d1f3f61e"
    assert receipt["workflow_run"]["id"] == "12345"
    assert receipt["assets"] == [
        {
            "name": artifact.name,
            "size_bytes": len(b"release artifact"),
            "sha256": "133cfccb5b503cf4040c95f3dfad56d07c1574283a1e39066b594f6ee33711ba",
        }
    ]
