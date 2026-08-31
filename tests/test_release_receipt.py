"""Regression tests for tagged release receipt generation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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
                "commit": "3f2e2b9687f96a6fc52c634a13bd75205af7dd96",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "receipt.json"
    release_environment = os.environ.copy()
    release_environment.update(
        {
            "RELEASE_CONTROL_REVISION": "c" * 40,
            "RELEASE_WORKFLOW_REVISION": "c" * 40,
            "RELEASE_WORKFLOW_RUN_ID": "12345",
            "RELEASE_WORKFLOW_ATTEMPT": "2",
            "RELEASE_WORKFLOW_EVENT": "workflow_dispatch",
            "RELEASE_WORKFLOW_REPOSITORY": "weby-homelab/power-framework",
            "RELEASE_WORKFLOW_REF": "refs/heads/main",
            "RELEASE_WORKFLOW_REF_PROTECTED": "true",
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
        env=release_environment,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["release"]["tag"] == "v3.2.5"
    assert receipt["release"]["commit"] == "3f2e2b9687f96a6fc52c634a13bd75205af7dd96"
    assert receipt["release"]["tree"] == "83fd4c776ffea2c81f89d456183e4ba6d1f3f61e"
    assert receipt["workflow_run"]["id"] == "12345"
    assert receipt["release_provenance"] == {
        "release_source_tag": "v3.2.5",
        "release_source_commit": "3f2e2b9687f96a6fc52c634a13bd75205af7dd96",
        "release_source_tree": "83fd4c776ffea2c81f89d456183e4ba6d1f3f61e",
        "release_tag_object": "4c8c0d7b88d575ea1c6d566020269f8488b11e2d",
        "release_control_revision": "c" * 40,
        "workflow_revision": "c" * 40,
        "workflow_run_id": "12345",
        "workflow_run_attempt": "2",
        "workflow_event": "workflow_dispatch",
        "workflow_ref": "refs/heads/main",
        "workflow_ref_protected": "true",
        "repository": "weby-homelab/power-framework",
    }
    assert receipt["assets"] == [
        {
            "name": artifact.name,
            "size_bytes": len(b"release artifact"),
            "sha256": "133cfccb5b503cf4040c95f3dfad56d07c1574283a1e39066b594f6ee33711ba",
        }
    ]


def test_receipt_normalizes_attestation_ids_and_binds_subjects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = tmp_path / "dist"
    assets.mkdir()
    wheel = assets / "power_framework-3.7.8-py3-none-any.whl"
    sdist = assets / "power_framework-3.7.8.tar.gz"
    wheel.write_bytes(b"wheel bytes")
    sdist.write_bytes(b"sdist bytes")
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
                    "web_image": {"digest": image_digest},
                },
            }
        ),
        encoding="utf-8",
    )

    for name, value in {
        "RELEASE_CONTROL_REVISION": "a" * 40,
        "RELEASE_WORKFLOW_REVISION": "a" * 40,
        "RELEASE_WORKFLOW_RUN_ID": "12345",
        "RELEASE_WORKFLOW_ATTEMPT": "1",
        "RELEASE_WORKFLOW_EVENT": "push",
        "RELEASE_WORKFLOW_REPOSITORY": "weby-homelab/power-framework",
        "RELEASE_WORKFLOW_REF": "refs/tags/v3.7.8",
        "RELEASE_WORKFLOW_REF_PROTECTED": "false",
    }.items():
        monkeypatch.setenv(name, value)

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
                ]
            ),
        },
        {"id": "github:456", "role": "web", "subjects": [image_digest]},
    ]


def _minimal_receipt_inputs(tmp_path: Path) -> tuple[Path, Path]:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "evidence.txt").write_text("synthetic evidence\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
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
    return assets, manifest


def _set_valid_provenance_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "RELEASE_CONTROL_REVISION": "c" * 40,
        "RELEASE_WORKFLOW_REVISION": "c" * 40,
        "RELEASE_WORKFLOW_RUN_ID": "12345",
        "RELEASE_WORKFLOW_ATTEMPT": "1",
        "RELEASE_WORKFLOW_EVENT": "workflow_dispatch",
        "RELEASE_WORKFLOW_REPOSITORY": "weby-homelab/power-framework",
        "RELEASE_WORKFLOW_REF": "refs/heads/main",
        "RELEASE_WORKFLOW_REF_PROTECTED": "true",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("RELEASE_CONTROL_REVISION", "not-a-sha", "release control revision"),
        ("RELEASE_WORKFLOW_ATTEMPT", "0", "workflow run attempt"),
        ("RELEASE_WORKFLOW_EVENT", "schedule", "workflow event"),
        ("RELEASE_WORKFLOW_REPOSITORY", "", "workflow repository"),
        ("RELEASE_WORKFLOW_REF", "refs/heads/feature", "workflow ref"),
    ],
)
def test_receipt_rejects_malformed_control_plane_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    assets, manifest = _minimal_receipt_inputs(tmp_path)
    _set_valid_provenance_environment(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        build_receipt(
            repo=REPO_ROOT,
            tag="v3.2.5",
            assets_dir=assets,
            repository="weby-homelab/power-framework",
            workflow_run_id="12345",
            manifest_path=manifest,
        )


def test_receipt_rejects_inconsistent_control_plane_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets, manifest = _minimal_receipt_inputs(tmp_path)
    _set_valid_provenance_environment(monkeypatch)
    monkeypatch.setenv("RELEASE_WORKFLOW_REVISION", "d" * 40)

    with pytest.raises(ValueError, match="does not match workflow revision"):
        build_receipt(
            repo=REPO_ROOT,
            tag="v3.2.5",
            assets_dir=assets,
            repository="weby-homelab/power-framework",
            workflow_run_id="12345",
            manifest_path=manifest,
        )
