"""Paired bootstrap confidence intervals for the FTS operator A/B benchmark.

The OR-vs-AND experiment is paired: every query runs under both operators.
Per-query deltas ``delta = AND - OR`` are resampled with replacement
(10,000 resamples, fixed seed) to produce a 95% CI for the mean delta.
"""

from __future__ import annotations

import random
import statistics
from typing import Any

DEFAULT_RESAMPLES = 10_000
DEFAULT_SEED = 20260801
CI_LEVEL = 0.95


def paired_deltas(and_scores: list[float], or_scores: list[float]) -> list[float]:
    """Per-query deltas AND - OR (strict pairing by list position)."""
    if len(and_scores) != len(or_scores):
        raise ValueError("paired bootstrap requires equal per-query sample sizes")
    return [and_score - or_score for and_score, or_score in zip(and_scores, or_scores, strict=True)]


def paired_bootstrap_ci(
    and_scores: list[float],
    or_scores: list[float],
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    ci: float = CI_LEVEL,
) -> dict[str, Any]:
    """Paired bootstrap 95% CI for the mean delta (AND - OR).

    Returns ``mean_delta``, ``ci_lower``, ``ci_upper`` and the sample size.
    With an empty sample the CI is ``[None, None]`` — the caller must then
    state that there is insufficient sample size instead of claiming
    significance.
    """
    deltas = paired_deltas(and_scores, or_scores)
    n = len(deltas)
    if n == 0:
        return {
            "mean_delta": 0.0,
            "ci_lower": None,
            "ci_upper": None,
            "n": 0,
            "n_resamples": n_resamples,
            "ci_level": ci,
            "seed": seed,
        }
    # Deterministic resampling is intentional; this is not cryptographic use.
    rng = random.Random(seed)  # noqa: S311
    boot_means: list[float] = []
    for _ in range(n_resamples):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        boot_means.append(statistics.fmean(sample))
    boot_means.sort()
    tail = int(n_resamples * (1.0 - ci) / 2.0)
    return {
        "mean_delta": statistics.fmean(deltas),
        "ci_lower": boot_means[tail],
        "ci_upper": boot_means[n_resamples - tail - 1],
        "n": n,
        "n_resamples": n_resamples,
        "ci_level": ci,
        "seed": seed,
    }


def win_tie_counts(
    and_scores: list[float],
    or_scores: list[float],
    epsilon: float = 1e-9,
) -> dict[str, int]:
    """Count AND wins, OR wins and ties for one metric over paired rows."""
    and_wins = 0
    or_wins = 0
    ties = 0
    for and_score, or_score in zip(and_scores, or_scores, strict=True):
        if abs(and_score - or_score) <= epsilon:
            ties += 1
        elif and_score > or_score:
            and_wins += 1
        else:
            or_wins += 1
    return {"and_wins": and_wins, "or_wins": or_wins, "ties": ties}
