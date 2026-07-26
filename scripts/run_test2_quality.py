#!/usr/bin/env python3
"""Write reproducible per-query and grouped retrieval-quality CSV artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades))


def _groups(data: dict[str, Any]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for name, group in data.get("language_groups", {}).items():
        for index in group.get("query_indexes", []):
            labels[index] = name
    return labels


def _reranker_candidate_paths(vault: Path, query: str) -> set[str]:
    """Reproduce the raw candidate union used before reranking for audit only."""
    from power_framework.core.searcher import (
        _fts_search,
        _rrf_merge,
        _semantic_search,
        _vector_search,
    )

    candidates = _rrf_merge(
        _fts_search(vault, query, max_results=150),
        _vector_search(vault, query, max_results=150),
    )
    return {item.rel_path for item in _rrf_merge(candidates, _semantic_search(vault, query, 60))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument(
        "--mode", required=True, choices=["fts", "vector", "hybrid", "semantic", "reranked"]
    )
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--per-query-output", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path)
    args = parser.parse_args()

    from power_framework.core.searcher import search_vault

    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    query_groups = _groups(data)
    rows: list[dict[str, str | float | int]] = []
    candidates: list[dict[str, str | float | int]] = []
    for index, item in enumerate(data["queries"]):
        query = item["query"]
        relevant = {str(path): int(grade) for path, grade in item["relevant"].items()}
        results = search_vault(args.vault, query, max_results=5, mode=args.mode)
        ranked = [result.rel_path for result in results]
        grades = [relevant.get(path, 0) for path in ranked]
        ideal = sorted(relevant.values(), reverse=True)[:5]
        ndcg = _dcg(grades) / _dcg(ideal) if ideal and _dcg(ideal) else 0.0
        hit_positions = [rank for rank, path in enumerate(ranked, 1) if path in relevant]
        recall = len(set(ranked) & set(relevant)) / len(relevant) if relevant else 0.0
        mrr = 1 / hit_positions[0] if hit_positions else 0.0
        rows.append(
            {
                "mode": args.mode,
                "query_index": index,
                "language_group": query_groups.get(index, "all"),
                "query": query,
                "nDCG@5": ndcg,
                "Recall@5": recall,
                "MRR@5": mrr,
                "result_count": len(ranked),
                "top5_rel_paths": json.dumps(ranked, ensure_ascii=False),
            }
        )
        if args.candidate_output and args.mode == "reranked":
            candidate_paths = _reranker_candidate_paths(args.vault, query)
            candidates.append(
                {
                    "query_index": index,
                    "language_group": query_groups.get(index, "all"),
                    "query": query,
                    "candidate_count": len(candidate_paths),
                    "relevant_count": len(relevant),
                    "candidate_recall": (
                        len(candidate_paths & set(relevant)) / len(relevant) if relevant else 0.0
                    ),
                }
            )

    for output in (args.summary_output, args.per_query_output, args.candidate_output):
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
    with args.per_query_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grouped: dict[str, list[dict[str, str | float | int]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["language_group"])].append(row)
    grouped["all"] = rows
    summary_rows = []
    for group, group_rows in grouped.items():
        summary_rows.append(
            {
                "mode": args.mode,
                "language_group": group,
                "n": len(group_rows),
                "nDCG@5": sum(float(row["nDCG@5"]) for row in group_rows) / len(group_rows),
                "Recall@5": sum(float(row["Recall@5"]) for row in group_rows) / len(group_rows),
                "MRR@5": sum(float(row["MRR@5"]) for row in group_rows) / len(group_rows),
            }
        )
    with args.summary_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    if args.candidate_output:
        with args.candidate_output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "query_index",
                    "language_group",
                    "query",
                    "candidate_count",
                    "relevant_count",
                    "candidate_recall",
                ],
            )
            writer.writeheader()
            writer.writerows(candidates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
