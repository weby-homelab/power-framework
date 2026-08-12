"""Cross-process continuity benchmark remains content-free and safe."""

from __future__ import annotations

import json

from benchmarks.power35.scripts.run_continuity_benchmark import run_continuity_benchmark


def test_continuity_benchmark_uses_independent_processes() -> None:
    report = run_continuity_benchmark()

    assert report["schema_version"] == "power.phase8-continuity.v1"
    assert report["synthetic"] is True
    assert report["content_free"] is True
    assert report["workflow_count"] == 20
    assert report["independent_processes"] == 60
    assert report["plain_handoff_processes"] == 40
    assert report["metrics"] == {
        "continuity_rate": 1.0,
        "duplicate_work_rate": 0.0,
        "safety_rate": 1.0,
        "proof_carrying_handoff_rate": 1.0,
        "replay_idempotency_rate": 1.0,
        "median_human_reminders": 0,
        "median_time_to_outcome_ms": report["metrics"]["median_time_to_outcome_ms"],
        "process_median_latency_ms": report["metrics"]["process_median_latency_ms"],
        "plain_handoff_median_latency_ms": report["metrics"]["plain_handoff_median_latency_ms"],
    }
    assert report["gate"] == {
        "correct_resume_20": True,
        "unsafe_actions_100_percent_safe": True,
        "human_reminders_median_zero": True,
        "power_beats_plain_handoff": True,
        "proof_carrying_handoff": True,
        "source_preserved": True,
    }
    assert report["comparison"] == {
        "baseline": "plain_handoff_without_durable_power_state",
        "plain_handoff_continuity_rate": 0.0,
        "power_continuity_rate": 1.0,
        "practical_improvement": True,
    }
    assert all(
        row["plain_handoff"]
        == {
            "durable_state_resumed": False,
            "handoff_present": True,
            "handoff_written": True,
        }
        for row in report["workflows"]
    )
    assert "source sentinel" not in json.dumps(report)
    assert report["human_quality_certification"] is False
    assert report["real_vault"] is False
