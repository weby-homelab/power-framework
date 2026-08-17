from __future__ import annotations

import json
import math
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

SEMANTIC_GT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "semantic_gt.json"
)
SEMANTIC_GT_RESOURCE = files("power_framework").joinpath("data", "semantic_gt.json")


def _load_semantic_gt(path: Path | None = None) -> dict[str, dict[str, int]]:
    """Load the packaged GT, or an explicit fixture for a governed evaluation."""
    if path is not None:
        raw_data = path.read_text(encoding="utf-8")
    else:
        try:
            raw_data = SEMANTIC_GT_RESOURCE.read_text(encoding="utf-8")
        except FileNotFoundError:
            # Editable source checkouts before the package data target is built
            # retain the historical fixture as a development fallback.
            raw_data = SEMANTIC_GT_PATH.read_text(encoding="utf-8")
    data = json.loads(raw_data)
    qrels: dict[str, dict[str, int]] = {}
    for entry in data["queries"]:
        qrels[entry["query"]] = entry["relevant"]
    return qrels


def dcg_at_k(relevance: Sequence[int], k: int | None = None) -> float:
    if not relevance:
        return 0.0
    if k is not None:
        relevance = list(relevance)[:k]
    total = 0.0
    for i, rel in enumerate(relevance, start=1):
        total += (2.0**rel - 1.0) / math.log2(i + 1)
    return total


def ndcg_at_k(
    relevance: Sequence[int],
    k: int | None = None,
) -> float:
    if not relevance:
        return 0.0
    if k is not None:
        relevance = list(relevance)[:k]
    ideal = sorted(relevance, reverse=True)
    actual_dcg = dcg_at_k(relevance, k=k)
    ideal_dcg = dcg_at_k(ideal, k=k)
    return 0.0 if ideal_dcg <= 0.0 else actual_dcg / ideal_dcg


def compute_ndcg(
    qrels: dict[str, dict[str, int]],
    run: dict[str, dict[str, float]],
    k: int = 5,
) -> dict[str, float]:
    per_query: list[float] = []
    for query, rel_docs in qrels.items():
        ranked = list(run.get(query, {}).keys())[:k]
        grades = [rel_docs.get(doc, 0) for doc in ranked]
        per_query.append(ndcg_at_k(grades, k=k))
    mean_ndcg = sum(per_query) / len(per_query) if per_query else 0.0
    return {
        f"ndcg@{k}": mean_ndcg,
    }


def compute_semantic_udcg(
    run: dict[str, dict[str, float]],
    k: int = 5,
    gt_path: Path | None = None,
) -> dict[str, float]:
    qrels = _load_semantic_gt(gt_path)
    metrics = compute_ndcg(qrels, run, k=k)
    ndcg_key = f"ndcg@{k}"
    return {
        ndcg_key: metrics[ndcg_key],
        f"udcg@{k}": metrics[ndcg_key],
    }
