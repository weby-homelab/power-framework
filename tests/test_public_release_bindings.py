"""Adversarial tests for zero-trust public release binding verification."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scripts.build_release_manifest import aggregate_tree_hash
from scripts.verify_public_release_bindings import (
    _validate_hash_pinned_lock,
    verify_public_release_bindings,
)

TAG = "v3.7.10"
COMMIT = "a" * 40
IMAGE_DIGEST = "sha256:" + "f" * 64
PIP_OPTION_DIRECTIVES = (
    "--index-url https://example.invalid/simple",
    "--extra-index-url https://example.invalid/simple",
    "--trusted-host example.invalid",
    "--find-links /tmp/packages",
    "-r other-requirements.txt",
    "--requirement other-requirements.txt",
    "-c constraints.txt",
    "--constraint constraints.txt",
)


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


@pytest.mark.parametrize("directive", PIP_OPTION_DIRECTIVES)
def test_public_lock_validator_rejects_top_level_pip_directives(
    tmp_path: Path, directive: str
) -> None:
    lock = tmp_path / "power-native-requirements.txt"
    lock.write_text(
        f"{directive}\nexample==1.0 --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pip option lines"):
        _validate_hash_pinned_lock(lock)


def test_public_lock_validator_accepts_hashed_requirement(tmp_path: Path) -> None:
    lock = tmp_path / "power-native-requirements.txt"
    lock.write_text(f"example==1.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")

    _validate_hash_pinned_lock(lock)


def _write_fixture(tmp_path: Path) -> dict[str, Path | str]:
    asset_dir = tmp_path / "public-assets"
    asset_dir.mkdir()
    wheel = asset_dir / "power_framework-3.7.10-py3-none-any.whl"
    sdist = asset_dir / "power_framework-3.7.10.tar.gz"
    dependency_lock = asset_dir / "power-native-requirements.txt"
    package_sbom = asset_dir / "power-framework-3.7.10.spdx.json"
    web_sbom = asset_dir / "power-web-3.7.10.spdx.json"
    profile = asset_dir / "power-profile-acceptance.json"
    skill_files = {
        "SKILL.md": b"---\nname: power\n---\n",
        "references/runtime-contract.md": b"runtime contract\n",
    }
    mcp_files = {
        "__init__.py": b"\n",
        "contract.py": b"MCP contract\n",
    }
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "power_framework-3.7.10.dist-info/METADATA",
            "Metadata-Version: 2.3\n"
            "Name: power-framework\n"
            "Version: 3.7.10\n"
            "Requires-Python: >=3.13,<3.15\n",
        )
        for relative, content in {**skill_files, **mcp_files}.items():
            prefix = (
                "power_framework/data/skills/power/"
                if relative in skill_files
                else "power_framework/mcp/"
            )
            archive.writestr(prefix + relative, content)
    sdist.write_bytes(b"sdist bytes from the frozen candidate")
    dependency_lock.write_text(
        "mcp==2.1.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
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
        "application_schema": "power.application.v2",
        "profiles": {
            "native": ["power", "power-mcp"],
            "web": ["power-web"],
            "skill": ["power"],
            "profile_a": {
                "status": "mcp-required",
                "mcp_transport": "stdio",
                "docker_web_containers": 0,
            },
            "profile_b": {
                "status": "web-only-container",
                "capabilities": ["web", "semantic", "rerank"],
                "mcp_services": 0,
            },
        },
        "mcp": {
            "entry_point": "power-mcp",
            "transport": "stdio",
            "vault_environment": "POWER_VAULT_DIR",
        },
        "web": {
            "entry_point": "power-web",
            "transport": "asgi",
            "port": 8080,
            "application_service_boundary": True,
        },
        "skill_tree_sha256": aggregate_tree_hash(skill_files),
        "mcp_contract_sha256": aggregate_tree_hash(mcp_files),
        "attestations": ["github:package-1", "github:web-1"],
        "artifacts": {
            "power_wheel": {"filename": wheel.name, "sha256": _sha256_file(wheel)},
            "power_sdist": {"filename": sdist.name, "sha256": _sha256_file(sdist)},
            "native_dependency_lock": {
                "filename": dependency_lock.name,
                "sha256": _sha256_file(dependency_lock),
            },
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
    checksum_files = [wheel, sdist, dependency_lock, package_sbom, web_sbom, profile, manifest_path]
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
                "subjects": [
                    _sha256_file(wheel),
                    _sha256_file(sdist),
                    _sha256_file(dependency_lock),
                ],
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
        "dependency_lock": dependency_lock,
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


def test_strict_release_provenance_binds_tag_and_workflow_context(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    receipt_path = Path(paths["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    tree = "b" * 40
    control_revision = "d" * 40
    receipt["release"].update(
        {
            "repository": "weby-homelab/power-framework",
            "tree": tree,
        }
    )
    receipt["release_provenance"] = {
        "release_source_tag": TAG,
        "release_source_commit": COMMIT,
        "release_source_tree": tree,
        "release_tag_object": "c" * 40,
        "release_control_revision": control_revision,
        "workflow_revision": control_revision,
        "workflow_run_id": "42",
        "workflow_run_attempt": "1",
        "workflow_event": "push",
        "workflow_ref": f"refs/tags/{TAG}",
        "workflow_ref_protected": "false",
        "repository": "weby-homelab/power-framework",
    }
    receipt["workflow_run"] = {
        "id": "42",
        "attempt": "1",
        "event": "push",
        "ref": f"refs/tags/{TAG}",
        "repository": "weby-homelab/power-framework",
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_public_release_bindings(
        tag=TAG,
        manifest_path=Path(paths["manifest"]),
        checksums_path=Path(paths["checksums"]),
        asset_dir=Path(paths["asset_dir"]),
        receipt_path=receipt_path,
        expected_tag_target=COMMIT,
        expected_tag_object="c" * 40,
        expected_tag_tree=tree,
        expected_release_control_revision=control_revision,
        expected_workflow_revision=control_revision,
        expected_workflow_run_id="42",
        expected_workflow_attempt="1",
        expected_workflow_event="push",
        expected_workflow_ref=f"refs/tags/{TAG}",
        expected_workflow_ref_protected="false",
        expected_repository="weby-homelab/power-framework",
        require_release_provenance=True,
    )
    assert result["release_provenance_status"] == "verified"


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


def test_workflow_attestation_ids_must_match_manifest_and_receipt(
    tmp_path: Path,
) -> None:
    paths = _write_fixture(tmp_path)
    with pytest.raises(ValueError, match="workflow outputs"):
        verify_public_release_bindings(
            tag=TAG,
            manifest_path=Path(paths["manifest"]),
            checksums_path=Path(paths["checksums"]),
            asset_dir=Path(paths["asset_dir"]),
            receipt_path=Path(paths["receipt"]),
            expected_tag_target=COMMIT,
            expected_attestation_ids=["package-1", "wrong-web-id"],
        )
