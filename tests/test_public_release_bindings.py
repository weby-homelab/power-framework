"""Adversarial tests for zero-trust public release binding verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.verify_public_release_bindings import verify_public_release_bindings

TAG = "v3.7.10"
COMMIT = "a" * 40
IMAGE_DIGEST = "sha256:" + "f" * 64


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_checksums(path: Path, files: list[Path]) -> None:
    path.write_text(
        "".join(
            f"{_sha256_file(file)}  {file.name}\n"
            for file in sorted(files, key=lambda item: item.name)
        ),
        encoding="utf-8",
    )


def _write_fixture(tmp_path: Path) -> dict[str, Path | str]:
    asset_dir = tmp_path / "public-assets"
    asset_dir.mkdir()
    wheel = asset_dir / "power_framework-3.7.10-py3-none-any.whl"
    sdist = asset_dir / "power_framework-3.7.10.tar.gz"
    package_sbom = asset_dir / "power-framework-3.7.10.spdx.json"
    web_sbom = asset_dir / "power-web-3.7.10.spdx.json"
    profile = asset_dir / "power-profile-acceptance.json"
    wheel.write_bytes(b"wheel bytes from the frozen candidate")
    sdist.write_bytes(b"sdist bytes from the frozen candidate")
    package_sbom.write_bytes(b'{"spdxVersion":"SPDX-2.3","name":"package"}\n')
    web_sbom.write_bytes(b'{"spdxVersion":"SPDX-2.3","name":"web"}\n')
    profile.write_text(
        json.dumps(
            {
                "schema": "power.profile.acceptance.v1",
                "version": "3.7.10",
                "acceptance_harness_revision": COMMIT,
                "image_digest": IMAGE_DIGEST,
                "profile_a": {
                    "native_cli": True,
                    "native_mcp_stdio": True,
                    "docker_web_containers": 0,
                },
                "profile_b": {
                    "web_health": True,
                    "web_authenticated_read": True,
                    "web_semantic_non_fallback": True,
                    "web_reranked_non_fallback": True,
                    "web_governed_mutation": True,
                    "host_cli_readback": True,
                    "host_mcp_readback": True,
                    "same_canonical_vault": True,
                    "cache_delete_rebuild": True,
                    "container_user": "10001:10001",
                    "cap_drop_all": True,
                    "read_only_rootfs": True,
                    "web_mcp_services": 0,
                    "web_applicationservice_bypass_count": 0,
                },
                "image": "ghcr.io/weby-homelab/power-framework-web:3.7.10@" + IMAGE_DIGEST,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema": "power.release.manifest.v1",
        "repository": "weby-homelab/power-framework",
        "version": "3.7.10",
        "commit": COMMIT,
        "requires_python": ">=3.13,<3.15",
        "attestations": ["github:package-1", "github:web-1"],
        "artifacts": {
            "power_wheel": {"filename": wheel.name, "sha256": _sha256_file(wheel)},
            "power_sdist": {"filename": sdist.name, "sha256": _sha256_file(sdist)},
            "package_sbom": {
                "filename": package_sbom.name,
                "sha256": _sha256_file(package_sbom),
            },
            "web_sbom": {"filename": web_sbom.name, "sha256": _sha256_file(web_sbom)},
            "profile_evidence": {"filename": profile.name, "sha256": _sha256_file(profile)},
            "web_image": {
                "reference": "ghcr.io/weby-homelab/power-framework-web:3.7.10",
                "digest": IMAGE_DIGEST,
            },
        },
    }
    manifest_path = asset_dir / "power-release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")

    checksums_path = asset_dir / "SHA256SUMS"
    checksum_files = [wheel, sdist, package_sbom, web_sbom, profile, manifest_path]
    _write_checksums(checksums_path, checksum_files)

    receipt_path = asset_dir / "power-framework.release-receipt.json"
    receipt = {
        "schema_version": 2,
        "release": {"tag": TAG, "commit": COMMIT},
        "attestations": ["package-1", "web-1"],
        "attestation_subjects": [
            {
                "id": "package-1",
                "role": "package",
                "subjects": [_sha256_file(wheel), _sha256_file(sdist)],
            },
            {"id": "web-1", "role": "web", "subjects": [IMAGE_DIGEST]},
        ],
        "unified_release_manifest": {
            "name": manifest_path.name,
            "sha256": _sha256_file(manifest_path),
        },
        "assets": [{"name": file.name, "sha256": _sha256_file(file)} for file in checksum_files],
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "asset_dir": asset_dir,
        "manifest": manifest_path,
        "checksums": checksums_path,
        "receipt": receipt_path,
        "commit": COMMIT,
    }


def _rewrite_manifest(paths: dict[str, Path | str], mutate: Any) -> None:
    manifest_path = Path(paths["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")


def _refresh_manifest_receipt_and_checksum(paths: dict[str, Path | str]) -> None:
    manifest_path = Path(paths["manifest"])
    receipt_path = Path(paths["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["unified_release_manifest"]["sha256"] = _sha256_file(manifest_path)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    checksum_path = Path(paths["checksums"])
    files = [
        path
        for path in Path(paths["asset_dir"]).iterdir()
        if path.is_file() and path.name not in {checksum_path.name, Path(paths["receipt"]).name}
    ]
    _write_checksums(checksum_path, files)


def _verify(paths: dict[str, Path | str]) -> dict[str, Any]:
    return verify_public_release_bindings(
        tag=TAG,
        manifest_path=Path(paths["manifest"]),
        checksums_path=Path(paths["checksums"]),
        asset_dir=Path(paths["asset_dir"]),
        receipt_path=Path(paths["receipt"]),
        expected_tag_target=str(paths["commit"]),
    )


def test_valid_frozen_release_binding_passes(tmp_path: Path) -> None:
    result = _verify(_write_fixture(tmp_path))
    assert result["status"] == "verified"


def test_required_manifest_filename_cannot_be_omitted(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    _rewrite_manifest(paths, lambda data: data["artifacts"]["power_wheel"].pop("filename"))
    _refresh_manifest_receipt_and_checksum(paths)
    with pytest.raises(ValueError, match=r"power_wheel.*filename"):
        _verify(paths)


def test_release_receipt_schema_must_be_v2(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    receipt_path = Path(paths["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["schema_version"] = 1
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        _verify(paths)


def test_release_receipt_must_be_inside_public_asset_directory(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    receipt_path = Path(paths["receipt"])
    external_receipt = tmp_path / receipt_path.name
    external_receipt.write_bytes(receipt_path.read_bytes())
    paths["receipt"] = external_receipt

    with pytest.raises(ValueError, match="inside the public asset directory"):
        _verify(paths)


def test_manifest_wheel_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    _rewrite_manifest(paths, lambda data: data["artifacts"]["power_wheel"].update(sha256="0" * 64))
    _refresh_manifest_receipt_and_checksum(paths)
    with pytest.raises(ValueError, match="power_wheel"):
        _verify(paths)


def test_manifest_sdist_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    _rewrite_manifest(paths, lambda data: data["artifacts"]["power_sdist"].update(sha256="0" * 64))
    _refresh_manifest_receipt_and_checksum(paths)
    with pytest.raises(ValueError, match="power_sdist"):
        _verify(paths)


def test_manifest_commit_mismatch_from_signed_tag_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    _rewrite_manifest(paths, lambda data: data.update(commit="b" * 40))
    _refresh_manifest_receipt_and_checksum(paths)
    with pytest.raises(ValueError, match="tag target"):
        _verify(paths)


def test_sha256sums_correct_but_manifest_sha_wrong_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    _rewrite_manifest(paths, lambda data: data["artifacts"]["power_wheel"].update(sha256="1" * 64))
    _refresh_manifest_receipt_and_checksum(paths)
    with pytest.raises(ValueError, match="power_wheel"):
        _verify(paths)


def test_correct_filename_with_wrong_public_content_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    wheel = Path(paths["asset_dir"]) / "power_framework-3.7.10-py3-none-any.whl"
    wheel.write_bytes(b"different bytes with the same filename")
    with pytest.raises(ValueError, match=r"asset|checksums|receipt"):
        _verify(paths)


def test_recovery_same_tag_with_different_package_bytes_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    wheel = Path(paths["asset_dir"]) / "power_framework-3.7.10-py3-none-any.whl"
    wheel.write_bytes(b"recovery rebuilt the same tag differently")
    with pytest.raises(ValueError, match=r"asset|checksums|receipt"):
        _verify(paths)


def test_attestation_subject_mismatch_from_final_digest_fails_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    receipt_path = Path(paths["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["attestation_subjects"][1]["subjects"] = ["sha256:" + "0" * 64]
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="attestation"):
        _verify(paths)


def test_attestation_subject_roles_cannot_be_swapped(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    receipt_path = Path(paths["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["attestation_subjects"][0]["role"] = "web"
    receipt["attestation_subjects"][1]["role"] = "package"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="attestation"):
        _verify(paths)
