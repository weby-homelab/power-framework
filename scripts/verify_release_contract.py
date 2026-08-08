#!/usr/bin/env python3
"""Validate the immutable, machine-readable release baseline for POWER.

The baseline is intentionally source-scoped rather than a performance claim.
It records the exact released tree, the checked model lock, frozen benchmark
dataset hashes, and the known validation boundary.  This prevents release
documentation and supply-chain metadata from silently drifting apart.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PYPROJECT = REPO_ROOT / "pyproject.toml"
DEFAULT_MODELS_LOCK = REPO_ROOT / "release" / "models.lock.json"
DEFAULT_BASELINE = REPO_ROOT / "release" / "evidence" / "baselines" / "v3.3.2.json"
DEFAULT_DATASET_MANIFEST = (
    REPO_ROOT / "benchmarks" / "power31" / "dataset" / "v1" / "corpus-manifest.json"
)
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
GIT_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
DATASET_HASH_FIELDS = {
    "corpus_sha256": ("corpus", "hash_sha256"),
    "queries_sha256": ("queries", "hash_sha256"),
    "qrels_sha256": ("qrels", "hash_sha256"),
    "expected_answers_sha256": ("expected_answers", "hash_sha256"),
}


def _load_json(path: Path) -> dict[str, Any]:
    """Return a JSON object or raise one actionable error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_package_version(path: Path) -> str:
    """Read ``[project].version`` without importing the package or a TOML dependency."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read project version from {path}: {exc}") from exc

    project_section = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", content)
    version_match = (
        re.search(r'(?m)^version\s*=\s*"([^"\n]+)"\s*$', project_section.group(1))
        if project_section is not None
        else None
    )
    if version_match is None:
        raise ValueError(f"project.version in {path} must be a non-empty string")
    return version_match.group(1)


def _sha256(path: Path) -> str:
    """Return a checkout-stable checksum for the tracked JSON input.

    Git stores this release metadata with LF line endings. Windows checkouts
    can materialize the same JSON with CRLF, so hash the canonical text form
    while retaining byte-exact hashing for every non-CRLF byte.
    """
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _git(repo: Path, *args: str) -> tuple[int, str, str]:
    """Run a read-only Git query and return its status, stdout and stderr."""
    result = subprocess.run(  # noqa: S603 -- fixed executable and repository-local read-only query.
        ["git", "-C", str(repo), *args],  # noqa: S607 -- fixed executable name.
        capture_output=True,
        check=False,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _validate_git_source(
    source: dict[str, Any],
    *,
    release: str,
    git_repo: Path,
    require_tag: bool,
    errors: list[str],
) -> None:
    """Prove that the baseline names the released Git objects and ref."""
    commit = source.get("commit")
    tree = source.get("tree")
    if not isinstance(commit, str) or not GIT_OBJECT_RE.fullmatch(commit):
        return
    if not isinstance(tree, str) or not GIT_OBJECT_RE.fullmatch(tree):
        return

    status, _, stderr = _git(git_repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if status != 0:
        errors.append(
            f"baseline source.commit does not resolve to a Git commit: {commit} ({stderr})"
        )
        return

    status, _, stderr = _git(git_repo, "cat-file", "-e", f"{tree}^{{tree}}")
    if status != 0:
        errors.append(f"baseline source.tree does not resolve to a Git tree: {tree} ({stderr})")
        return

    status, actual_tree, stderr = _git(git_repo, "show", "-s", "--format=%T", commit)
    if status != 0:
        errors.append(f"cannot read commit tree for {commit}: {stderr}")
    elif actual_tree != tree:
        errors.append(
            "baseline source.tree does not match the named commit: "
            f"expected {tree}, actual {actual_tree}"
        )

    tag = source.get("tag", f"v{release}")
    if not isinstance(tag, str) or not GIT_TAG_RE.fullmatch(tag):
        errors.append(f"baseline source.tag must be a release tag like v{release!s}")
        return
    status, tag_commit, stderr = _git(
        git_repo,
        "rev-parse",
        "--verify",
        f"refs/tags/{tag}^{{commit}}",
    )
    if status != 0 and require_tag:
        errors.append(f"baseline source.tag does not resolve to a commit: {tag} ({stderr})")
    elif status == 0 and tag_commit != commit:
        errors.append(
            f"baseline source.tag {tag} does not point to source.commit: "
            f"expected {commit}, actual {tag_commit}"
        )


def validate_release_contract(
    *,
    pyproject_path: Path,
    models_lock_path: Path,
    baseline_path: Path,
    dataset_manifest_path: Path,
    git_repo: Path,
    require_tag: bool = False,
) -> list[str]:
    """Return every release-contract violation without stopping at the first."""
    package_version = _load_package_version(pyproject_path)
    models_lock = _load_json(models_lock_path)
    baseline = _load_json(baseline_path)
    dataset_manifest = _load_json(dataset_manifest_path)
    errors: list[str] = []

    lock_version = models_lock.get("release")
    if lock_version != package_version:
        errors.append(
            f"models.lock release {lock_version!r} does not match project version {package_version!r}"
        )

    if baseline.get("schema_version") != 1:
        errors.append("baseline schema_version must be 1")
    if baseline.get("release") != package_version:
        errors.append(
            f"baseline release {baseline.get('release')!r} does not match project version {package_version!r}"
        )

    source = baseline.get("source")
    if not isinstance(source, dict):
        errors.append("baseline source must be an object")
    else:
        for field in ("commit", "tree"):
            value = source.get(field)
            if not isinstance(value, str) or not GIT_OBJECT_RE.fullmatch(value):
                errors.append(
                    f"baseline source.{field} must be a 40-character lowercase Git object id"
                )
        if source.get("clean") is not True:
            errors.append(
                "baseline source.clean must be true; dirty source cannot be a release baseline"
            )
        _validate_git_source(
            source,
            release=package_version,
            git_repo=git_repo,
            require_tag=require_tag,
            errors=errors,
        )

    expected_lock_hash = baseline.get("models_lock_sha256")
    actual_lock_hash = _sha256(models_lock_path)
    if expected_lock_hash != actual_lock_hash:
        errors.append(
            "baseline models_lock_sha256 does not match release/models.lock.json "
            f"(expected {expected_lock_hash!r}, actual {actual_lock_hash!r})"
        )

    benchmark = baseline.get("benchmark")
    if not isinstance(benchmark, dict):
        errors.append("baseline benchmark must be an object")
    else:
        if benchmark.get("synthetic") is not True:
            errors.append(
                "baseline benchmark.synthetic must be true for the POWER 3.1 frozen dataset"
            )
        for baseline_field, manifest_path in DATASET_HASH_FIELDS.items():
            current: Any = dataset_manifest
            for key in manifest_path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            if benchmark.get(baseline_field) != current:
                errors.append(
                    f"baseline benchmark.{baseline_field} does not match dataset manifest value {current!r}"
                )

    validation = baseline.get("validation")
    if not isinstance(validation, dict):
        errors.append("baseline validation must be an object")
    else:
        for field in ("passed", "skipped", "warning_count"):
            value = validation.get(field)
            if not isinstance(value, int) or value < 0:
                errors.append(f"baseline validation.{field} must be a non-negative integer")
        coverage = validation.get("coverage_percent")
        if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 100:
            errors.append("baseline validation.coverage_percent must be between 0 and 100")
        skipped_gates = validation.get("skipped_optional_gates")
        if not isinstance(skipped_gates, list) or not all(
            isinstance(gate, str) and gate for gate in skipped_gates
        ):
            errors.append(
                "baseline validation.skipped_optional_gates must be a list of non-empty strings"
            )

    return errors


def main() -> int:
    """Validate the release baseline and report all failures."""
    parser = argparse.ArgumentParser(description="Validate POWER release baseline contract")
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--models-lock", type=Path, default=DEFAULT_MODELS_LOCK)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    parser.add_argument("--git-repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--require-tag",
        action="store_true",
        help="fail when the release tag is not present or does not point to source.commit",
    )
    args = parser.parse_args()

    try:
        errors = validate_release_contract(
            pyproject_path=args.pyproject,
            models_lock_path=args.models_lock,
            baseline_path=args.baseline,
            dataset_manifest_path=args.dataset_manifest,
            git_repo=args.git_repo,
            require_tag=args.require_tag,
        )
    except ValueError as exc:
        print(f"Release contract validation failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Release contract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Release contract is valid for {args.baseline}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
