"""Red Team Adversarial Test Suite for POWER 3.7.10 Release Verification.

Executes 10 distinct attack vectors against the candidate implementation:
1. Manifest wrong hash while SHA256SUMS correct.
2. Correct filename but wrong bytes / hash mismatch.
3. Tag target mismatch (commit SHA mismatch).
4. Receipt role mismatch (candidate vs final release receipt, invalid/swapped roles).
5. Package attestation subject mismatch.
6. Web attestation subject mismatch (receipt vs manifest vs profile evidence).
7. Source manifest mistaken for final manifest.
8. Recovery workflow produces different bytes.
9. PRXMX reads wrong manifest authority (ensuring public release manifest asset is required).
10. Public readback validates names but not hashes (comprehensive surface tampering).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.build_release_manifest import aggregate_tree_hash
from scripts.prxmx_power_runtime_audit import (
    ReleaseValidationError,
    _fetch_from_github,
    _fetch_from_local_source,
)
from scripts.verify_public_release_bindings import verify_public_release_bindings

TAG = "v3.7.10"
COMMIT = "a" * 40
IMAGE_DIGEST = "sha256:" + "f" * 64
REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _write_full_fixture(tmp_path: Path) -> dict[str, Any]:
    asset_dir = tmp_path / "public-assets"
    asset_dir.mkdir(exist_ok=True)
    wheel = asset_dir / "power_framework-3.7.10-py3-none-any.whl"
    sdist = asset_dir / "power_framework-3.7.10.tar.gz"
    dependency_lock = asset_dir / "power-native-requirements.txt"
    package_sbom = asset_dir / "power-framework-3.7.10.spdx.json"
    web_sbom = asset_dir / "power-web-3.7.10.spdx.json"
    profile = asset_dir / "power-profile-acceptance.json"
    baseline = asset_dir / "power-framework.release-baseline.json"

    skill_files = {"SKILL.md": b"---\nname: power\n---\n"}
    mcp_files = {"__init__.py": b"\n", "contract.py": b"MCP contract\n"}
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "power_framework-3.7.10.dist-info/METADATA",
            "Metadata-Version: 2.3\n"
            "Name: power-framework\n"
            "Version: 3.7.10\n"
            "Requires-Python: >=3.13,<3.15\n",
        )
        archive.writestr("power_framework/data/skills/power/SKILL.md", skill_files["SKILL.md"])
        for relative, content in mcp_files.items():
            archive.writestr("power_framework/mcp/" + relative, content)
    sdist.write_bytes(b"\x1f\x8b\x08\x00power_framework sdist content 3.7.10 candidate")
    dependency_lock.write_text(
        "mcp==2.1.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    package_sbom.write_bytes(b'{"spdxVersion":"SPDX-2.3","name":"power-framework"}\n')
    web_sbom.write_bytes(b'{"spdxVersion":"SPDX-2.3","name":"power-web"}\n')
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
    baseline.write_bytes(b'{"schema":"power.release.baseline.v1","version":"3.7.10"}\n')

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
        "attestations": ["github:11111", "github:22222"],
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
    checksum_files = [
        wheel,
        sdist,
        dependency_lock,
        package_sbom,
        web_sbom,
        profile,
        baseline,
        manifest_path,
    ]
    _write_checksums(checksums_path, checksum_files)

    receipt_path = asset_dir / "power-framework.release-receipt.json"
    receipt = {
        "schema_version": 2,
        "release": {"tag": TAG, "commit": COMMIT},
        "attestations": ["github:11111", "github:22222"],
        "attestation_subjects": [
            {
                "id": "github:11111",
                "role": "package",
                "subjects": sorted(
                    [_sha256_file(wheel), _sha256_file(sdist), _sha256_file(dependency_lock)]
                ),
            },
            {"id": "github:22222", "role": "web", "subjects": [IMAGE_DIGEST]},
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
        "wheel": wheel,
        "sdist": sdist,
        "dependency_lock": dependency_lock,
        "package_sbom": package_sbom,
        "web_sbom": web_sbom,
        "profile": profile,
        "baseline": baseline,
        "manifest": manifest_path,
        "checksums": checksums_path,
        "receipt": receipt_path,
        "commit": COMMIT,
        "tag": TAG,
    }


def _fixture_assets(fixture: dict[str, Any]) -> list[Path]:
    """Return every file asset that belongs in checksums and receipt fixtures."""
    return [
        fixture["wheel"],
        fixture["sdist"],
        fixture["dependency_lock"],
        fixture["package_sbom"],
        fixture["web_sbom"],
        fixture["profile"],
        fixture["baseline"],
        fixture["manifest"],
    ]


def _verify_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    return verify_public_release_bindings(
        tag=fixture["tag"],
        manifest_path=fixture["manifest"],
        checksums_path=fixture["checksums"],
        asset_dir=fixture["asset_dir"],
        receipt_path=fixture["receipt"],
        expected_tag_target=fixture["commit"],
    )


# =========================================================================
# ATTACK 1: Manifest wrong hash while SHA256SUMS correct
# =========================================================================


def test_attack_1_manifest_wrong_wheel_hash_while_sha256sums_correct(tmp_path: Path) -> None:
    """Attack 1a: Alter wheel sha256 in manifest while SHA256SUMS reflects actual bytes on disk."""
    fix = _write_full_fixture(tmp_path)
    manifest_data = json.loads(fix["manifest"].read_text(encoding="utf-8"))
    manifest_data["artifacts"]["power_wheel"]["sha256"] = "0" * 64
    fix["manifest"].write_text(json.dumps(manifest_data, sort_keys=True) + "\n", encoding="utf-8")

    files = _fixture_assets(fix)
    _write_checksums(fix["checksums"], files)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["unified_release_manifest"]["sha256"] = _sha256_file(fix["manifest"])
    receipt_data["assets"] = [{"name": f.name, "sha256": _sha256_file(f)} for f in files]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"manifest artifact power_wheel"):
        _verify_fixture(fix)


def test_attack_1_manifest_wrong_sdist_hash_while_sha256sums_correct(tmp_path: Path) -> None:
    """Attack 1b: Alter sdist sha256 in manifest while SHA256SUMS reflects actual bytes on disk."""
    fix = _write_full_fixture(tmp_path)
    manifest_data = json.loads(fix["manifest"].read_text(encoding="utf-8"))
    manifest_data["artifacts"]["power_sdist"]["sha256"] = "1" * 64
    fix["manifest"].write_text(json.dumps(manifest_data, sort_keys=True) + "\n", encoding="utf-8")

    files = _fixture_assets(fix)
    _write_checksums(fix["checksums"], files)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["unified_release_manifest"]["sha256"] = _sha256_file(fix["manifest"])
    receipt_data["assets"] = [{"name": f.name, "sha256": _sha256_file(f)} for f in files]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"manifest artifact power_sdist"):
        _verify_fixture(fix)


# =========================================================================
# ATTACK 2: Correct filename but wrong bytes / hash mismatch
# =========================================================================


def test_attack_2_tampered_wheel_bytes_same_filename(tmp_path: Path) -> None:
    """Attack 2a: Replace wheel with malicious payload under the identical filename."""
    fix = _write_full_fixture(tmp_path)
    fix["wheel"].write_bytes(b"MALICIOUS INJECTED WHEEL PAYLOAD")

    with pytest.raises(ValueError, match=r"public asset does not match SHA256SUMS"):
        _verify_fixture(fix)


def test_attack_2_tampered_wheel_local_prxmx_fetch(tmp_path: Path) -> None:
    """Attack 2b: PRXMX local audit checks wheel against manifest and catches altered bytes."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    pyproject = source_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "power-framework"\nversion = "3.7.10"\n')
    dist_dir = source_dir / "dist"
    dist_dir.mkdir()
    wheel = dist_dir / "power_framework-3.7.10-py3-none-any.whl"
    wheel.write_bytes(b"actual disk bytes")

    rel_dir = source_dir / "release"
    rel_dir.mkdir()
    manifest_file = rel_dir / "power-release-manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "schema": "power.release.manifest.v1",
                "version": "3.7.10",
                "artifacts": {
                    "power_wheel": {
                        "filename": wheel.name,
                        "sha256": "e" * 64,
                    }
                },
            }
        )
    )

    with pytest.raises(ReleaseValidationError, match=r"Wheel digest mismatch"):
        _fetch_from_local_source(source_dir, "v3.7.10")


# =========================================================================
# ATTACK 3: Tag target mismatch
# =========================================================================


def test_attack_3_manifest_commit_mismatch(tmp_path: Path) -> None:
    """Attack 3a: Manifest claims commit B while signed tag points to commit A."""
    fix = _write_full_fixture(tmp_path)
    manifest_data = json.loads(fix["manifest"].read_text(encoding="utf-8"))
    manifest_data["commit"] = "b" * 40
    fix["manifest"].write_text(json.dumps(manifest_data, sort_keys=True) + "\n", encoding="utf-8")

    files = _fixture_assets(fix)
    _write_checksums(fix["checksums"], files)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["unified_release_manifest"]["sha256"] = _sha256_file(fix["manifest"])
    receipt_data["assets"] = [{"name": f.name, "sha256": _sha256_file(f)} for f in files]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match=r"published release manifest commit does not match expected tag target"
    ):
        _verify_fixture(fix)


def test_attack_3_receipt_commit_mismatch(tmp_path: Path) -> None:
    """Attack 3b: Receipt points to different commit than manifest."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["release"]["commit"] = "c" * 40
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"release receipt commit does not match manifest commit"):
        _verify_fixture(fix)


# =========================================================================
# ATTACK 4: Receipt role mismatch
# =========================================================================


def test_attack_4_candidate_template_passed_as_final_manifest(tmp_path: Path) -> None:
    """Attack 4a: Candidate template manifest passed to public binding verifier."""
    fix = _write_full_fixture(tmp_path)
    template_manifest = {
        "schema": "power.release.manifest.template.v1",
        "authority": "candidate-only",
        "version": "3.7.10",
        "artifacts": {},
    }
    fix["manifest"].write_text(
        json.dumps(template_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )

    files = _fixture_assets(fix)
    _write_checksums(fix["checksums"], files)

    with pytest.raises(ValueError, match=r"published release manifest schema is invalid"):
        _verify_fixture(fix)


def test_attack_4_receipt_attestation_roles_swapped(tmp_path: Path) -> None:
    """Attack 4b: Attestation roles swapped between package and web."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["attestation_subjects"][0]["role"] = "web"
    receipt_data["attestation_subjects"][1]["role"] = "package"
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"attestation"):
        _verify_fixture(fix)


def test_attack_4_receipt_attestation_role_invalid_string(tmp_path: Path) -> None:
    """Attack 4c: Attestation role is set to unauthorized value."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["attestation_subjects"][0]["role"] = "candidate_release"
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"attestation role is invalid"):
        _verify_fixture(fix)


# =========================================================================
# ATTACK 5: Package attestation subject mismatch
# =========================================================================


def test_attack_5_package_attestation_subject_digest_tampered(tmp_path: Path) -> None:
    """Attack 5a: Package attestation subject digest in receipt altered."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["attestation_subjects"][0]["subjects"] = ["0" * 64, _sha256_file(fix["sdist"])]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"attestation subject does not match a final digest"):
        _verify_fixture(fix)


def test_attack_5_package_attestation_missing_sdist_subject(tmp_path: Path) -> None:
    """Attack 5b: Package attestation only covers wheel, omitting sdist."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["attestation_subjects"][0]["subjects"] = [_sha256_file(fix["wheel"])]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"attestation subjects do not cover every final wheel, sdist, and image digest",
    ):
        _verify_fixture(fix)


# =========================================================================
# ATTACK 6: Web attestation subject mismatch
# =========================================================================


def test_attack_6_web_attestation_subject_tampered(tmp_path: Path) -> None:
    """Attack 6a: Web attestation subject altered to point to a different container digest."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["attestation_subjects"][1]["subjects"] = ["sha256:" + "9" * 64]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"attestation subject does not match a final digest"):
        _verify_fixture(fix)


def test_attack_6_profile_evidence_image_digest_mismatch(tmp_path: Path) -> None:
    """Attack 6b: Profile evidence image digest differs from manifest web image digest."""
    fix = _write_full_fixture(tmp_path)
    profile_data = json.loads(fix["profile"].read_text(encoding="utf-8"))
    profile_data["image_digest"] = "sha256:" + "8" * 64
    fix["profile"].write_text(json.dumps(profile_data, sort_keys=True) + "\n", encoding="utf-8")

    files = _fixture_assets(fix)
    _write_checksums(fix["checksums"], files)
    manifest_data = json.loads(fix["manifest"].read_text(encoding="utf-8"))
    manifest_data["artifacts"]["profile_evidence"]["sha256"] = _sha256_file(fix["profile"])
    fix["manifest"].write_text(json.dumps(manifest_data, sort_keys=True) + "\n", encoding="utf-8")
    _write_checksums(fix["checksums"], files)

    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["unified_release_manifest"]["sha256"] = _sha256_file(fix["manifest"])
    receipt_data["assets"] = [{"name": f.name, "sha256": _sha256_file(f)} for f in files]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match=r"Profile B image digest does not match manifest image digest"
    ):
        _verify_fixture(fix)


# =========================================================================
# ATTACK 7: Source manifest mistaken for final manifest
# =========================================================================


def test_attack_7_source_manifest_rejected_as_final_manifest(tmp_path: Path) -> None:
    """Attack 7a: verify_public_release_bindings rejects source repo template manifest."""
    source_manifest_path = REPO_ROOT / "release" / "power-release-manifest.json"
    fix = _write_full_fixture(tmp_path)
    fix["manifest"].write_text(source_manifest_path.read_text(encoding="utf-8"), encoding="utf-8")

    files = _fixture_assets(fix)
    _write_checksums(fix["checksums"], files)

    with pytest.raises(ValueError, match=r"published release manifest schema is invalid"):
        _verify_fixture(fix)


def test_attack_7_prxmx_refuses_source_template_as_public_proof(tmp_path: Path) -> None:
    """Attack 7b: PRXMX local audit ignores source manifest template artifacts."""
    source_dir = tmp_path / "repo"
    source_dir.mkdir()
    (source_dir / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.10"\n'
    )
    (source_dir / "release").mkdir()
    (source_dir / "release" / "power-release-manifest.json").write_text(
        json.dumps(
            {
                "schema": "power.release.manifest.template.v1",
                "authority": "candidate-only",
                "version": "3.7.10",
                "artifacts": {},
            }
        )
    )
    payload = _fetch_from_local_source(source_dir, "v3.7.10")
    assert payload.manifest == {}
    assert payload.wheel_sha256 is None


def test_attack_7_source_manifest_template_missing_candidate_authority_fails(
    tmp_path: Path,
) -> None:
    """Attack 7c: PRXMX rejects source template that omits authority=candidate-only."""
    source_dir = tmp_path / "repo"
    source_dir.mkdir()
    (source_dir / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.10"\n'
    )
    (source_dir / "release").mkdir()
    (source_dir / "release" / "power-release-manifest.json").write_text(
        json.dumps(
            {
                "schema": "power.release.manifest.template.v1",
                "authority": "public-release-authority",
                "version": "3.7.10",
            }
        )
    )
    with pytest.raises(
        ReleaseValidationError,
        match=r"source release manifest template must declare authority=candidate-only",
    ):
        _fetch_from_local_source(source_dir, "v3.7.10")


# =========================================================================
# ATTACK 8: Recovery workflow produces different bytes
# =========================================================================


def test_attack_8_recovery_rebuild_differs_fails_closed(tmp_path: Path) -> None:
    """Attack 8a: Same-tag recovery build produces different wheel bytes."""
    fix = _write_full_fixture(tmp_path)
    fix["wheel"].write_bytes(b"RECOVERY RUN BUILT DIFFERENT BYTES FOR 3.7.10")

    with pytest.raises(ValueError, match=r"public asset does not match SHA256SUMS"):
        _verify_fixture(fix)


# =========================================================================
# ATTACK 9: PRXMX reads wrong manifest authority
# =========================================================================


def test_attack_9_prxmx_github_fetch_missing_published_manifest_fails_closed() -> None:
    """Attack 9a: GitHub Release has raw files but lacks published power-release-manifest.json asset."""
    release_payload = {
        "tag_name": "v3.7.10",
        "assets": [
            {"name": "power_framework-3.7.10-py3-none-any.whl", "digest": "sha256:" + "a" * 64}
        ],
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp_rel = MagicMock()
        mock_resp_rel.read.return_value = json.dumps(release_payload).encode()
        mock_resp_rel.__enter__.return_value = mock_resp_rel

        mock_resp_pyproj = MagicMock()
        mock_resp_pyproj.read.return_value = (
            b'[project]\nname = "power-framework"\nversion = "3.7.10"\n'
        )
        mock_resp_pyproj.__enter__.return_value = mock_resp_pyproj

        mock_urlopen.side_effect = [mock_resp_rel, mock_resp_pyproj]

        with pytest.raises(
            ReleaseValidationError,
            match=r"GitHub release must contain exactly one published power-release-manifest\.json asset",
        ):
            _fetch_from_github("weby-homelab/power-framework", "v3.7.10")


def test_attack_9_prxmx_github_fetch_manifest_bytes_hash_mismatch() -> None:
    """Attack 9b: GitHub release manifest asset bytes do not match GitHub API asset digest."""
    manifest_bytes = b'{"schema": "power.release.manifest.v1", "version": "3.7.10"}'
    wrong_digest = "sha256:" + "0" * 64

    release_payload = {
        "tag_name": "v3.7.10",
        "assets": [
            {"name": "power-release-manifest.json", "digest": wrong_digest},
            {"name": "power_framework-3.7.10-py3-none-any.whl", "digest": "sha256:" + "a" * 64},
        ],
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp_rel = MagicMock()
        mock_resp_rel.read.return_value = json.dumps(release_payload).encode()
        mock_resp_rel.__enter__.return_value = mock_resp_rel

        mock_resp_pyproj = MagicMock()
        mock_resp_pyproj.read.return_value = (
            b'[project]\nname = "power-framework"\nversion = "3.7.10"\n'
        )
        mock_resp_pyproj.__enter__.return_value = mock_resp_pyproj

        mock_resp_manifest = MagicMock()
        mock_resp_manifest.read.return_value = manifest_bytes
        mock_resp_manifest.__enter__.return_value = mock_resp_manifest

        mock_urlopen.side_effect = [mock_resp_rel, mock_resp_pyproj, mock_resp_manifest]

        with pytest.raises(
            ReleaseValidationError,
            match="published release manifest bytes do not match the GitHub asset digest",
        ):
            _fetch_from_github("weby-homelab/power-framework", "v3.7.10")


# =========================================================================
# ATTACK 10: Public readback validates names but not hashes
# =========================================================================


def test_attack_10_all_filenames_present_but_wheel_hash_tampered_in_receipt(tmp_path: Path) -> None:
    """Attack 10a: All files exist on disk with matching names and SHA256SUMS, but receipt asset hash is wrong."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    for item in receipt_data["assets"]:
        if item["name"] == fix["wheel"].name:
            item["sha256"] = "3" * 64
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"receipt asset digest mismatch for power_framework-3.7.10-py3-none-any.whl",
    ):
        _verify_fixture(fix)


def test_attack_10_unexpected_extra_file_in_public_dir_fails_closed(tmp_path: Path) -> None:
    """Attack 10b: Unverified extra file in public release directory."""
    fix = _write_full_fixture(tmp_path)
    extra = fix["asset_dir"] / "untracked_binary.bin"
    extra.write_bytes(b"untracked payload")

    with pytest.raises(ValueError, match=r"public asset set differs from SHA256SUMS"):
        _verify_fixture(fix)


def test_attack_10_missing_file_from_public_dir_fails_closed(tmp_path: Path) -> None:
    """Attack 10c: Required file in SHA256SUMS deleted from public directory."""
    fix = _write_full_fixture(tmp_path)
    fix["baseline"].unlink()

    with pytest.raises(ValueError, match=r"public asset set differs from SHA256SUMS"):
        _verify_fixture(fix)


def test_attack_10_receipt_missing_hash_binding_fails_closed(tmp_path: Path) -> None:
    """Attack 10d: Receipt assets list omits a required manifest file."""
    fix = _write_full_fixture(tmp_path)
    receipt_data = json.loads(fix["receipt"].read_text(encoding="utf-8"))
    receipt_data["assets"] = [
        item for item in receipt_data["assets"] if item["name"] != fix["sdist"].name
    ]
    fix["receipt"].write_text(json.dumps(receipt_data, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"release receipt is missing hash bindings"):
        _verify_fixture(fix)
