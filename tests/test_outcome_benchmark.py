"""Synthetic Phase 8 benchmark stays content-free and technically honest."""

from __future__ import annotations

import json

from benchmarks.power35.scripts.run_outcome_benchmark import run_benchmark
from power_framework.core import __version__


def test_outcome_benchmark_compares_twenty_workflows_without_raw_content() -> None:
    report = run_benchmark()

    assert report["schema_version"] == "power.phase8-outcome.v2"
    assert report["release"] == __version__
    assert len(report["source"]["commit"]) == 40
    assert len(report["source"]["tree"]) == 40
    assert len(report["source"]["worktree_sha256"]) == 64
    assert report["synthetic"] is True
    assert report["content_free"] is True
    assert report["workflow_count"] == 20
    assert report["comparison"]["practical_improvement"] is True
    assert report["gate"] == {
        "fresh_agent_completion": 1.0,
        "median_human_reminders": 0,
        "safety_invariants_100": True,
        "technical_continuity_20": True,
        "blocked_workflow_abstention": True,
        "false_premise_abstention": True,
        "stale_state_filter": True,
    }
    assert report["comparison"]["evidence_recall"] == {"power": 0.75, "no_power": 0.0}
    assert report["comparison"]["evidence_use"] == {"power": 0.75, "no_power": 0.0}
    assert report["comparison"]["false_premise_cases"] == 5
    assert report["comparison"]["false_premise_abstention"] is True
    assert report["comparison"]["stale_state_cases"] == 1
    assert report["comparison"]["stale_state_filter"] is True
    assert report["retrieval_profiles"]["auto"]["fallback_to_fts_rate"] == 1.0
    assert report["retrieval_profiles"]["semantic"]["status"] == "not_evaluated"
    assert report["feedback_reuse"]["measured"] is False
    assert report["bilingual_strata"]["en"]["workflow_count"] == 10
    assert report["bilingual_strata"]["uk"]["workflow_count"] == 10
    assert report["blind_scoring"] is False
    assert report["bootstrap_context_tokens"]["measured"] is False
    assert report["resources"]["power"]["median_latency_ms"] >= 0
    assert "Declared fixture fact" not in json.dumps(report, ensure_ascii=False)
    assert "requested premise" not in json.dumps(report, ensure_ascii=False)
    assert report["human_quality_certification"] is False
    assert report["real_vault"] is False
