#!/usr/bin/env python3
"""Generate a dirty-worktree release-candidate baseline.

This artifact is useful for local/CI candidate gates only.  Final release
evidence must be generated from an exact clean tag with
``generate_release_baseline.py`` and validated with ``--require-tag``.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from verify_phase8_evidence import validate_technical_receipts
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.verify_phase8_evidence import validate_technical_receipts
try:
    from generate_release_baseline import _load_validation_report
    from verify_release_contract import (
        REPO_ROOT,
        _load_json,
        _load_package_version,
        _sha256,
        _worktree_hash,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.generate_release_baseline import _load_validation_report
    from scripts.verify_release_contract import (
        REPO_ROOT,
        _load_json,
        _load_package_version,
        _sha256,
        _worktree_hash,
    )


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local arguments.
        ["git", "-C", str(repo), *args],  # noqa: S607 -- fixed executable name.
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def build_candidate(
    *,
    repo: Path,
    template: Path,
    models_lock: Path,
    validation_report_path: Path,
    output_path: Path | None = None,
    phase8_outcome_receipt_path: Path | None = None,
    phase8_continuity_receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Return candidate metadata bound to the current worktree identity."""
    version = _load_package_version(repo / "pyproject.toml")
    commit = _git(repo, "rev-parse", "--verify", "HEAD").strip()
    tree = _git(repo, "show", "-s", "--format=%T", commit).strip()
    worktree_sha256 = _worktree_hash(repo, exclude=output_path)
    baseline = copy.deepcopy(_load_json(template))
    baseline["release"] = version
    baseline["candidate"] = True
    baseline["source"] = {
        "commit": commit,
        "tree": tree,
        "tag": f"v{version}",
        "clean": False,
        "worktree_sha256": worktree_sha256,
    }
    baseline["models_lock_sha256"] = _sha256(models_lock)
    if (phase8_outcome_receipt_path is None) != (phase8_continuity_receipt_path is None):
        raise ValueError("Phase 8 outcome and continuity receipt paths must be supplied together")
    technical_receipts: dict[str, Any] = {"status": "pending"}
    if phase8_outcome_receipt_path is not None and phase8_continuity_receipt_path is not None:
        errors = validate_technical_receipts(
            outcome_path=phase8_outcome_receipt_path,
            continuity_path=phase8_continuity_receipt_path,
            release=version,
            source_commit=commit,
            source_tree=tree,
            worktree_sha256=worktree_sha256,
        )
        if errors:
            raise ValueError("Phase 8 technical receipt validation failed: " + "; ".join(errors))
        technical_receipts = {
            "status": "passed",
            "outcome_sha256": _sha256(phase8_outcome_receipt_path),
            "continuity_sha256": _sha256(phase8_continuity_receipt_path),
        }
    validation = _load_validation_report(validation_report_path)
    validation["technical_receipts"] = technical_receipts
    baseline["validation"] = validation
    baseline["scope"] = {
        "technical_release": False,
        "candidate_only": True,
        "phase8_evidence": {"status": "pending"},
        "human_quality_certification": False,
        "production_quality_claim": False,
        "sealed_holdout": "do_not_open",
    }
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--phase8-outcome-receipt", type=Path)
    parser.add_argument("--phase8-continuity-receipt", type=Path)
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO_ROOT / "release" / "evidence" / "baselines" / "v3.4.5.json",
    )
    parser.add_argument(
        "--models-lock", type=Path, default=REPO_ROOT / "release" / "models.lock.json"
    )
    args = parser.parse_args(argv)
    candidate = build_candidate(
        repo=REPO_ROOT,
        template=args.template,
        models_lock=args.models_lock,
        validation_report_path=args.validation_report,
        output_path=args.output,
        phase8_outcome_receipt_path=args.phase8_outcome_receipt,
        phase8_continuity_receipt_path=args.phase8_continuity_receipt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Release candidate baseline written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
