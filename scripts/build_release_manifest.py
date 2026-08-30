#!/usr/bin/env python3
"""Build the exact unified POWER release manifest from verified artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

try:
    from release_bindings import normalize_attestation_id
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.release_bindings import normalize_attestation_id


def aggregate_tree_hash(files: dict[str, bytes]) -> str:
    """Hash relative paths and file bytes in deterministic lexical order."""
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[relative]).digest())
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_metadata(path: Path) -> dict[str, str]:
    """Read the identity fields required for release binding."""
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("wheel must contain exactly one dist-info METADATA file")
        fields: dict[str, str] = {}
        for line in archive.read(names[0]).decode("utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in {"Name", "Version", "Requires-Python"}:
                fields[key] = value.strip()
        return fields


def wheel_tree(path: Path, prefix: str) -> dict[str, bytes]:
    """Read one package-data subtree from a wheel."""
    with zipfile.ZipFile(path) as archive:
        return {
            name[len(prefix) :]: archive.read(name)
            for name in archive.namelist()
            if name.startswith(prefix)
            and not name.endswith("/")
            and "__pycache__" not in name
            and not name.endswith(".pyc")
        }


def source_tree(root: Path) -> dict[str, bytes]:
    """Read the source Skill tree for a source/artifact consistency check."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if (
            path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    }


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically and keep the destination owner-readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_manifest(
    *,
    repo_root: Path,
    wheel: Path,
    sdist: Path | None,
    version: str,
    commit: str,
    web_image: str | None,
    web_image_digest: str | None,
    package_sbom: Path | None,
    web_sbom: Path | None,
    profile_evidence: Path | None,
    attestations: list[str],
) -> dict[str, Any]:
    """Build a release manifest bound to commit, package, SBOM, and Web identities."""
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("commit must be a 40-character lowercase Git commit SHA")
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("wheel must be an existing .whl file")
    if sdist is None:
        inferred_sdist = wheel.with_name(f"power_framework-{version}.tar.gz")
        sdist = inferred_sdist if inferred_sdist.is_file() else None
    if sdist is not None and (not sdist.is_file() or sdist.suffixes[-2:] != [".tar", ".gz"]):
        raise ValueError("sdist must be an existing .tar.gz file")
    metadata = wheel_metadata(wheel)
    if metadata.get("Name") != "power-framework":
        raise ValueError("wheel distribution must be power-framework")
    if metadata.get("Version") != version:
        raise ValueError("wheel version does not match --version")
    requires_python = metadata.get("Requires-Python")
    if not requires_python:
        raise ValueError("wheel Requires-Python metadata is required")

    skill_files = wheel_tree(wheel, "power_framework/data/skills/power/")
    if "SKILL.md" not in skill_files:
        raise ValueError("wheel does not contain the packaged POWER Skill")
    source_skill = source_tree(repo_root / "skills" / "power")
    if source_skill != skill_files:
        raise ValueError("wheel Skill tree differs from the checked-out source Skill tree")

    mcp_files = wheel_tree(wheel, "power_framework/mcp/")
    if not mcp_files:
        raise ValueError("wheel does not contain the MCP contract")
    if (web_image is None) != (web_image_digest is None):
        raise ValueError("--web-image and --web-image-digest must be supplied together")
    if (
        web_image_digest is not None
        and re.fullmatch(r"sha256:[0-9a-f]{64}", web_image_digest) is None
    ):
        raise ValueError("Web image digest must use sha256:<64 lowercase hex characters>")
    if web_image is not None and (
        package_sbom is None or web_sbom is None or profile_evidence is None
    ):
        raise ValueError("final Web manifests require package, Web SBOM, and Profile A/B evidence")
    if package_sbom is not None and not package_sbom.is_file():
        raise ValueError("package SBOM must be an existing file")
    if web_sbom is not None and not web_sbom.is_file():
        raise ValueError("Web SBOM must be an existing file")
    if profile_evidence is not None and not profile_evidence.is_file():
        raise ValueError("Profile A/B evidence must be an existing file")
    try:
        normalized_attestations = [normalize_attestation_id(item) for item in attestations]
    except ValueError as exc:
        raise ValueError(f"invalid attestation identity: {exc}") from exc
    if len(set(normalized_attestations)) != len(normalized_attestations):
        raise ValueError("attestation identities must be unique")

    manifest: dict[str, Any] = {
        "schema": "power.release.manifest.v1",
        "repository": "weby-homelab/power-framework",
        "version": version,
        "commit": commit,
        "requires_python": requires_python,
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
        "artifacts": {
            "power_wheel": {
                "filename": wheel.name,
                "sha256": sha256_file(wheel),
            },
        },
        "attestations": sorted(normalized_attestations),
    }
    if sdist is not None:
        manifest["artifacts"]["power_sdist"] = {
            "filename": sdist.name,
            "sha256": sha256_file(sdist),
        }
    if package_sbom is not None:
        manifest["artifacts"]["package_sbom"] = {
            "filename": package_sbom.name,
            "sha256": sha256_file(package_sbom),
        }
    if profile_evidence is not None:
        manifest["artifacts"]["profile_evidence"] = {
            "filename": profile_evidence.name,
            "sha256": sha256_file(profile_evidence),
        }
    if web_image is not None and web_image_digest is not None:
        manifest["artifacts"]["web_image"] = {
            "reference": web_image,
            "digest": web_image_digest,
        }
        if web_sbom is not None:
            manifest["artifacts"]["web_sbom"] = {
                "filename": web_sbom.name,
                "sha256": sha256_file(web_sbom),
            }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--web-image")
    parser.add_argument("--web-image-digest")
    parser.add_argument("--package-sbom", type=Path)
    parser.add_argument("--web-sbom", type=Path)
    parser.add_argument("--profile-evidence", type=Path)
    parser.add_argument("--attestation", action="append", default=[])
    args = parser.parse_args()
    payload = build_manifest(
        repo_root=args.repo_root.resolve(),
        wheel=args.wheel.expanduser().resolve(),
        sdist=args.sdist.expanduser().resolve() if args.sdist else None,
        version=args.version,
        commit=args.commit,
        web_image=args.web_image,
        web_image_digest=args.web_image_digest,
        package_sbom=args.package_sbom.expanduser().resolve() if args.package_sbom else None,
        web_sbom=args.web_sbom.expanduser().resolve() if args.web_sbom else None,
        profile_evidence=(
            args.profile_evidence.expanduser().resolve() if args.profile_evidence else None
        ),
        attestations=args.attestation,
    )
    atomic_json_write(args.output.expanduser().resolve(), payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
