#!/usr/bin/env python3
"""Create a provenance receipt for a tagged POWER release and its artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from release_bindings import normalize_attestation_id
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.release_bindings import normalize_attestation_id

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")
RELEASE_EVENTS = frozenset({"push", "workflow_dispatch"})


def _git(repo: Path, *args: str) -> str:
    """Return one successful read-only Git query."""
    result = subprocess.run(  # noqa: S603 -- fixed executable and read-only release queries.
        ["git", "-C", str(repo), *args],  # noqa: S607 -- fixed executable name.
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    """Hash one release asset in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(value: Any, label: str) -> str:
    """Require one non-empty textual provenance field."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _required_git_object(value: Any, label: str) -> str:
    """Require one lowercase 40-character Git object ID."""
    text = _required_text(value, label)
    if GIT_OBJECT_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a 40-character lowercase Git SHA")
    return text


def _required_positive_integer(value: Any, label: str) -> str:
    """Require one positive decimal identifier represented as text."""
    text = _required_text(value, label)
    if POSITIVE_INTEGER_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a positive decimal integer")
    return text


def _required_repository(value: Any, label: str) -> str:
    """Require one safe GitHub owner/name repository identity."""
    text = _required_text(value, label)
    if REPOSITORY_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must use owner/name syntax")
    return text


def _context_value(primary: str, fallback: Any, label: str) -> str:
    """Read an explicit release context field without accepting an empty override."""
    value = os.environ.get(primary, fallback)
    return _required_text(value, label)


def _build_release_provenance(
    *,
    repo: Path,
    tag: str,
    commit: str,
    tree: str,
    repository: str,
    workflow_run_id: str,
) -> dict[str, str]:
    """Build and validate the source/control-plane identity for one release."""
    if TAG_RE.fullmatch(tag) is None:
        raise ValueError("release source tag must be a stable v<major>.<minor>.<patch> tag")
    repository = _required_repository(repository, "release repository")
    workflow_repository = _required_repository(
        _context_value(
            "RELEASE_WORKFLOW_REPOSITORY",
            os.environ.get("GITHUB_REPOSITORY"),
            "workflow repository",
        ),
        "workflow repository",
    )
    if workflow_repository != repository:
        raise ValueError("workflow repository does not match release repository")

    source_commit = _required_git_object(commit, "release source commit")
    source_tree = _required_git_object(tree, "release source tree")
    tag_object = _required_git_object(
        _git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{tag}}"),
        "release tag object",
    )
    control_revision = _required_git_object(
        _context_value(
            "RELEASE_CONTROL_REVISION",
            os.environ.get("GITHUB_SHA"),
            "release control revision",
        ),
        "release control revision",
    )
    workflow_revision = _required_git_object(
        _context_value(
            "RELEASE_WORKFLOW_REVISION",
            os.environ.get("GITHUB_SHA"),
            "workflow revision",
        ),
        "workflow revision",
    )
    if control_revision != workflow_revision:
        raise ValueError("release control revision does not match workflow revision")

    argument_run_id = _required_positive_integer(workflow_run_id, "workflow run ID argument")
    release_workflow_run_id = _required_positive_integer(
        _context_value("RELEASE_WORKFLOW_RUN_ID", workflow_run_id, "workflow run ID"),
        "workflow run ID",
    )
    if release_workflow_run_id != argument_run_id:
        raise ValueError("workflow run ID does not match the generator argument")
    workflow_attempt = _required_positive_integer(
        _context_value(
            "RELEASE_WORKFLOW_ATTEMPT",
            os.environ.get("GITHUB_RUN_ATTEMPT"),
            "workflow run attempt",
        ),
        "workflow run attempt",
    )
    workflow_event = _context_value(
        "RELEASE_WORKFLOW_EVENT",
        os.environ.get("GITHUB_EVENT_NAME"),
        "workflow event",
    )
    if workflow_event not in RELEASE_EVENTS:
        raise ValueError(f"workflow event is not a supported release event: {workflow_event}")
    workflow_ref = _required_text(
        _context_value("RELEASE_WORKFLOW_REF", os.environ.get("GITHUB_REF"), "workflow ref"),
        "workflow ref",
    )
    expected_ref = (
        "refs/heads/main" if workflow_event == "workflow_dispatch" else f"refs/tags/{tag}"
    )
    if workflow_ref != expected_ref:
        raise ValueError(f"workflow ref does not match release event: expected {expected_ref}")
    workflow_ref_protected = _context_value(
        "RELEASE_WORKFLOW_REF_PROTECTED",
        os.environ.get("GITHUB_REF_PROTECTED"),
        "workflow ref protection state",
    )
    if workflow_ref_protected not in {"true", "false"}:
        raise ValueError("workflow ref protection state must be true or false")
    if workflow_event == "workflow_dispatch" and workflow_ref_protected != "true":
        raise ValueError("workflow_dispatch release control ref must be protected")

    return {
        "release_source_tag": tag,
        "release_source_commit": source_commit,
        "release_source_tree": source_tree,
        "release_tag_object": tag_object,
        "release_control_revision": control_revision,
        "workflow_revision": workflow_revision,
        "workflow_run_id": release_workflow_run_id,
        "workflow_run_attempt": workflow_attempt,
        "workflow_event": workflow_event,
        "workflow_ref": workflow_ref,
        "workflow_ref_protected": workflow_ref_protected,
        "repository": repository,
    }


def _asset_receipt(path: Path) -> dict[str, Any]:
    """Return stable, path-safe metadata for one uploaded asset."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"release asset must be a regular file: {path}")
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _parse_attestation_roles(values: list[str]) -> dict[str, str]:
    """Parse ``attestation-id=package|web`` role bindings."""
    roles: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str) or "=" not in value:
            raise ValueError("attestation role must use id=package|web syntax")
        raw_id, role = value.split("=", 1)
        try:
            identity = normalize_attestation_id(raw_id)
        except ValueError as exc:
            raise ValueError(f"invalid attestation role identity: {exc}") from exc
        role = role.strip()
        if role not in {"package", "web"}:
            raise ValueError("attestation role must be package or web")
        if identity in roles:
            raise ValueError(f"duplicate attestation role identity: {identity}")
        roles[identity] = role
    return roles


def _parse_attestation_subjects(values: list[str], roles: dict[str, str]) -> list[dict[str, Any]]:
    """Parse ``attestation-id=digest`` values into deterministic receipt entries."""
    subjects: dict[str, set[str]] = {}
    for value in values:
        if not isinstance(value, str) or "=" not in value:
            raise ValueError("attestation subject must use id=digest syntax")
        raw_id, raw_digest = value.split("=", 1)
        try:
            identity = normalize_attestation_id(raw_id)
        except ValueError as exc:
            raise ValueError(f"invalid attestation subject identity: {exc}") from exc
        digest = raw_digest.strip()
        if digest.startswith("sha256:"):
            if IMAGE_DIGEST_RE.fullmatch(digest) is None:
                raise ValueError("attestation image subject must use sha256:<64 lowercase hex>")
        elif HASH_RE.fullmatch(digest) is None:
            raise ValueError("attestation package subject must be a lowercase SHA-256")
        subjects.setdefault(identity, set()).add(digest)
    return [
        {"id": identity, "role": roles.get(identity), "subjects": sorted(digests)}
        for identity, digests in sorted(subjects.items())
    ]


def build_receipt(
    *,
    repo: Path,
    tag: str,
    assets_dir: Path,
    repository: str,
    workflow_run_id: str,
    manifest_path: Path | None = None,
    attestation_ids: list[str] | None = None,
    attestation_subjects: list[str] | None = None,
    attestation_subject_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Build a receipt tied to the exact tag commit, tree and local artifacts."""
    try:
        normalized_attestation_ids = [
            normalize_attestation_id(value) for value in (attestation_ids or [])
        ]
    except ValueError as exc:
        raise ValueError(f"invalid attestation identity: {exc}") from exc
    if len(set(normalized_attestation_ids)) != len(normalized_attestation_ids):
        raise ValueError("attestation IDs must be unique")
    parsed_roles = _parse_attestation_roles(attestation_subject_roles or [])
    parsed_subjects = _parse_attestation_subjects(attestation_subjects or [], parsed_roles)
    commit = _git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    tree = _git(repo, "show", "-s", "--format=%T", commit)
    assets = sorted(
        path
        for path in assets_dir.iterdir()
        if path.is_file()
        and not path.is_symlink()
        and path.name != "power-framework.release-receipt.json"
        and path.suffix in {".whl", ".gz", ".json", ".txt"}
    )
    if not assets:
        raise ValueError(f"no release assets found in {assets_dir}")

    manifest_file = manifest_path or assets_dir / "power-release-manifest.json"
    if not manifest_file.is_file():
        raise ValueError(f"unified release manifest is missing: {manifest_file}")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("unified release manifest is not valid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != "power.release.manifest.v1":
        raise ValueError("unified release manifest schema is invalid")
    if manifest.get("commit") != commit:
        raise ValueError("unified release manifest commit does not match the tag commit")
    repository = _required_repository(repository, "release repository")
    manifest_repository = _required_repository(
        manifest.get("repository"), "release manifest repository"
    )
    if manifest_repository != repository:
        raise ValueError("release manifest repository does not match release repository")
    release_provenance = _build_release_provenance(
        repo=repo,
        tag=tag,
        commit=commit,
        tree=tree,
        repository=repository,
        workflow_run_id=workflow_run_id,
    )
    manifest_attestation_values = manifest.get("attestations", [])
    if not isinstance(manifest_attestation_values, list):
        raise ValueError("unified release manifest attestations must be a list")
    try:
        manifest_attestation_ids = {
            normalize_attestation_id(value) for value in manifest_attestation_values
        }
    except ValueError as exc:
        raise ValueError(f"invalid manifest attestation identity: {exc}") from exc
    if manifest_attestation_ids != set(normalized_attestation_ids):
        raise ValueError("receipt attestation IDs do not match the release manifest")
    if normalized_attestation_ids:
        subject_ids = {item["id"] for item in parsed_subjects}
        if subject_ids != manifest_attestation_ids:
            raise ValueError("receipt attestation subjects do not match attestation IDs")
        if set(parsed_roles) != manifest_attestation_ids or set(parsed_roles.values()) != {
            "package",
            "web",
        }:
            raise ValueError("receipt attestation roles must map one package ID and one web ID")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError(
                "unified release manifest artifacts are required for attestation subjects"
            )
        expected_subjects: set[str] = set()
        for key in ("power_wheel", "power_sdist"):
            entry = artifacts.get(key)
            if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
                raise ValueError(f"manifest artifact {key} is required for attestation subjects")
            expected_subjects.add(entry["sha256"])
        image_entry = artifacts.get("web_image")
        if not isinstance(image_entry, dict) or not isinstance(image_entry.get("digest"), str):
            raise ValueError("manifest web_image is required for attestation subjects")
        expected_subjects.add(image_entry["digest"])
        observed_subjects = {subject for item in parsed_subjects for subject in item["subjects"]}
        if observed_subjects != expected_subjects:
            raise ValueError("attestation subjects do not match final manifest digests")
        subjects_by_role = {
            role: {
                subject
                for item in parsed_subjects
                if item["role"] == role
                for subject in item["subjects"]
            }
            for role in {"package", "web"}
        }
        if subjects_by_role["package"] != {
            artifacts["power_wheel"]["sha256"],
            artifacts["power_sdist"]["sha256"],
        }:
            raise ValueError("package attestation subjects do not match wheel and sdist")
        if subjects_by_role["web"] != {image_entry["digest"]}:
            raise ValueError("web attestation subject does not match the image digest")

    return {
        "schema_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "release": {
            "repository": repository,
            "tag": tag,
            "commit": commit,
            "tree": tree,
        },
        "release_provenance": {
            **release_provenance,
        },
        "workflow_run": {
            "id": release_provenance["workflow_run_id"],
            "name": os.environ.get("GITHUB_WORKFLOW"),
            "attempt": release_provenance["workflow_run_attempt"],
            "event": release_provenance["workflow_event"],
            "ref": release_provenance["workflow_ref"],
            "repository": release_provenance["repository"],
            "url": f"https://github.com/{repository}/actions/runs/{release_provenance['workflow_run_id']}",
        },
        "attestations": sorted(normalized_attestation_ids),
        "attestation_subjects": parsed_subjects,
        "unified_release_manifest": {
            "name": manifest_file.name,
            "sha256": _sha256(manifest_file),
            "version": manifest.get("version"),
            "commit": manifest.get("commit"),
            "web_image": manifest.get("artifacts", {}).get("web_image"),
        },
        "assets": [_asset_receipt(path) for path in assets],
    }


def main() -> int:
    """Parse release context and write one content-free JSON receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-repo", type=Path, default=Path.cwd())
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--release-manifest", type=Path, default=None)
    parser.add_argument("--attestation-id", action="append", default=[])
    parser.add_argument("--attestation-subject", action="append", default=[])
    parser.add_argument("--attestation-subject-role", action="append", default=[])
    args = parser.parse_args()

    receipt = build_receipt(
        repo=args.git_repo.resolve(),
        tag=args.tag,
        assets_dir=args.assets_dir.resolve(),
        repository=args.repository,
        workflow_run_id=args.workflow_run_id,
        manifest_path=args.release_manifest.resolve() if args.release_manifest else None,
        attestation_ids=args.attestation_id,
        attestation_subjects=args.attestation_subject,
        attestation_subject_roles=args.attestation_subject_role,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Release receipt written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
