#!/usr/bin/env python3
"""Reproducible FTS OR-vs-AND operator benchmark for P.O.W.E.R.

One command runs both variants (``POWER_FTS_OPERATOR=OR`` and ``=AND``) over
one frozen corpus, query set and independent qrels fixture, then produces the
comparison and all artifacts. The FTS index is synced exactly once before
either variant so the two runs share one immutable index; the only thing that
changes between variants is the boolean operator environment variable (scoped,
restored afterwards).

Usage:
    python benchmarks/fts_operator/scripts/run_benchmark.py \
        --dataset benchmarks/power31/dataset/v1 \
        --provenance benchmarks/fts_operator/fixtures/ground_truth_provenance.json \
        --output benchmarks/fts_operator/results/run-YYYYMMDD \
        [--top-k 10] [--seed 20260801] [--samples 10000]

Exit code 0 = run completed and artifacts written. The conclusion is data
driven and may be "no clear winner" or "insufficient evidence".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED  # noqa: E402
from compare import (  # noqa: E402
    build_report_markdown,
    compare_paired_rows,
    summarize_groups,
    write_per_query_csv,
    write_summary_csv,
)
from ground_truth import fts_operator_env, load_ground_truth  # noqa: E402
from metrics import compute_query_metrics  # noqa: E402

DEFAULT_DATASET = REPO_ROOT / "benchmarks" / "power31" / "dataset" / "v1"
DEFAULT_PROVENANCE = (
    REPO_ROOT / "benchmarks" / "fts_operator" / "fixtures" / "ground_truth_provenance.json"
)
BM25_WEIGHTS = {"title": 10.0, "tags": 5.0, "description": 3.0, "content": 1.0}
METRIC_NAMES = (
    "ndcg@5",
    "ndcg@10",
    "recall@5",
    "recall@10",
    "mrr@5",
    "mrr@10",
    "precision@5",
    "precision@10",
    "hit_rate@5",
    "hit_rate@10",
)
PRIMARY_METRICS = ("ndcg@5", "recall@10", "mrr@5", "zero_result")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        # git resolved via shutil.which; no untrusted input reaches the call.
        completed = subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _corpus_snapshot_hash(corpus_dir: Path) -> str:
    """Deterministic corpus hash: sorted relative path + content sha256."""
    digest = hashlib.sha256()
    for filepath in sorted(corpus_dir.glob("*.md")):
        digest.update(filepath.name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(_sha256_file(filepath).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _load_variant_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"variant config must be a YAML mapping: {path}")
    operator = str(data.get("fts_operator", "")).upper()
    if operator not in {"OR", "AND"}:
        raise ValueError(f"variant config {path} must declare fts_operator OR or AND")
    return data


def _materialise_vault(corpus_dir: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    resource_dir = target / "03_Resources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    for md_file in sorted(corpus_dir.glob("*.md")):
        shutil.copy2(md_file, resource_dir / md_file.name)


def _sync_fts_once(vault_dir: Path, db_path: Path) -> None:
    """Sync the single immutable FTS index used by both variants."""
    from power_framework.core.db import _init_db
    from power_framework.core.searcher import _sync_vault_to_db

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        _init_db(conn)
        _sync_vault_to_db(vault_dir, conn, sync_embeddings=False)
        row = conn.execute("SELECT COUNT(*) FROM file_metadata").fetchone()
        if row is None or row[0] == 0:
            raise RuntimeError("FTS sync produced an empty index")
    finally:
        conn.close()


def _run_variant(
    vault_dir: Path,
    ground_truth: Any,
    operator: str,
    top_k: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from power_framework.core.searcher import search_vault

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with fts_operator_env(operator):
        for query_id, query_record in ground_truth.queries.items():
            try:
                results = search_vault(
                    vault_dir,
                    query_record.query,
                    max_results=top_k,
                    mode="fts",
                    temporal_view="all",
                )
                # Normalize rel_path to the qrels document-id space (file name),
                # matching the power31 corpus/qrels convention.
                retrieved = [Path(result.rel_path).name for result in results]
            except Exception as exc:
                failures.append(
                    {
                        "query_id": query_id,
                        "operator": operator,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                retrieved = []
            relevant = ground_truth.qrels.get(query_id, {})
            metrics = compute_query_metrics(retrieved, relevant, k_values=(5, 10))
            relevant_set = set(relevant)
            retrieved_set = set(retrieved)
            row: dict[str, Any] = {
                "query_id": query_id,
                "query": query_record.query,
                "query_language": query_record.language,
                "query_class": query_record.query_class,
                "stratum": query_record.stratum,
                "query_term_count": query_record.term_count,
                "has_phrase": int(query_record.has_phrase),
                "has_hyphen": int(query_record.has_hyphen),
                "relevant_count": len(relevant),
            }
            row.update(metrics)
            row[f"{operator.lower()}_top10"] = json.dumps(retrieved[:10], ensure_ascii=False)
            row[f"{operator.lower()}_only_relevant"] = json.dumps(
                sorted(retrieved_set & relevant_set), ensure_ascii=False
            )
            rows.append(row)
    return rows, failures


def _merge_pair_rows(
    or_rows: list[dict[str, Any]], and_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair per-query rows of both variants into one diagnostic CSV row."""
    by_id = {row["query_id"]: row for row in and_rows}
    if len(by_id) != len(and_rows):
        raise ValueError("AND run contains duplicate query_ids")
    merged: list[dict[str, Any]] = []
    for or_row in or_rows:
        query_id = str(or_row["query_id"])
        and_row = by_id.pop(query_id, None)
        if and_row is None:
            raise ValueError(f"AND run is missing query {query_id}; paired design violated")
        or_relevant = set(json.loads(or_row["or_only_relevant"]))
        and_relevant = set(json.loads(and_row["and_only_relevant"]))
        merged.append(
            {
                "query_id": query_id,
                "query": or_row["query"],
                "query_language": or_row["query_language"],
                "query_class": or_row["query_class"],
                "stratum": or_row["stratum"],
                "query_term_count": or_row["query_term_count"],
                "relevant_count": or_row["relevant_count"],
                "or_result_count": or_row["result_count"],
                "and_result_count": and_row["result_count"],
                "or_top10": or_row["or_top10"],
                "and_top10": and_row["and_top10"],
                "or_relevant_hits@5": or_row["relevant_hits@5"],
                "and_relevant_hits@5": and_row["relevant_hits@5"],
                "or_relevant_hits@10": or_row["relevant_hits@10"],
                "and_relevant_hits@10": and_row["relevant_hits@10"],
                "or_first_relevant_rank": or_row["first_relevant_rank"],
                "and_first_relevant_rank": and_row["first_relevant_rank"],
                "or_zero_result": or_row["zero_result"],
                "and_zero_result": and_row["zero_result"],
                "or_only_relevant": or_row["or_only_relevant"],
                "and_only_relevant": and_row["and_only_relevant"],
                "common_relevant": json.dumps(
                    sorted(or_relevant & and_relevant), ensure_ascii=False
                ),
                **{f"or_{metric}": or_row[metric] for metric in METRIC_NAMES},
                **{f"and_{metric}": and_row[metric] for metric in METRIC_NAMES},
            }
        )
    if by_id:
        raise ValueError(f"AND run contains queries absent from OR run: {sorted(by_id)[:5]}")
    return merged


def _zero_result_diagnostics(merged_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "query_id": row["query_id"],
            "query": row["query"],
            "stratum": row["stratum"],
            "or_relevant_hits@10": row["or_relevant_hits@10"],
        }
        for row in merged_rows
        if row["or_zero_result"] == 0 and row["and_zero_result"] == 1
    ]


def _example_winners(
    merged_rows: list[dict[str, Any]],
    prefer_or: bool,
    limit: int = 10,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for row in sorted(
        merged_rows,
        key=lambda r: (
            (float(r["and_recall@10"]) - float(r["or_recall@10"]))
            if prefer_or
            else (float(r["or_recall@10"]) - float(r["and_recall@10"]))
        ),
        reverse=True,
    ):
        or_recall = float(row["or_recall@10"])
        and_recall = float(row["and_recall@10"])
        if (prefer_or and or_recall > and_recall) or (not prefer_or and and_recall > or_recall):
            examples.append(row)
        if len(examples) >= limit:
            break
    return examples


def _build_manifest(
    args: argparse.Namespace,
    dataset: Path,
    provenance_path: Path,
    ground_truth: Any,
    queries_path: Path,
    qrels_path: Path,
    corpus_document_count: int,
) -> dict[str, Any]:
    import sqlite3 as sqlite_module
    import sys as sys_module

    try:
        # Prefer the repo-declared version (deterministic) over the possibly
        # stale installed metadata.
        pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r"^version\s*=\s*\"([^\"]+)\"", pyproject_text, re.MULTILINE)
        power_version = match.group(1) if match else "unknown"
    except OSError:
        power_version = "unknown"
    return {
        "schema_version": "power.fts-operator.manifest.v1",
        "power_version": power_version,
        "git_commit": _git_commit(),
        "python_version": sys_module.version.split()[0],
        "sqlite_version": sqlite_module.sqlite_version,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "corpus_path": str(dataset / "corpus"),
        "corpus_snapshot_hash": _corpus_snapshot_hash(dataset / "corpus"),
        "corpus_document_count": corpus_document_count,
        "queries_path": str(queries_path),
        "queries_sha256": ground_truth.queries_sha256,
        "qrels_path": str(qrels_path),
        "qrels_sha256": ground_truth.qrels_sha256,
        "provenance_path": str(provenance_path),
        "provenance_sha256": ground_truth.provenance_sha256,
        "variants": {
            "fts_or": {"mode": "fts", "fts_operator": "OR"},
            "fts_and": {"mode": "fts", "fts_operator": "AND"},
        },
        "bm25_weights": BM25_WEIGHTS,
        "code_changed_between_variants": False,
        "index": "single FTS index synced once before both variants",
        "top_k": args.top_k,
        "seed": args.seed,
        "bootstrap_resamples": args.samples,
        "query_count": len(ground_truth.queries),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--config-or", type=Path)
    parser.add_argument("--config-and", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--samples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--vault-dir", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = args.dataset.resolve()
    queries_path = dataset / "queries.jsonl"
    qrels_path = dataset / "qrels.synthetic.jsonl"
    corpus_dir = dataset / "corpus"
    for required in (queries_path, qrels_path, corpus_dir, args.provenance):
        if not required.exists():
            raise SystemExit(f"missing required fixture: {required}")

    if args.config_or is not None:
        _load_variant_config(args.config_or)
    if args.config_and is not None:
        _load_variant_config(args.config_and)

    ground_truth = load_ground_truth(queries_path, qrels_path, args.provenance)
    corpus_document_count = len(list(corpus_dir.glob("*.md")))

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    vault_dir = args.vault_dir or Path(tempfile.mkdtemp(prefix="fts-operator-vault-"))
    _materialise_vault(corpus_dir, vault_dir)
    db_path = vault_dir / ".power_search.db"
    previous_db = os.environ.get("POWER_SEARCH_DB")
    os.environ["POWER_SEARCH_DB"] = str(db_path)
    try:
        _sync_fts_once(vault_dir, db_path)
        or_rows, or_failures = _run_variant(vault_dir, ground_truth, "OR", args.top_k)
        and_rows, and_failures = _run_variant(vault_dir, ground_truth, "AND", args.top_k)
    finally:
        if previous_db is None:
            os.environ.pop("POWER_SEARCH_DB", None)
        else:
            os.environ["POWER_SEARCH_DB"] = previous_db

    merged_rows = _merge_pair_rows(or_rows, and_rows)
    comparison = compare_paired_rows(or_rows, and_rows, seed=args.seed, n_resamples=args.samples)
    groups = summarize_groups(or_rows, and_rows)
    newly_lost = _zero_result_diagnostics(merged_rows)
    examples_or = _example_winners(merged_rows, prefer_or=True)
    examples_and = _example_winners(merged_rows, prefer_or=False)
    failures = [*or_failures, *and_failures]

    manifest = _build_manifest(
        args,
        dataset,
        args.provenance,
        ground_truth,
        queries_path,
        qrels_path,
        corpus_document_count,
    )
    manifest["variant_configs"] = {
        "fts_or": str(args.config_or) if args.config_or else None,
        "fts_and": str(args.config_and) if args.config_and else None,
    }

    write_per_query_csv(merged_rows, output_dir / "per_query.csv")
    write_summary_csv(comparison, groups, output_dir / "summary.csv")

    comparison_artifact = {
        "schema_version": "power.fts-operator.comparison.v1",
        "conclusion": comparison["conclusion"],
        "primary_metrics": list(PRIMARY_METRICS),
        "metrics": comparison["metrics"],
        "groups": groups,
        "zero_result": {
            "newly_lost_by_and": len(newly_lost),
            "newly_lost_queries": newly_lost,
        },
        "failures": failures,
        "examples": {
            "or_wins": examples_or,
            "and_wins": examples_and,
        },
    }
    (output_dir / "comparison.json").write_text(
        json.dumps(comparison_artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = build_report_markdown(
        comparison,
        groups,
        merged_rows,
        manifest,
        newly_lost,
        examples_or,
        examples_and,
        failures,
    )
    (output_dir / "comparison.md").write_text(report, encoding="utf-8")
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    failures_path = output_dir / "failures.json"
    failures_path.write_text(
        json.dumps(failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    bootstrap_path = output_dir / "bootstrap.json"
    bootstrap_path.write_text(
        json.dumps(
            {
                metric: {
                    "or_mean": comparison["metrics"][metric]["or_mean"],
                    "and_mean": comparison["metrics"][metric]["and_mean"],
                    "delta_and_minus_or": comparison["metrics"][metric]["delta_and_minus_or"],
                    "ci95": comparison["metrics"][metric]["ci95"],
                    "n": comparison["metrics"][metric]["n"],
                    "seed": args.seed,
                    "resamples": args.samples,
                }
                for metric in PRIMARY_METRICS
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    conclusion = comparison["conclusion"]
    sys.stdout.write(
        json.dumps(
            {
                "output": str(output_dir),
                "queries": len(merged_rows),
                "or_zero_result_rate": comparison["metrics"]["zero_result"]["or_mean"],
                "and_zero_result_rate": comparison["metrics"]["zero_result"]["and_mean"],
                "recall10_or": comparison["metrics"]["recall@10"]["or_mean"],
                "recall10_and": comparison["metrics"]["recall@10"]["and_mean"],
                "conclusion": conclusion["label"],
                "newly_lost_by_and": len(newly_lost),
                "failures": len(failures),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
