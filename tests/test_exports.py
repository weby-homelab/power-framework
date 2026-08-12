"""Compatibility tests for package-level lazy exports."""

from __future__ import annotations

import power_framework
import power_framework.core as core


def test_top_level_lazy_exports_resolve() -> None:
    for name in ("cli_main", "format_relation_suggestions", "suggest_related"):
        assert name in power_framework.__all__
        assert getattr(power_framework, name) is not None


def test_core_lazy_exports_resolve() -> None:
    names = (
        "cli_main",
        "EmbeddingManager",
        "QueryExpander",
        "KnowledgeGraph",
        "RelationSuggestion",
        "format_relation_suggestions",
        "suggest_related",
        "suggest_related_semantic",
        "RerankerManager",
        "TYPE_HALF_LIFE_DAYS",
        "ContentDedupDetector",
        "ContradictionDetector",
        "FreshnessScorer",
        "LinkRotChecker",
        "UsageTracker",
    )
    for name in names:
        assert name in core.__all__
        assert getattr(core, name) is not None
