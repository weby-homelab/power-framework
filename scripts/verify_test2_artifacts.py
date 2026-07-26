#!/usr/bin/env python3
"""Fail closed when published TEST-2 evidence is incomplete or inconsistent."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

REQUIRED = {
    "run-manifest.json",
    "environment.txt",
    "git-commit.txt",
    "git-status-start.txt",
    "git-status-end.txt",
    "source-sha256.txt",
    "pytest.log",
    "pytest-pr-ws.xml",
    "pytest-origin-main-ws.log",
    "pytest-origin-main-ws.xml",
    "pytest-baseline-comparison.json",
    "pytest-baseline-comparison.md",
    "known-baseline-failures.md",
    "coverage.json",
    "ruff.log",
    "mypy.log",
    "power-lint.log",
    "db-state-final.txt",
    "db-schema.txt",
    "duplicate-chunks.txt",
    "chunk-count-explanation.md",
    "db-integrity.txt",
    "quality-development.csv",
    "quality-development-per-query.csv",
    "quality-holdout.csv",
    "quality-holdout-per-query.csv",
    "candidate-recall.csv",
    "holdout-sha256.txt",
    "cold-latency.csv",
    "warm-inprocess-latency.csv",
    "warm-mcp-latency.csv",
    "memory-rss.csv",
    "memory-cgroup.csv",
    "sync-stages.csv",
    "determinism-neural.csv",
    "crash-recovery.log",
    "security-file-api.log",
    "egress-semantic-filtered.txt",
    "egress-semantic.stdout",
    "egress-semantic.stderr",
    "egress-semantic.exit-code",
    "egress-reranked-filtered.txt",
    "egress-reranked.stdout",
    "egress-reranked.stderr",
    "egress-reranked.exit-code",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    art = args.artifacts
    errors = [
        f"missing artifact: {name}" for name in sorted(REQUIRED) if not (art / name).is_file()
    ]
    if not list(art.glob("egress-semantic.raw*")):
        errors.append("missing semantic raw egress capture")
    if not list(art.glob("egress-reranked.raw*")):
        errors.append("missing reranked raw egress capture")
    try:
        summary = json.loads((art / "benchmark-summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid benchmark summary: {exc}")
        summary = {}
    sha = summary.get("tested_source_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        errors.append("tested_source_commit is not a full 40-character SHA")
    if (
        summary.get("working_tree_clean_at_start") is not True
        or summary.get("working_tree_clean_at_end") is not True
    ):
        errors.append("benchmark git tree was not clean")
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", summary.get("evidence_generated_at_utc", "")
    ):
        errors.append("missing or placeholder evidence timestamp")
    if not all(
        isinstance(summary.get("db_actual", {}).get(key), int)
        for key in ("doc_embeddings", "chunk_embeddings")
    ):
        errors.append("actual DB counts are missing")
    comparison = summary.get("pytest", {})
    failed_nodeids = comparison.get("pr_failed_nodeids", [])
    if comparison.get("failures", 0) + comparison.get("errors", 0) != len(failed_nodeids):
        errors.append("pytest failure category sums do not match parsed nodeids")
    fixture = args.repo / "tests/fixtures/semantic_gt_holdout_v1.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    if data.get("metadata", {}).get("query_count") != len(data.get("queries", [])):
        errors.append("holdout metadata count does not match fixture")
    holdout_checksum = art / "holdout-sha256.txt"
    if holdout_checksum.exists():
        expected_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        recorded_hash = holdout_checksum.read_text(encoding="utf-8", errors="replace").split()[0:1]
        if recorded_hash != [expected_hash]:
            errors.append("holdout SHA256 artifact does not match fixture")
    comparison_path = art / "pytest-baseline-comparison.json"
    if comparison_path.exists():
        try:
            parsed_comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid pytest baseline comparison: {exc}")
        else:
            expected_sets = {
                "fixed_failures": set(parsed_comparison.get("baseline_failed_nodeids", []))
                - set(parsed_comparison.get("pr_failed_nodeids", [])),
                "new_failures": set(parsed_comparison.get("pr_failed_nodeids", []))
                - set(parsed_comparison.get("baseline_failed_nodeids", [])),
                "common_failures": set(parsed_comparison.get("baseline_failed_nodeids", []))
                & set(parsed_comparison.get("pr_failed_nodeids", [])),
            }
            if any(
                set(parsed_comparison.get(name, [])) != values
                for name, values in expected_sets.items()
            ):
                errors.append("pytest baseline comparison set differences are inconsistent")
    env_text = (
        (art / "environment.txt").read_text(encoding="utf-8", errors="replace")
        if (art / "environment.txt").exists()
        else ""
    )
    if re.search(r"Machine ID|Boot ID|ghp_|github_pat_|BEGIN .*PRIVATE KEY", env_text, re.I):
        errors.append("environment artifact contains sensitive host or credential material")
    report = args.report.read_text(encoding="utf-8") if args.report.exists() else ""
    if sha and sha not in report:
        errors.append("report does not contain tested source SHA")
    for value in summary.get("db_actual", {}).values():
        if isinstance(value, int) and str(value) not in report:
            errors.append("report does not match DB counts in summary")
            break
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        changed = subprocess.run(  # noqa: S603
            [
                "/usr/bin/git",
                "-C",
                str(args.repo),
                "diff",
                "--name-only",
                f"{sha}..HEAD",
                "--",
                "src",
                "tests",
                "scripts",
                "pyproject.toml",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if changed.returncode or changed.stdout.strip():
            errors.append("source changed after tested source commit")
    if errors:
        print("TEST-2 artifact verification FAILED")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("TEST-2 artifact verification PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
