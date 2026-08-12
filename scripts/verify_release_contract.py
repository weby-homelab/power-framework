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

try:
    from release_platforms import DEFERRED_RELEASE_PLATFORMS, SUPPORTED_RELEASE_PLATFORMS
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.release_platforms import DEFERRED_RELEASE_PLATFORMS, SUPPORTED_RELEASE_PLATFORMS

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PYPROJECT = REPO_ROOT / "pyproject.toml"
DEFAULT_MODELS_LOCK = REPO_ROOT / "release" / "models.lock.json"
DEFAULT_BASELINE = REPO_ROOT / "release" / "evidence" / "baselines" / "v3.5.0.json"
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


def _worktree_hash(repo: Path, *, exclude: Path | None = None) -> str:
    """Hash the uncommitted worktree state without including file contents in output."""
    digest = hashlib.sha256()
    diff = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local arguments.
        ["git", "-C", str(repo), "diff", "--binary", "HEAD", "--"],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout
    digest.update(diff)
    paths = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local arguments.
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "-z"],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    excluded_name = None
    if exclude is not None:
        try:
            excluded_name = exclude.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            excluded_name = None
    for raw_name in sorted(path for path in paths if path):
        name = raw_name.decode("utf-8")
        if name == excluded_name:
            continue
        path = repo / name
        if not path.is_file() or path.is_symlink():
            continue
        digest.update(raw_name)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _validate_git_source(
    source: dict[str, Any],
    *,
    release: str,
    git_repo: Path,
    require_tag: bool,
    require_signed_tag: bool,
    candidate: bool = False,
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
    if candidate:
        # A candidate may be ahead of an existing release tag; final baselines
        # still bind the tag to the exact source commit below.
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
    if require_signed_tag and status == 0:
        signature_status, _, signature_stderr = _git(git_repo, "verify-tag", "--raw", tag)
        if signature_status != 0:
            errors.append(
                f"baseline source.tag is not a valid signed tag: {tag} ({signature_stderr})"
            )


def validate_release_contract(
    *,
    pyproject_path: Path,
    models_lock_path: Path,
    baseline_path: Path,
    dataset_manifest_path: Path,
    git_repo: Path,
    sbom_path: Path | None = None,
    upgrade_matrix_path: Path | None = None,
    require_tag: bool = False,
    require_signed_tag: bool = False,
    require_worktree_hash: bool = False,
    candidate: bool = False,
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
    if candidate:
        if baseline.get("candidate") is not True:
            errors.append("candidate release baseline must carry candidate=true")
        scope = baseline.get("scope")
        if not isinstance(scope, dict) or scope.get("candidate_only") is not True:
            errors.append("candidate release baseline must carry scope.candidate_only=true")
    else:
        if baseline.get("candidate") is True:
            errors.append("final release baseline cannot carry candidate=true")
        scope = baseline.get("scope")
        if not isinstance(scope, dict):
            errors.append("final release baseline scope must be an object")
        else:
            if scope.get("candidate_only") is True:
                errors.append("final release baseline cannot carry candidate_only=true")
            if scope.get("technical_release") is not True:
                errors.append("final release baseline scope.technical_release must be true")
            phase8_evidence = scope.get("phase8_evidence")
            if not isinstance(phase8_evidence, dict) or phase8_evidence.get("status") != "passed":
                errors.append("final release requires passed Phase 8 real-vault and human evidence")
            elif not all(
                isinstance(phase8_evidence.get(field), str)
                and re.fullmatch(r"[0-9a-f]{64}", phase8_evidence[field])
                for field in ("real_vault_receipt_sha256", "human_manifest_sha256")
            ):
                errors.append("final Phase 8 evidence must include both receipt SHA-256 bindings")
            if scope.get("human_quality_certification") is not True:
                errors.append("final release requires human_quality_certification=true")
            if scope.get("production_quality_claim") is not True:
                errors.append("final release requires production_quality_claim=true")
            if scope.get("sealed_holdout") != "passed":
                errors.append("final release requires sealed_holdout=passed")

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
        if source.get("clean") is not True and not candidate:
            errors.append(
                "baseline source.clean must be true; dirty source cannot be a release baseline"
            )
        if candidate and source.get("clean") is not True:
            worktree_hash = source.get("worktree_sha256")
            if not isinstance(worktree_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", worktree_hash
            ):
                errors.append(
                    "candidate source.worktree_sha256 must be a 64-character lowercase SHA-256"
                )
            elif require_worktree_hash and worktree_hash != _worktree_hash(
                git_repo, exclude=baseline_path
            ):
                errors.append(
                    "candidate source.worktree_sha256 does not match the current worktree"
                )
        _validate_git_source(
            source,
            release=package_version,
            git_repo=git_repo,
            require_tag=require_tag,
            require_signed_tag=require_signed_tag,
            candidate=candidate,
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
        if validation.get("schema_version") != "power.release-validation.v1":
            errors.append("baseline validation.schema_version must be power.release-validation.v1")
        if validation.get("status") != "passed":
            errors.append("baseline validation.status must be passed")
        if validation.get("content_free") is not True:
            errors.append("baseline validation.content_free must be true")
        for field in (
            "passed",
            "skipped",
            "warning_count",
            "mandatory_skipped",
            "mandatory_failed",
            "test_failures",
            "test_errors",
        ):
            value = validation.get(field)
            if not isinstance(value, int) or value < 0:
                errors.append(f"baseline validation.{field} must be a non-negative integer")
        if validation.get("mandatory_skipped") != 0:
            errors.append("baseline validation cannot contain skipped mandatory gates")
        if validation.get("mandatory_failed") != 0:
            errors.append("baseline validation cannot contain failed mandatory gates")
        if validation.get("warnings_as_errors") is not True or validation.get("warning_count") != 0:
            errors.append("baseline validation must prove warnings-as-errors with zero warnings")
        if validation.get("test_failures") != 0 or validation.get("test_errors") != 0:
            errors.append("baseline validation must contain zero test failures and errors")
        for field in ("junit_sha256", "coverage_sha256", "gate_manifest_sha256"):
            value = validation.get(field)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                errors.append(f"baseline validation.{field} must be a SHA-256")
        warning_policy = validation.get("warning_policy")
        if not isinstance(warning_policy, str) or not warning_policy:
            errors.append("baseline validation.warning_policy must be non-empty")
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
        if not candidate:
            technical_receipts = validation.get("technical_receipts")
            if (
                not isinstance(technical_receipts, dict)
                or technical_receipts.get("status") != "passed"
            ):
                errors.append("final release requires passed synthetic Phase 8 technical receipts")
            elif not all(
                isinstance(technical_receipts.get(field), str)
                and re.fullmatch(r"[0-9a-f]{64}", technical_receipts[field])
                for field in ("outcome_sha256", "continuity_sha256")
            ):
                errors.append("final technical receipts must include both SHA-256 bindings")
            sbom_hash = validation.get("sbom_sha256")
            if not isinstance(sbom_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", sbom_hash):
                errors.append("final release requires an SBOM SHA-256 binding")
            elif sbom_path is None or not sbom_path.is_file():
                errors.append("final release requires the referenced SBOM artifact")
            elif _sha256(sbom_path) != sbom_hash:
                errors.append("baseline SBOM SHA-256 does not match the supplied artifact")
            upgrade = validation.get("upgrade_matrix")
            if not isinstance(upgrade, dict) or upgrade.get("status") != "passed":
                errors.append("final release requires passed aggregate upgrade evidence")
            elif not isinstance(upgrade.get("sha256"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", upgrade["sha256"]
            ):
                errors.append("final upgrade evidence must include a SHA-256 binding")
            elif upgrade_matrix_path is None or not upgrade_matrix_path.is_file():
                errors.append("final release requires the referenced aggregate upgrade artifact")
            elif _sha256(upgrade_matrix_path) != upgrade["sha256"]:
                errors.append("baseline upgrade evidence SHA-256 does not match the artifact")
            if upgrade_matrix_path is not None and upgrade_matrix_path.is_file():
                upgrade_matrix = _load_json(upgrade_matrix_path)
                if upgrade_matrix.get("supported_platforms") != list(SUPPORTED_RELEASE_PLATFORMS):
                    errors.append(
                        "final upgrade evidence has an unexpected supported-platform boundary"
                    )
                if upgrade_matrix.get("deferred_platforms") != list(DEFERRED_RELEASE_PLATFORMS):
                    errors.append(
                        "final upgrade evidence has an unexpected deferred-platform boundary"
                    )
                if upgrade_matrix.get("platforms") != dict.fromkeys(
                    SUPPORTED_RELEASE_PLATFORMS, "executed"
                ):
                    errors.append("final upgrade evidence must execute every supported platform")

    return errors


def main() -> int:
    """Validate the release baseline and report all failures."""
    parser = argparse.ArgumentParser(description="Validate POWER release baseline contract")
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--models-lock", type=Path, default=DEFAULT_MODELS_LOCK)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--upgrade-matrix-aggregate", type=Path)
    parser.add_argument("--git-repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--require-tag",
        action="store_true",
        help="fail when the release tag is not present or does not point to source.commit",
    )
    parser.add_argument(
        "--require-signed-tag",
        action="store_true",
        help="fail unless the resolved release tag has a valid Git signature",
    )
    parser.add_argument(
        "--require-worktree-hash",
        action="store_true",
        help="require a candidate baseline hash to match the current dirty worktree",
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="validate a dirty, explicitly marked release candidate; never permits final publish",
    )
    args = parser.parse_args()

    try:
        errors = validate_release_contract(
            pyproject_path=args.pyproject,
            models_lock_path=args.models_lock,
            baseline_path=args.baseline,
            dataset_manifest_path=args.dataset_manifest,
            git_repo=args.git_repo,
            sbom_path=args.sbom,
            upgrade_matrix_path=args.upgrade_matrix_aggregate,
            require_tag=args.require_tag,
            require_signed_tag=args.require_signed_tag,
            require_worktree_hash=args.require_worktree_hash,
            candidate=args.candidate,
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
