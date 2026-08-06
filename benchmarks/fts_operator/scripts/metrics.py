"""Retrieval quality metrics for the FTS operator A/B benchmark.

All metrics are computed per query from a ranked document-id list and the
frozen graded relevance judgments. Distractors are excluded at qrels load time
(see ``ground_truth.load_qrels``), so they are never counted as hits.
"""

from __future__ import annotations

import math
from typing import Any

GRADED_GAIN_BASE = 2


def _gains(relevance: int) -> float:
    return max(0.0, float(GRADED_GAIN_BASE**relevance - 1.0))


def ndcg_at_k(retrieved: list[str], relevant: dict[str, int], k: int) -> float:
    """Graded nDCG@k (gains 2^rel - 1, log2 rank discount)."""
    top = retrieved[:k]
    if not top:
        return 0.0
    dcg = sum(_gains(relevant.get(doc, 0)) / math.log2(rank + 2) for rank, doc in enumerate(top))
    ideal = sorted((_gains(rel) for rel in relevant.values()), reverse=True)[:k]
    idcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(ideal))
    if idcg <= 0.0:
        return 0.0
    return dcg / idcg


def recall_at_k(retrieved: list[str], relevant: dict[str, int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = len(set(retrieved[:k]) & set(relevant))
    return hits / len(relevant)


def precision_at_k(retrieved: list[str], relevant: dict[str, int], k: int) -> float:
    top = retrieved[:k]
    if not top:
        return 0.0
    return len(set(top) & set(relevant)) / len(top)


def mrr_at_k(retrieved: list[str], relevant: dict[str, int], k: int) -> float:
    for rank, doc in enumerate(retrieved[:k], start=1):
        if doc in relevant:
            return 1.0 / rank
    return 0.0


def hit_rate_at_k(retrieved: list[str], relevant: dict[str, int], k: int) -> float:
    """1.0 if any relevant document appears in the top-k, else 0.0."""
    if not relevant:
        return 0.0
    return 1.0 if set(retrieved[:k]) & set(relevant) else 0.0


def first_relevant_rank(retrieved: list[str], relevant: dict[str, int]) -> int | None:
    """1-based rank of the first relevant document, or None."""
    for rank, doc in enumerate(retrieved, start=1):
        if doc in relevant:
            return rank
    return None


def relevant_hits_at_k(retrieved: list[str], relevant: dict[str, int], k: int) -> int:
    return len(set(retrieved[:k]) & set(relevant))


def compute_query_metrics(
    retrieved: list[str],
    relevant: dict[str, int],
    k_values: tuple[int, ...] = (5, 10),
) -> dict[str, float | int]:
    """All metrics for one query over one variant."""
    metrics: dict[str, float | int] = {"result_count": len(retrieved)}
    for k in k_values:
        prefix = f"@{k}"
        metrics[f"ndcg{prefix}"] = ndcg_at_k(retrieved, relevant, k)
        metrics[f"recall{prefix}"] = recall_at_k(retrieved, relevant, k)
        metrics[f"precision{prefix}"] = precision_at_k(retrieved, relevant, k)
        metrics[f"mrr{prefix}"] = mrr_at_k(retrieved, relevant, k)
        metrics[f"hit_rate{prefix}"] = hit_rate_at_k(retrieved, relevant, k)
        metrics[f"relevant_hits{prefix}"] = relevant_hits_at_k(retrieved, relevant, k)
    first = first_relevant_rank(retrieved, relevant)
    metrics["first_relevant_rank"] = float(first) if first is not None else 0.0
    metrics["zero_result"] = 1.0 if not retrieved else 0.0
    return metrics


def metric_names(k_values: tuple[int, ...] = (5, 10)) -> list[str]:
    names: list[str] = []
    for k in k_values:
        prefix = f"@{k}"
        names.extend(
            [
                f"ndcg{prefix}",
                f"recall{prefix}",
                f"precision{prefix}",
                f"mrr{prefix}",
                f"hit_rate{prefix}",
                f"relevant_hits{prefix}",
            ]
        )
    names.extend(["first_relevant_rank", "zero_result", "result_count"])
    return names


def aggregate(values: list[float]) -> dict[str, float]:
    """Mean and median of per-query values (empty -> 0.0)."""
    if not values:
        return {"mean": 0.0, "median": 0.0}
    ordered = sorted(values)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
    return {"mean": sum(values) / n, "median": median}


def summarize_variant(
    per_query: list[dict[str, Any]],
    metric: str,
) -> dict[str, Any]:
    """Aggregate one metric over a variant's per-query rows."""
    values = [float(row[metric]) for row in per_query]
    summary = aggregate(values)
    return {
        "metric": metric,
        "n": len(values),
        "mean": summary["mean"],
        "median": summary["median"],
        "zero_count": sum(1 for value in values if value == 0.0),
    }
