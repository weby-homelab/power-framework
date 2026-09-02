"""Regression tests for tagged release receipt generation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.generate_release_receipt import build_receipt

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_release_receipt.py"


def test_receipt_binds_tag_tree_workflow_and_asset_digest(tmp_path: Path) -> None:
    assets = tmp_path / "dist"
    assets.mkdir()
    artifact = assets / "power-framework-test.whl"
    artifact.write_bytes(b"release artifact")
    manifest = tmp_path / "power-release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "power.release.manifest.v1",
                "repository": "weby-homelab/power-framework",
                "version": "3.2.5",
                "commit": "3f2e2b9687f96a6fc52c634a13bd75205af7dd96",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "receipt.json"

    environment = os.environ.copy()
    environment.update(
        {
            "RELEASE_WORKFLOW_REPOSITORY": "weby-homelab/power-framework",
            "RELEASE_CONTROL_REVISION": "a" * 40,
            "RELEASE_WORKFLOW_REVISION": "a" * 40,
            "RELEASE_WORKFLOW_RUN_ID": "12345",
            "RELEASE_WORKFLOW_ATTEMPT": "1",
            "RELEASE_WORKFLOW_EVENT": "push",
            "RELEASE_WORKFLOW_REF": "refs/tags/v3.2.5",
            "RELEASE_WORKFLOW_REF_PROTECTED": "false",
        }
    )
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
            "--release-manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
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


def test_receipt_normalizes_attestation_ids_and_binds_subjects(tmp_path: Path, monkeypatch) -> None:
    assets = tmp_path / "dist"
    assets.mkdir()
    wheel = assets / "power_framework-3.7.8-py3-none-any.whl"
    sdist = assets / "power_framework-3.7.8.tar.gz"
    dependency_lock = assets / "power-native-requirements.txt"
    wheel.write_bytes(b"wheel bytes")
    sdist.write_bytes(b"sdist bytes")
    dependency_lock.write_text(
        "mcp==2.1.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    image_digest = "sha256:" + "d" * 64
    manifest_path = tmp_path / "power-release-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "power.release.manifest.v1",
                "repository": "weby-homelab/power-framework",
                "version": "3.7.8",
                "commit": "6e7d0a48d36e564030954138fec03778ee44d6a0",
                "attestations": ["github:123", "github:456"],
                "artifacts": {
                    "power_wheel": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
                    "power_sdist": {"sha256": hashlib.sha256(sdist.read_bytes()).hexdigest()},
                    "native_dependency_lock": {
                        "filename": dependency_lock.name,
                        "sha256": hashlib.sha256(dependency_lock.read_bytes()).hexdigest(),
                    },
                    "web_image": {"digest": image_digest},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("RELEASE_WORKFLOW_REPOSITORY", "weby-homelab/power-framework")
    monkeypatch.setenv("RELEASE_CONTROL_REVISION", "b" * 40)
    monkeypatch.setenv("RELEASE_WORKFLOW_REVISION", "b" * 40)
    monkeypatch.setenv("RELEASE_WORKFLOW_RUN_ID", "12345")
    monkeypatch.setenv("RELEASE_WORKFLOW_ATTEMPT", "1")
    monkeypatch.setenv("RELEASE_WORKFLOW_EVENT", "push")
    monkeypatch.setenv("RELEASE_WORKFLOW_REF", "refs/tags/v3.7.8")
    monkeypatch.setenv("RELEASE_WORKFLOW_REF_PROTECTED", "false")

    receipt = build_receipt(
        repo=REPO_ROOT,
        tag="v3.7.8",
        assets_dir=assets,
        repository="weby-homelab/power-framework",
        workflow_run_id="12345",
        manifest_path=manifest_path,
        attestation_ids=["123", "github:456"],
        attestation_subjects=[
            f"123={hashlib.sha256(wheel.read_bytes()).hexdigest()}",
            f"123={hashlib.sha256(sdist.read_bytes()).hexdigest()}",
            f"123={hashlib.sha256(dependency_lock.read_bytes()).hexdigest()}",
            f"456={image_digest}",
        ],
        attestation_subject_roles=["123=package", "456=web"],
    )

    assert receipt["schema_version"] == 2
    assert receipt["attestations"] == ["github:123", "github:456"]
    assert receipt["attestation_subjects"] == [
        {
            "id": "github:123",
            "role": "package",
            "subjects": sorted(
                [
                    hashlib.sha256(wheel.read_bytes()).hexdigest(),
                    hashlib.sha256(sdist.read_bytes()).hexdigest(),
                    hashlib.sha256(dependency_lock.read_bytes()).hexdigest(),
                ]
            ),
        },
        {"id": "github:456", "role": "web", "subjects": [image_digest]},
    ]
