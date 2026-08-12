#!/usr/bin/env python3
"""Generate a release baseline bound to the exact annotated tag commit."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from release_platforms import DEFERRED_RELEASE_PLATFORMS, SUPPORTED_RELEASE_PLATFORMS
    from verify_phase8_evidence import validate_phase8_evidence, validate_technical_receipts
    from verify_release_contract import (
        DEFAULT_DATASET_MANIFEST,
        DEFAULT_MODELS_LOCK,
        REPO_ROOT,
        _git,
        _load_json,
        _load_package_version,
        _sha256,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.release_platforms import DEFERRED_RELEASE_PLATFORMS, SUPPORTED_RELEASE_PLATFORMS
    from scripts.verify_phase8_evidence import validate_phase8_evidence, validate_technical_receipts
    from scripts.verify_release_contract import (
        DEFAULT_DATASET_MANIFEST,
        DEFAULT_MODELS_LOCK,
        REPO_ROOT,
        _git,
        _load_json,
        _load_package_version,
        _sha256,
    )

TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
DEFAULT_TEMPLATE = REPO_ROOT / "release" / "evidence" / "baselines" / "v3.4.0.json"
VALIDATION_SCHEMA_VERSION = "power.release-validation.v1"


def _default_template() -> Path:
    candidates = sorted((REPO_ROOT / "release" / "evidence" / "baselines").glob("v*.json"))
    for candidate in reversed(candidates):
        try:
            payload = _load_json(candidate)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if payload.get("candidate") is not True:
            return candidate
    return DEFAULT_TEMPLATE


def _manifest_hash(manifest: dict[str, Any], section: str) -> str:
    value = manifest.get(section, {}).get("hash_sha256")
    if not isinstance(value, str) or not value:
        raise ValueError(f"dataset manifest has no {section}.hash_sha256")
    return value


def _load_validation_report(path: Path) -> dict[str, Any]:
    """Load exact CI validation counts and reject stale or incomplete reports."""
    report = _load_json(path)
    if report.get("schema_version") != VALIDATION_SCHEMA_VERSION:
        raise ValueError("validation report has an unsupported schema")
    if report.get("status") != "passed":
        raise ValueError("validation report status must be passed")
    if report.get("content_free") is not True:
        raise ValueError("validation report must be content-free")
    for field in (
        "passed",
        "skipped",
        "warning_count",
        "mandatory_skipped",
        "mandatory_failed",
    ):
        value = report.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"validation report {field} must be a non-negative integer")
    if report["mandatory_skipped"] != 0:
        raise ValueError("validation report cannot contain skipped mandatory gates")
    if report["mandatory_failed"] != 0:
        raise ValueError("validation report cannot contain failed mandatory gates")
    if report.get("warnings_as_errors") is not True or report["warning_count"] != 0:
        raise ValueError("validation report must prove warnings-as-errors with zero warnings")
    for field in ("junit_sha256", "coverage_sha256", "gate_manifest_sha256"):
        value = report.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"validation report {field} must be a SHA-256")
    coverage = report.get("coverage_percent")
    if (
        not isinstance(coverage, (int, float))
        or isinstance(coverage, bool)
        or not math.isfinite(float(coverage))
        or not 0 <= float(coverage) <= 100
    ):
        raise ValueError("validation report coverage_percent must be finite and between 0 and 100")
    if not isinstance(report.get("warning_policy"), str) or not report["warning_policy"]:
        raise ValueError("validation report warning_policy must be non-empty")
    skipped_gates = report.get("skipped_optional_gates")
    if not isinstance(skipped_gates, list) or not all(
        isinstance(gate, str) and gate for gate in skipped_gates
    ):
        raise ValueError("validation report skipped_optional_gates must be a list of strings")
    return report


def _git_output(repo: Path, *args: str) -> str:
    status, stdout, stderr = _git(repo, *args)
    if status != 0:
        raise ValueError(f"git query failed: {' '.join(args)}: {stderr}")
    return stdout


def build_baseline(
    *,
    repo: Path,
    tag: str,
    template_path: Path,
    models_lock_path: Path,
    dataset_manifest_path: Path,
    validation_report_path: Path,
    sbom_path: Path,
    upgrade_matrix_path: Path,
    phase8_real_vault_receipt_path: Path | None = None,
    phase8_human_manifest_path: Path | None = None,
    phase8_outcome_receipt_path: Path | None = None,
    phase8_continuity_receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Return a baseline whose source fields describe ``tag`` exactly."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"invalid release tag: {tag}")

    if not sbom_path.is_file():
        raise ValueError(f"SBOM artifact is missing: {sbom_path}")
    upgrade_matrix = _load_json(upgrade_matrix_path)
    if upgrade_matrix.get("schema_version") != "power.upgrade-matrix.aggregate.v1":
        raise ValueError("upgrade matrix aggregate has an unsupported schema")
    if upgrade_matrix.get("content_free") is not True:
        raise ValueError("upgrade matrix aggregate must be content-free")
    if upgrade_matrix.get("raw_content_in_report") is not False:
        raise ValueError("upgrade matrix aggregate must not contain raw content")
    upgrade_gate = upgrade_matrix.get("release_gate")
    if not isinstance(upgrade_gate, dict) or upgrade_gate.get("all_platforms_executed") is not True:
        raise ValueError("upgrade matrix aggregate must cover all supported platforms")
    if upgrade_gate.get("local_invariants") is not True:
        raise ValueError("upgrade matrix aggregate local invariants must pass")
    if upgrade_matrix.get("supported_platforms") != list(SUPPORTED_RELEASE_PLATFORMS):
        raise ValueError("upgrade matrix aggregate has an unexpected supported-platform boundary")
    if upgrade_matrix.get("deferred_platforms") != list(DEFERRED_RELEASE_PLATFORMS):
        raise ValueError("upgrade matrix aggregate has an unexpected deferred-platform boundary")
    if upgrade_matrix.get("platforms") != dict.fromkeys(SUPPORTED_RELEASE_PLATFORMS, "executed"):
        raise ValueError("upgrade matrix aggregate must execute every supported platform")

    package_version = _load_package_version(repo / "pyproject.toml")
    expected_tag = f"v{package_version}"
    if tag != expected_tag:
        raise ValueError(f"tag {tag} does not match package version {package_version}")

    commit = _git_output(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    head = _git_output(repo, "rev-parse", "--verify", "HEAD")
    if head != commit:
        raise ValueError("final release baseline must be generated from the checked-out tag commit")
    if _git_output(repo, "status", "--porcelain"):
        raise ValueError("final release baseline requires a clean worktree")
    tree = _git_output(repo, "show", "-s", "--format=%T", commit)
    baseline = copy.deepcopy(_load_json(template_path))
    manifest = _load_json(dataset_manifest_path)

    baseline["release"] = package_version
    baseline["source"] = {
        "commit": commit,
        "tree": tree,
        "tag": tag,
        "clean": True,
    }
    # A candidate baseline may be the most recent template in the worktree.
    # Never carry its publication boundary into a clean, tag-bound artifact.
    baseline["candidate"] = False
    scope = baseline.setdefault("scope", {})
    if not isinstance(scope, dict):
        raise ValueError("baseline scope must be an object")
    scope["technical_release"] = True
    scope["candidate_only"] = False
    scope["phase8_evidence"] = {"status": "pending"}
    validation_report = _load_validation_report(validation_report_path)
    validation = baseline["validation"] = copy.deepcopy(validation_report)
    validation["sbom_sha256"] = _sha256(sbom_path)
    validation["upgrade_matrix"] = {
        "status": "passed",
        "sha256": _sha256(upgrade_matrix_path),
    }
    validation["technical_receipts"] = {"status": "pending"}
    if (phase8_outcome_receipt_path is None) != (phase8_continuity_receipt_path is None):
        raise ValueError("Phase 8 outcome and continuity receipt paths must be supplied together")
    if phase8_outcome_receipt_path is not None and phase8_continuity_receipt_path is not None:
        errors = validate_technical_receipts(
            outcome_path=phase8_outcome_receipt_path,
            continuity_path=phase8_continuity_receipt_path,
        )
        if errors:
            raise ValueError("Phase 8 technical receipt validation failed: " + "; ".join(errors))
        validation["technical_receipts"] = {
            "status": "passed",
            "outcome_sha256": hashlib.sha256(phase8_outcome_receipt_path.read_bytes()).hexdigest(),
            "continuity_sha256": hashlib.sha256(
                phase8_continuity_receipt_path.read_bytes()
            ).hexdigest(),
        }
    if (phase8_real_vault_receipt_path is None) != (phase8_human_manifest_path is None):
        raise ValueError("Phase 8 real-vault and human evidence paths must be supplied together")
    if phase8_real_vault_receipt_path is not None and phase8_human_manifest_path is not None:
        errors = validate_phase8_evidence(
            real_vault_receipt_path=phase8_real_vault_receipt_path,
            human_manifest_path=phase8_human_manifest_path,
            release=package_version,
        )
        if errors:
            raise ValueError("Phase 8 evidence validation failed: " + "; ".join(errors))
        scope["phase8_evidence"] = {
            "status": "passed",
            "real_vault_receipt_sha256": hashlib.sha256(
                phase8_real_vault_receipt_path.read_bytes()
            ).hexdigest(),
            "human_manifest_sha256": hashlib.sha256(
                phase8_human_manifest_path.read_bytes()
            ).hexdigest(),
        }
        scope["human_quality_certification"] = True
        scope["production_quality_claim"] = True
        scope["sealed_holdout"] = "passed"
    benchmark = baseline.setdefault("benchmark", {})
    benchmark["synthetic"] = True
    benchmark["corpus_sha256"] = _manifest_hash(manifest, "corpus")
    benchmark["queries_sha256"] = _manifest_hash(manifest, "queries")
    benchmark["qrels_sha256"] = _manifest_hash(manifest, "qrels")
    benchmark["expected_answers_sha256"] = _manifest_hash(manifest, "expected_answers")
    baseline["models_lock_sha256"] = _sha256(models_lock_path)
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=_default_template())
    parser.add_argument("--models-lock", type=Path, default=DEFAULT_MODELS_LOCK)
    parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--upgrade-matrix-aggregate", type=Path, required=True)
    parser.add_argument("--phase8-real-vault-receipt", type=Path)
    parser.add_argument("--phase8-human-manifest", type=Path)
    parser.add_argument("--phase8-outcome-receipt", type=Path)
    parser.add_argument("--phase8-continuity-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        baseline = build_baseline(
            repo=REPO_ROOT,
            tag=args.tag,
            template_path=args.template,
            models_lock_path=args.models_lock,
            dataset_manifest_path=args.dataset_manifest,
            validation_report_path=args.validation_report,
            sbom_path=args.sbom,
            upgrade_matrix_path=args.upgrade_matrix_aggregate,
            phase8_real_vault_receipt_path=args.phase8_real_vault_receipt,
            phase8_human_manifest_path=args.phase8_human_manifest,
            phase8_outcome_receipt_path=args.phase8_outcome_receipt,
            phase8_continuity_receipt_path=args.phase8_continuity_receipt,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Release baseline written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
