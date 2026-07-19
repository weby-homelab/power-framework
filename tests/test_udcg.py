"""Tests for the UDCG metric (EACL 2026) used to evaluate RAG retrieval utility."""

from __future__ import annotations

import json
from pathlib import Path

from power_framework.core.metrics.udcg import (
    normalized_udcg,
    udcg,
    utilities_from_relevance,
)

FIXTURE = Path(__file__).parent / "fixtures" / "search_gt.json"


def test_udcg_monotonic_in_utility() -> None:
    assert udcg([1.0, 1.0, 1.0]) > udcg([1.0, 0.0, 0.0])


def test_udcg_position_discount() -> None:
    # A highly useful doc at rank 2 scores less than the same doc at rank 1.
    assert udcg([0.0, 1.0]) < udcg([1.0, 0.0])


def test_udcg_empty() -> None:
    assert udcg([]) == 0.0


def test_normalized_udcg_perfect_ranking() -> None:
    utils = [1.0, 0.6, 0.3]
    assert normalized_udcg(utils) == 1.0


def test_normalized_udcg_reversed() -> None:
    utils = [0.3, 0.6, 1.0]
    n = normalized_udcg(utils)
    assert 0.0 < n < 1.0


def test_utilities_from_relevance_bounds() -> None:
    utils = utilities_from_relevance([0, 1, 2, 3])
    assert utils[0] == 0.0
    assert utils[-1] == 1.0
    # sqrt compression: gap 2->3 smaller than 0->1
    assert (utils[3] - utils[2]) < (utils[1] - utils[0])


def test_frozen_gt_fixture_loads() -> None:
    assert FIXTURE.exists(), "frozen GT fixture must exist (FP-6 fix)"
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "queries" in data
    for group in ("GT-LEXICAL", "GT-SEMANTIC", "GT-RAG"):
        assert group in data["queries"], f"missing GT group {group}"
        assert len(data["queries"][group]) >= 1
