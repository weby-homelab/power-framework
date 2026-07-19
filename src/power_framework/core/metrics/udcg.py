"""UDCG — Utility-Discounted Cumulative Gain (EACL 2026).

Standard retrieval metrics (MRR, nDCG) were designed for human recall lists and
do not capture *utility* for an LLM RAG reader: a perfect ordering of marginally
useful docs scores the same as a perfect ordering of highly useful docs, and a
list padded with irrelevant results is not penalized. UDCG fixes both:

    UDCG@k = sum_{i=1..k}  ( u_i / log2(i + 1) )

where ``u_i`` is the utility of the i-th retrieved result in [0, 1]
(1 = directly answers the query, 0 = irrelevant). The discount is the same
logarithmic position discount as DCG, but the gain term is a *utility* score
instead of a relevance grade, and there is no ideal-list normalization (the
utility ceiling is already bounded by the query's own rubric).

This makes UDCG reproducible and comparable across queries once a frozen ground
-truth rubric (``tests/fixtures/search_gt.json``) is used — fixing FP-6
("GT instability") from the v2.2.2 failure-pattern analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def udcg(
    utilities: Sequence[float],
    k: int | None = None,
    *,
    use_log2: bool = True,
) -> float:
    """Compute UDCG for a ranked list of per-result utilities in [0, 1].

    Args:
        utilities: Utility score u_i for each retrieved result, ordered by rank.
        k: Truncate the list at position ``k`` (default: whole list).
        use_log2: Use log2(i+1) discount (DCG-style). If False, uses linear
            (1/i) discount — rarely needed, kept for experimentation.

    Returns:
        The UDCG score (>= 0).
    """
    if not utilities:
        return 0.0
    if k is not None:
        utilities = list(utilities)[:k]

    total = 0.0
    for i, u in enumerate(utilities, start=1):
        discount = __import__("math").log2(i + 1) if use_log2 else float(i)
        total += float(u) / discount
    return total


def normalized_udcg(
    utilities: Sequence[float],
    k: int | None = None,
) -> float:
    """UDCG divided by the ideal UDCG (all utilities sorted descending).

    Unlike nDCG this does NOT require a separate ideal ranking of *relevant*
    docs — the ideal is simply the retrieved utilities sorted best-first, which
    is well-defined for any utility rubric and avoids the GT-instability that
    plagued nDCG (FP-6).
    """
    if not utilities:
        return 0.0
    if k is not None:
        utilities = list(utilities)[:k]
    ideal = sorted(utilities, reverse=True)
    denom = udcg(ideal, k=k)
    if denom <= 0.0:
        return 0.0
    return udcg(utilities, k=k) / denom


def utilities_from_relevance(
    relevance: Sequence[int],
    max_relevance: int = 3,
) -> list[float]:
    """Map graded relevance (e.g. 0-3) to a bounded utility score in [0, 1].

    The mapping is monotonic but compressed (sqrt) so that the gap between
    "perfect" (3) and "good" (2) is smaller than the gap between "good" and
    "irrelevant" (0) — matching how an LLM reader actually benefits.
    """
    import math

    return [math.sqrt(max(0, min(r, max_relevance)) / max_relevance) for r in relevance]
