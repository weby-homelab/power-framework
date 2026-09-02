#!/usr/bin/env python3
"""Verify public release bytes against checksums, manifest, receipt, and attestations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

try:
    from release_bindings import (
        normalize_attestation_id,
        required_git_object,
        required_positive_integer,
        required_repository,
        required_text,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.release_bindings import (
        normalize_attestation_id,
        required_git_object,
        required_positive_integer,
        required_repository,
        required_text,
    )

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RELEASE_EVENTS = frozenset({"push", "workflow_dispatch"})
REQUIRED_ARTIFACTS = (
    "power_wheel",
    "power_sdist",
    "native_dependency_lock",
    "package_sbom",
    "web_sbom",
    "profile_evidence",
    "web_image",
)


def _load_json(path: Path, description: str) -> dict[str, Any]:
    """Load one regular JSON object without following a symlink input."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{description} is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must contain a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    """Calculate a file digest in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_asset_path(asset_dir: Path, name: Any) -> Path:
    """Resolve a release asset name while forbidding traversal and symlinks."""
    if not isinstance(name, str) or not name or name != Path(name).name:
        raise ValueError(f"release asset name is not a safe filename: {name!r}")
    if "\\" in name or "\0" in name or name in {".", ".."}:
        raise ValueError(f"release asset name is not a safe filename: {name!r}")
    path = asset_dir / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"release asset is missing or symlinked: {name}")
    return path


def _parse_checksums(path: Path) -> dict[str, str]:
    """Parse a strict SHA256SUMS file with unique, basename-only entries."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"SHA256SUMS is not a regular file: {path}")
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError(f"SHA256SUMS line {number} is malformed")
        digest, name = fields[0].strip(), fields[1].strip()
        if not HASH_RE.fullmatch(digest):
            raise ValueError(f"SHA256SUMS line {number} has an invalid digest")
        if name.startswith("*"):
            name = name[1:]
        if not name or name != Path(name).name or "\\" in name or "\0" in name:
            raise ValueError(f"SHA256SUMS line {number} has an unsafe filename")
        if name in entries:
            raise ValueError(f"SHA256SUMS contains a duplicate filename: {name}")
        entries[name] = digest
    if not entries:
        raise ValueError("SHA256SUMS must contain at least one asset")
    return entries


def _tag_version(tag: str) -> str:
    """Return the stable version encoded by a release tag."""
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        raise ValueError(f"release tag is not a stable v<major>.<minor>.<patch> tag: {tag!r}")
    return tag.removeprefix("v")


def _digest_value(value: Any, label: str) -> str:
    """Validate one lowercase SHA-256 value."""
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _canonical_subject(value: Any, label: str) -> str:
    """Validate an attestation subject and normalize package/image notation."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    subject = value.strip()
    if subject.startswith("sha256:"):
        if IMAGE_DIGEST_RE.fullmatch(subject) is None:
            raise ValueError(f"{label} must be a SHA-256 subject")
        return subject
    return _digest_value(subject, label)


def _verify_release_provenance(
    receipt: dict[str, Any],
    *,
    tag: str,
    commit: str,
    expected_tag_object: str | None,
    expected_tag_tree: str | None,
    expected_release_control_revision: str | None,
    expected_workflow_revision: str | None,
    expected_workflow_run_id: str | None,
    expected_workflow_attempt: str | None,
    expected_workflow_event: str | None,
    expected_workflow_ref: str | None,
    expected_workflow_ref_protected: str | None,
    expected_repository: str | None,
    require: bool,
) -> dict[str, str] | None:
    """Verify source/control provenance and optional trusted workflow bindings."""
    provenance = receipt.get("release_provenance")
    expected_values = {
        "expected tag object": expected_tag_object,
        "expected tag tree": expected_tag_tree,
        "expected release control revision": expected_release_control_revision,
        "expected workflow revision": expected_workflow_revision,
        "expected workflow run ID": expected_workflow_run_id,
        "expected workflow attempt": expected_workflow_attempt,
        "expected workflow event": expected_workflow_event,
        "expected workflow ref": expected_workflow_ref,
        "expected workflow ref protection state": expected_workflow_ref_protected,
        "expected repository": expected_repository,
    }
    if provenance is None:
        if require:
            raise ValueError("release provenance is required for strict public verification")
        if any(value is not None for value in expected_values.values()):
            raise ValueError("trusted provenance expectations require release provenance")
        return None
    if not isinstance(provenance, dict):
        raise ValueError("release_provenance must be an object")
    if require:
        missing_expectations = [label for label, value in expected_values.items() if value is None]
        if missing_expectations:
            raise ValueError(
                "strict release provenance requires " + ", ".join(missing_expectations)
            )

    source_tag = required_text(provenance.get("release_source_tag"), "release source tag")
    if TAG_RE.fullmatch(source_tag) is None:
        raise ValueError("release source tag must be a stable v<major>.<minor>.<patch> tag")
    source_commit = required_git_object(
        provenance.get("release_source_commit"), "release source commit"
    )
    source_tree = required_git_object(provenance.get("release_source_tree"), "release source tree")
    tag_object = required_git_object(provenance.get("release_tag_object"), "release tag object")
    control_revision = required_git_object(
        provenance.get("release_control_revision"), "release control revision"
    )
    workflow_revision = required_git_object(
        provenance.get("workflow_revision"), "workflow revision"
    )
    workflow_run_id = required_positive_integer(
        provenance.get("workflow_run_id"), "workflow run ID"
    )
    workflow_attempt = required_positive_integer(
        provenance.get("workflow_run_attempt"), "workflow run attempt"
    )
    workflow_event = required_text(provenance.get("workflow_event"), "workflow event")
    if workflow_event not in RELEASE_EVENTS:
        raise ValueError(f"workflow event is not a supported release event: {workflow_event}")
    workflow_ref = required_text(provenance.get("workflow_ref"), "workflow ref")
    expected_ref = (
        "refs/heads/main" if workflow_event == "workflow_dispatch" else f"refs/tags/{tag}"
    )
    if workflow_ref != expected_ref:
        raise ValueError(f"workflow ref does not match release event: expected {expected_ref}")
    ref_protected = required_text(
        provenance.get("workflow_ref_protected"), "workflow ref protection state"
    )
    if ref_protected not in {"true", "false"}:
        raise ValueError("workflow ref protection state must be true or false")
    if workflow_event == "workflow_dispatch" and ref_protected != "true":
        raise ValueError("workflow_dispatch release control ref must be protected")
    repository = required_repository(provenance.get("repository"), "provenance repository")

    release = receipt.get("release")
    if not isinstance(release, dict):
        raise ValueError("release receipt release must be an object")
    release_tree = required_git_object(release.get("tree"), "release receipt source tree")
    release_repository = required_repository(
        release.get("repository"), "release receipt repository"
    )
    if source_tag != tag or source_tag != release.get("tag"):
        raise ValueError("release provenance source tag does not match receipt identity")
    if source_commit != commit or source_commit != release.get("commit"):
        raise ValueError("release provenance source commit does not match receipt identity")
    if source_tree != release_tree:
        raise ValueError("release provenance source tree does not match receipt identity")
    if repository != release_repository:
        raise ValueError("release provenance repository does not match receipt identity")
    if control_revision != workflow_revision:
        raise ValueError("release control revision does not match workflow revision")

    workflow_run = receipt.get("workflow_run")
    if not isinstance(workflow_run, dict):
        raise ValueError("workflow_run is required with release provenance")
    if required_positive_integer(workflow_run.get("id"), "workflow_run.id") != workflow_run_id:
        raise ValueError("workflow_run.id does not match release provenance")
    if (
        required_positive_integer(workflow_run.get("attempt"), "workflow_run.attempt")
        != workflow_attempt
    ):
        raise ValueError("workflow_run.attempt does not match release provenance")
    if required_text(workflow_run.get("event"), "workflow_run.event") != workflow_event:
        raise ValueError("workflow_run.event does not match release provenance")
    if required_text(workflow_run.get("ref"), "workflow_run.ref") != workflow_ref:
        raise ValueError("workflow_run.ref does not match release provenance")
    if required_repository(workflow_run.get("repository"), "workflow_run.repository") != repository:
        raise ValueError("workflow_run.repository does not match release provenance")

    comparisons = {
        "expected tag object": (expected_tag_object, tag_object),
        "expected tag tree": (expected_tag_tree, source_tree),
        "expected release control revision": (expected_release_control_revision, control_revision),
        "expected workflow revision": (expected_workflow_revision, workflow_revision),
        "expected workflow run ID": (expected_workflow_run_id, workflow_run_id),
        "expected workflow attempt": (expected_workflow_attempt, workflow_attempt),
        "expected workflow event": (expected_workflow_event, workflow_event),
        "expected workflow ref": (expected_workflow_ref, workflow_ref),
        "expected workflow ref protection state": (expected_workflow_ref_protected, ref_protected),
        "expected repository": (expected_repository, repository),
    }
    for label, (expected, actual) in comparisons.items():
        if expected is not None and required_text(expected, label) != actual:
            raise ValueError(f"{label} does not match release provenance")

    return {
        "release_source_tag": source_tag,
        "release_source_commit": source_commit,
        "release_source_tree": source_tree,
        "release_tag_object": tag_object,
        "release_control_revision": control_revision,
        "workflow_revision": workflow_revision,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_attempt,
        "workflow_event": workflow_event,
        "workflow_ref": workflow_ref,
        "workflow_ref_protected": ref_protected,
        "repository": repository,
    }


def _aggregate_tree_hash(files: dict[str, bytes]) -> str:
    """Hash one packaged tree using the release manifest ordering contract."""
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[relative]).digest())
    return digest.hexdigest()


def _wheel_tree(path: Path, prefix: str) -> dict[str, bytes]:
    """Read one package-data subtree without extracting untrusted ZIP paths."""
    try:
        with zipfile.ZipFile(path) as archive:
            files: dict[str, bytes] = {}
            for name in archive.namelist():
                if not name.startswith(prefix) or name.endswith("/"):
                    continue
                relative = name[len(prefix) :]
                if (
                    not relative
                    or relative.startswith("/")
                    or ".." in Path(relative).parts
                    or "__pycache__" in relative
                    or relative.endswith(".pyc")
                ):
                    raise ValueError("release wheel contains an unsafe packaged path")
                if relative in files:
                    raise ValueError("release wheel contains duplicate packaged paths")
                files[relative] = archive.read(name)
            return files
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeError) as exc:
        raise ValueError("published power wheel is not a valid readable archive") from exc


def _wheel_metadata(path: Path) -> dict[str, str]:
    """Read the identity fields that bind a public wheel to the manifest."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError("published power wheel must contain one dist-info METADATA")
            fields: dict[str, str] = {}
            for line in archive.read(names[0]).decode("utf-8").splitlines():
                key, separator, value = line.partition(":")
                if separator and key in {"Name", "Version", "Requires-Python"}:
                    fields[key] = value.strip()
            return fields
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeError) as exc:
        raise ValueError("published power wheel metadata is unreadable") from exc


def _validate_manifest_semantics(manifest: dict[str, Any], version: str) -> None:
    """Validate the non-artifact runtime contract before trusting public bytes."""
    if manifest.get("repository") != "weby-homelab/power-framework":
        raise ValueError("published release manifest repository is not trusted")
    if manifest.get("application_schema") != "power.application.v2":
        raise ValueError("published release manifest application schema is invalid")
    requires_python = manifest.get("requires_python")
    if not isinstance(requires_python, str) or not requires_python.strip():
        raise ValueError("published release manifest requires_python is invalid")

    profiles = manifest.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("published release manifest profiles are missing")
    if profiles.get("native") != ["power", "power-mcp"]:
        raise ValueError("published release manifest native profile is invalid")
    if profiles.get("web") != ["power-web"] or profiles.get("skill") != ["power"]:
        raise ValueError("published release manifest Web or Skill profile is invalid")
    profile_a = profiles.get("profile_a")
    if (
        not isinstance(profile_a, dict)
        or profile_a.get("status") != "mcp-required"
        or profile_a.get("mcp_transport") != "stdio"
        or profile_a.get("docker_web_containers") != 0
    ):
        raise ValueError("published release manifest Profile A is invalid")
    profile_b = profiles.get("profile_b")
    if (
        not isinstance(profile_b, dict)
        or profile_b.get("status") != "web-only-container"
        or profile_b.get("capabilities") != ["web", "semantic", "rerank"]
        or profile_b.get("mcp_services") != 0
    ):
        raise ValueError("published release manifest Profile B is invalid")

    mcp = manifest.get("mcp")
    if (
        not isinstance(mcp, dict)
        or mcp.get("entry_point") != "power-mcp"
        or mcp.get("transport") != "stdio"
        or mcp.get("vault_environment") != "POWER_VAULT_DIR"
    ):
        raise ValueError("published release manifest MCP contract is invalid")
    web = manifest.get("web")
    if (
        not isinstance(web, dict)
        or web.get("entry_point") != "power-web"
        or web.get("transport") != "asgi"
        or web.get("port") != 8080
        or web.get("application_service_boundary") is not True
    ):
        raise ValueError("published release manifest Web contract is invalid")

    for key in ("skill_tree_sha256", "mcp_contract_sha256"):
        _digest_value(manifest.get(key), f"published release manifest {key}")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("published release manifest artifacts are missing")
    if set(artifacts) != set(REQUIRED_ARTIFACTS):
        raise ValueError("published release manifest artifact set is not exact")
    image = artifacts.get("web_image")
    if not isinstance(image, dict) or image.get("filename") is not None:
        if not isinstance(image, dict):
            raise ValueError("published release manifest Web image artifact is invalid")
        raise ValueError("published Web image must be represented by a registry digest")
    expected_reference = f"ghcr.io/weby-homelab/power-framework-web:{version}"
    if image.get("reference") != expected_reference:
        raise ValueError("published Web image reference does not match the release version")


def _validate_wheel_contract(manifest: dict[str, Any], wheel_path: Path, version: str) -> None:
    """Bind wheel metadata and packaged contract trees to manifest digests."""
    metadata = _wheel_metadata(wheel_path)
    if metadata.get("Name") != "power-framework":
        raise ValueError("published wheel distribution name is invalid")
    if metadata.get("Version") != version:
        raise ValueError("published wheel version does not match the release tag")
    if metadata.get("Requires-Python") != manifest.get("requires_python"):
        raise ValueError("published wheel Python requirement does not match the manifest")
    skill_files = _wheel_tree(wheel_path, "power_framework/data/skills/power/")
    if "SKILL.md" not in skill_files:
        raise ValueError("published wheel does not contain the POWER Skill")
    if _aggregate_tree_hash(skill_files) != manifest["skill_tree_sha256"]:
        raise ValueError("published wheel Skill tree does not match the manifest")
    mcp_files = _wheel_tree(wheel_path, "power_framework/mcp/")
    if not mcp_files:
        raise ValueError("published wheel does not contain the MCP contract")
    if _aggregate_tree_hash(mcp_files) != manifest["mcp_contract_sha256"]:
        raise ValueError("published wheel MCP tree does not match the manifest")


def _validate_hash_pinned_lock(path: Path) -> None:
    """Require every exported dependency entry to contain a valid SHA-256."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("published native dependency lock is unreadable") from exc
    requirements = 0
    hashes = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        continuation = raw_line[0].isspace()
        if not continuation and line.startswith(("-e ", "--editable ")):
            raise ValueError(
                "published native dependency lock must not contain editable requirements"
            )
        if not continuation and line.startswith(("git+", "git://", "file:", "http://", "https://")):
            raise ValueError(
                "published native dependency lock must not contain local or VCS requirements"
            )
        if not continuation and (" @ git+" in line or " @ file:" in line or " @ http" in line):
            raise ValueError(
                "published native dependency lock must not contain direct URL requirements"
            )
        if not continuation and line.startswith("-"):
            raise ValueError("published native dependency lock must not contain pip option lines")
        if not continuation:
            requirements += 1
        for marker in re.findall(r"--hash=sha256:[^\s\\]+", line):
            if re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", marker) is None:
                raise ValueError("published native dependency lock contains an invalid hash")
            hashes += 1
    if requirements == 0 or hashes < requirements:
        raise ValueError("published native dependency lock must hash every requirement")


def _manifest_file_artifacts(
    manifest: dict[str, Any], asset_dir: Path, checksums: dict[str, str], version: str
) -> tuple[dict[str, str], str]:
    """Verify every final file artifact and return filename hashes plus image digest."""
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("release manifest artifacts must be an object")
    for key in REQUIRED_ARTIFACTS:
        if not isinstance(artifacts.get(key), dict):
            raise ValueError(f"release manifest is missing final artifact: {key}")
    if set(artifacts) != set(REQUIRED_ARTIFACTS):
        raise ValueError("release manifest artifact set is not exact")

    file_hashes: dict[str, str] = {}
    expected_filenames = {
        "power_wheel": f"power_framework-{version}-py3-none-any.whl",
        "power_sdist": f"power_framework-{version}.tar.gz",
        "native_dependency_lock": "power-native-requirements.txt",
        "package_sbom": f"power-framework-{version}.spdx.json",
        "web_sbom": f"power-web-{version}.spdx.json",
        "profile_evidence": "power-profile-acceptance.json",
    }
    for key, entry in artifacts.items():
        if not isinstance(entry, dict):
            raise ValueError(f"release manifest artifact {key} must be an object")
        filename = entry.get("filename")
        if key in expected_filenames and not isinstance(filename, str):
            raise ValueError(f"manifest artifact {key} must declare a filename")
        if filename is None:
            continue
        if key in expected_filenames and filename != expected_filenames[key]:
            raise ValueError(
                f"manifest artifact {key} filename does not match release version: {filename}"
            )
        path = _safe_asset_path(asset_dir, filename)
        expected = _digest_value(entry.get("sha256"), f"manifest artifact {key}.sha256")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"manifest artifact {key} digest mismatch for {filename}: "
                f"expected {expected}, got {actual}"
            )
        if checksums.get(filename) != expected:
            raise ValueError(f"manifest artifact {key} does not match SHA256SUMS for {filename}")
        if key == "native_dependency_lock":
            _validate_hash_pinned_lock(path)
        file_hashes[filename] = expected

    image_entry = artifacts["web_image"]
    if image_entry.get("filename") is not None:
        raise ValueError("release manifest Web image must not declare a file name")
    image_digest = image_entry.get("digest")
    if not isinstance(image_digest, str) or IMAGE_DIGEST_RE.fullmatch(image_digest) is None:
        raise ValueError("manifest web_image.digest must use sha256:<64 lowercase hex>")
    _validate_wheel_contract(
        manifest,
        _safe_asset_path(asset_dir, artifacts["power_wheel"]["filename"]),
        version,
    )
    return file_hashes, image_digest


def _verify_receipt(
    receipt: dict[str, Any],
    *,
    tag: str,
    commit: str,
    manifest_path: Path,
    manifest_hash: str,
    asset_dir: Path,
    required_files: set[str],
    expected_tag_object: str | None,
    expected_tag_tree: str | None,
    expected_release_control_revision: str | None,
    expected_workflow_revision: str | None,
    expected_workflow_run_id: str | None,
    expected_workflow_attempt: str | None,
    expected_workflow_event: str | None,
    expected_workflow_ref: str | None,
    expected_workflow_ref_protected: str | None,
    expected_repository: str | None,
    require_release_provenance: bool,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    """Verify receipt identity, file hashes, attestation IDs, and subjects."""
    if receipt.get("schema_version") != 2:
        raise ValueError("release receipt schema_version must be 2")
    if manifest_path.parent.resolve() != asset_dir.resolve():
        raise ValueError("release manifest must be inside the public asset directory")
    release = receipt.get("release")
    if not isinstance(release, dict):
        raise ValueError("release receipt release must be an object")
    if release.get("tag") != tag:
        raise ValueError("release receipt tag does not match requested tag")
    if release.get("commit") != commit:
        raise ValueError("release receipt commit does not match manifest commit")

    manifest_binding = receipt.get("unified_release_manifest")
    if not isinstance(manifest_binding, dict):
        raise ValueError("release receipt manifest binding is missing")
    if manifest_binding.get("name") != manifest_path.name:
        raise ValueError("release receipt manifest name does not match downloaded manifest")
    if manifest_binding.get("sha256") != manifest_hash:
        raise ValueError("release receipt manifest SHA-256 does not match downloaded manifest")

    receipt_assets = receipt.get("assets")
    if not isinstance(receipt_assets, list):
        raise ValueError("release receipt assets must be a list")
    receipt_hashes: dict[str, str] = {}
    for item in receipt_assets:
        if not isinstance(item, dict):
            raise ValueError("release receipt asset entry must be an object")
        name = item.get("name")
        path = _safe_asset_path(asset_dir, name)
        digest = _digest_value(item.get("sha256"), f"receipt asset {name}.sha256")
        actual = _sha256(path)
        if actual != digest:
            raise ValueError(f"receipt asset digest mismatch for {name}")
        if name in receipt_hashes:
            raise ValueError(f"release receipt contains a duplicate asset: {name}")
        receipt_hashes[name] = digest
    missing = required_files - receipt_hashes.keys()
    if missing:
        raise ValueError(f"release receipt is missing hash bindings: {sorted(missing)}")
    unexpected = receipt_hashes.keys() - required_files
    if unexpected:
        raise ValueError(f"release receipt has unexpected asset bindings: {sorted(unexpected)}")

    provenance = _verify_release_provenance(
        receipt,
        tag=tag,
        commit=commit,
        expected_tag_object=expected_tag_object,
        expected_tag_tree=expected_tag_tree,
        expected_release_control_revision=expected_release_control_revision,
        expected_workflow_revision=expected_workflow_revision,
        expected_workflow_run_id=expected_workflow_run_id,
        expected_workflow_attempt=expected_workflow_attempt,
        expected_workflow_event=expected_workflow_event,
        expected_workflow_ref=expected_workflow_ref,
        expected_workflow_ref_protected=expected_workflow_ref_protected,
        expected_repository=expected_repository,
        require=require_release_provenance,
    )
    return receipt.get("attestation_subjects", []), provenance


def verify_public_release_bindings(
    *,
    tag: str,
    manifest_path: Path,
    checksums_path: Path,
    asset_dir: Path,
    receipt_path: Path,
    expected_tag_target: str,
    expected_tag_object: str | None = None,
    expected_tag_tree: str | None = None,
    expected_release_control_revision: str | None = None,
    expected_workflow_revision: str | None = None,
    expected_workflow_run_id: str | None = None,
    expected_workflow_attempt: str | None = None,
    expected_workflow_event: str | None = None,
    expected_workflow_ref: str | None = None,
    expected_workflow_ref_protected: str | None = None,
    expected_repository: str | None = None,
    expected_attestation_ids: list[str] | None = None,
    require_release_provenance: bool = False,
) -> dict[str, Any]:
    """Fail closed unless all public release identities bind to the same bytes."""
    version = _tag_version(tag)
    if (
        not isinstance(expected_tag_target, str)
        or re.fullmatch(r"[0-9a-f]{40}", expected_tag_target) is None
    ):
        raise ValueError("expected tag target must be a 40-character lowercase Git SHA")
    if asset_dir.is_symlink() or not asset_dir.is_dir():
        raise ValueError(f"public asset directory is missing or symlinked: {asset_dir}")
    asset_root = asset_dir.resolve()
    manifest_file = manifest_path.expanduser().absolute()
    checksums_file = checksums_path.expanduser().absolute()
    if (
        manifest_file.parent.resolve() != asset_root
        or checksums_file.parent.resolve() != asset_root
    ):
        raise ValueError("manifest and SHA256SUMS must be files in the public asset directory")

    checksums = _parse_checksums(checksums_file)
    public_files = {
        path.name
        for path in asset_root.iterdir()
        if path.is_file()
        and not path.is_symlink()
        and path.name not in {checksums_file.name, receipt_path.name}
    }
    if set(checksums) != public_files:
        missing = sorted(public_files - set(checksums))
        unexpected = sorted(set(checksums) - public_files)
        raise ValueError(
            f"public asset set differs from SHA256SUMS: missing={missing}, unexpected={unexpected}"
        )
    for name, expected in checksums.items():
        actual = _sha256(_safe_asset_path(asset_root, name))
        if actual != expected:
            raise ValueError(f"public asset does not match SHA256SUMS: {name}")

    manifest = _load_json(manifest_file, "release manifest")
    if manifest.get("schema") != "power.release.manifest.v1":
        raise ValueError("published release manifest schema is invalid")
    if manifest.get("version") != version:
        raise ValueError("published release manifest version does not match tag")
    _validate_manifest_semantics(manifest, version)
    commit = manifest.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("published release manifest commit is invalid")
    if commit != expected_tag_target:
        raise ValueError("published release manifest commit does not match expected tag target")
    manifest_hash = _sha256(manifest_file)
    file_hashes, image_digest = _manifest_file_artifacts(manifest, asset_root, checksums, version)
    if checksums.get(manifest_file.name) != manifest_hash:
        raise ValueError("published release manifest does not match SHA256SUMS")

    profile_name = manifest["artifacts"]["profile_evidence"]["filename"]
    profile = _load_json(_safe_asset_path(asset_root, profile_name), "Profile A/B evidence")
    if profile.get("schema") != "power.profile.acceptance.v1":
        raise ValueError("Profile A/B evidence schema is invalid")
    if profile.get("version") != version:
        raise ValueError("Profile A/B evidence version does not match tag")
    if profile.get("acceptance_harness_revision") != commit:
        raise ValueError("Profile A/B evidence harness revision does not match tag commit")
    if profile.get("image_digest") != image_digest:
        raise ValueError("Profile B image digest does not match manifest image digest")
    profile_a = profile.get("profile_a")
    if not isinstance(profile_a, dict):
        raise ValueError("Profile A evidence is missing")
    for field in ("native_cli", "native_mcp_stdio"):
        if profile_a.get(field) is not True:
            raise ValueError(f"Profile A evidence {field} must be true")
    if profile_a.get("docker_web_containers") != 0:
        raise ValueError("Profile A evidence must contain zero Web containers")
    profile_b = profile.get("profile_b")
    if not isinstance(profile_b, dict):
        raise ValueError("Profile B evidence is missing")
    for field in (
        "web_health",
        "web_authenticated_read",
        "web_semantic_non_fallback",
        "web_reranked_non_fallback",
        "web_governed_mutation",
        "host_cli_readback",
        "host_mcp_readback",
        "same_canonical_vault",
        "cache_delete_rebuild",
        "cap_drop_all",
        "read_only_rootfs",
    ):
        if profile_b.get(field) is not True:
            raise ValueError(f"Profile B evidence {field} must be true")
    if profile_b.get("container_user") != "10001:10001":
        raise ValueError("Profile B evidence container user is invalid")
    if profile_b.get("web_mcp_services") != 0:
        raise ValueError("Profile B evidence must contain zero MCP services")
    if profile_b.get("web_applicationservice_bypass_count") != 0:
        raise ValueError("Profile B evidence reports an ApplicationService bypass")
    profile_image = profile.get("image")
    if not isinstance(profile_image, str) or not profile_image.endswith(f"@{image_digest}"):
        raise ValueError("Profile B evidence must bind an image reference to a digest")

    receipt_file = receipt_path.expanduser().absolute()
    if receipt_file.parent.resolve() != asset_root:
        raise ValueError("release receipt must be inside the public asset directory")
    receipt = _load_json(receipt_file, "release receipt")
    required_receipt_files = set(checksums)
    _, release_provenance = _verify_receipt(
        receipt,
        tag=tag,
        commit=commit,
        manifest_path=manifest_file,
        manifest_hash=manifest_hash,
        asset_dir=asset_root,
        required_files=required_receipt_files,
        expected_tag_object=expected_tag_object,
        expected_tag_tree=expected_tag_tree,
        expected_release_control_revision=expected_release_control_revision,
        expected_workflow_revision=expected_workflow_revision,
        expected_workflow_run_id=expected_workflow_run_id,
        expected_workflow_attempt=expected_workflow_attempt,
        expected_workflow_event=expected_workflow_event,
        expected_workflow_ref=expected_workflow_ref,
        expected_workflow_ref_protected=expected_workflow_ref_protected,
        expected_repository=expected_repository,
        require_release_provenance=require_release_provenance,
    )
    if release_provenance is not None:
        manifest_repository = required_repository(
            manifest.get("repository"), "release manifest repository"
        )
        if manifest_repository != release_provenance["repository"]:
            raise ValueError("release manifest repository does not match release provenance")

    manifest_attestations = manifest.get("attestations")
    receipt_attestations = receipt.get("attestations")
    if not isinstance(manifest_attestations, list) or not manifest_attestations:
        raise ValueError("published release manifest attestations must be a non-empty list")
    if not isinstance(receipt_attestations, list) or not receipt_attestations:
        raise ValueError("release receipt attestations must be a non-empty list")
    try:
        manifest_ids = {normalize_attestation_id(value) for value in manifest_attestations}
        receipt_ids = {normalize_attestation_id(value) for value in receipt_attestations}
    except ValueError as exc:
        raise ValueError(f"invalid attestation identity: {exc}") from exc
    if manifest_ids != receipt_ids:
        raise ValueError("release manifest and receipt attestation identities differ")

    subjects = receipt.get("attestation_subjects")
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("release receipt attestation subjects are missing")
    subject_ids: set[str] = set()
    observed_subjects: set[str] = set()
    subject_roles: dict[str, set[str]] = {}
    expected_subjects = {
        file_hashes[manifest["artifacts"]["power_wheel"]["filename"]],
        file_hashes[manifest["artifacts"]["power_sdist"]["filename"]],
        file_hashes[manifest["artifacts"]["native_dependency_lock"]["filename"]],
        image_digest,
    }
    for item in subjects:
        if not isinstance(item, dict):
            raise ValueError("attestation subject entry must be an object")
        try:
            subject_id = normalize_attestation_id(item.get("id"))
        except ValueError as exc:
            raise ValueError(f"invalid attestation subject identity: {exc}") from exc
        if subject_id in subject_ids:
            raise ValueError(f"duplicate attestation subject identity: {subject_id}")
        subject_ids.add(subject_id)
        role = item.get("role")
        if role not in {"package", "web"}:
            raise ValueError(f"attestation role is invalid for {subject_id}")
        subject_roles.setdefault(role, set()).add(subject_id)
        values = item.get("subjects")
        if not isinstance(values, list) or not values:
            raise ValueError(f"attestation subjects are missing for {subject_id}")
        for number, value in enumerate(values):
            subject = _canonical_subject(value, f"attestation {subject_id} subject {number}")
            if subject not in expected_subjects:
                raise ValueError(f"attestation subject does not match a final digest: {subject}")
            observed_subjects.add(subject)
    if subject_ids != manifest_ids:
        raise ValueError("attestation subject identities differ from manifest attestations")
    if expected_attestation_ids is not None:
        try:
            expected_ids = {normalize_attestation_id(value) for value in expected_attestation_ids}
        except ValueError as exc:
            raise ValueError(f"invalid expected attestation identity: {exc}") from exc
        if expected_ids != manifest_ids:
            raise ValueError("release attestation identities do not match workflow outputs")
    if observed_subjects != expected_subjects:
        raise ValueError(
            "attestation subjects do not cover every final wheel, sdist, and image digest"
        )
    if set(subject_roles) != {"package", "web"} or any(
        len(identities) != 1 for identities in subject_roles.values()
    ):
        raise ValueError("attestation roles must map one package ID and one web ID")
    subjects_by_role = {
        role: {subject for item in subjects if item["role"] == role for subject in item["subjects"]}
        for role in {"package", "web"}
    }
    wheel_filename = manifest["artifacts"]["power_wheel"]["filename"]
    sdist_filename = manifest["artifacts"]["power_sdist"]["filename"]
    dependency_lock_filename = manifest["artifacts"]["native_dependency_lock"]["filename"]
    if subjects_by_role["package"] != {
        file_hashes[wheel_filename],
        file_hashes[sdist_filename],
        file_hashes[dependency_lock_filename],
    }:
        raise ValueError(
            "package attestation subjects do not match wheel, sdist, and dependency lock"
        )
    if subjects_by_role["web"] != {image_digest}:
        raise ValueError("web attestation subject does not match image digest")

    return {
        "status": "verified",
        "tag": tag,
        "version": version,
        "commit": commit,
        "manifest_sha256": manifest_hash,
        "file_sha256": dict(sorted(file_hashes.items())),
        "web_image_digest": image_digest,
        "attestation_count": len(subject_ids),
        "release_provenance_status": "verified"
        if release_provenance is not None
        else "not_present_legacy_release",
        "release_provenance": release_provenance,
    }


def main(argv: list[str] | None = None) -> int:
    """Verify a downloaded public release and print a content-free receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-tag-target", required=True)
    parser.add_argument("--expected-tag-object")
    parser.add_argument("--expected-tag-tree")
    parser.add_argument("--expected-release-control-revision")
    parser.add_argument("--expected-workflow-revision")
    parser.add_argument("--expected-workflow-run-id")
    parser.add_argument("--expected-workflow-attempt")
    parser.add_argument("--expected-workflow-event")
    parser.add_argument("--expected-workflow-ref")
    parser.add_argument("--expected-workflow-ref-protected")
    parser.add_argument("--expected-repository")
    parser.add_argument("--expected-attestation-id", action="append")
    parser.add_argument("--require-release-provenance", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify_public_release_bindings(
            tag=args.tag,
            manifest_path=args.manifest,
            checksums_path=args.checksums,
            asset_dir=args.asset_dir,
            receipt_path=args.receipt,
            expected_tag_target=args.expected_tag_target,
            expected_tag_object=args.expected_tag_object,
            expected_tag_tree=args.expected_tag_tree,
            expected_release_control_revision=args.expected_release_control_revision,
            expected_workflow_revision=args.expected_workflow_revision,
            expected_workflow_run_id=args.expected_workflow_run_id,
            expected_workflow_attempt=args.expected_workflow_attempt,
            expected_workflow_event=args.expected_workflow_event,
            expected_workflow_ref=args.expected_workflow_ref,
            expected_workflow_ref_protected=args.expected_workflow_ref_protected,
            expected_repository=args.expected_repository,
            expected_attestation_ids=args.expected_attestation_id,
            require_release_provenance=args.require_release_provenance,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
