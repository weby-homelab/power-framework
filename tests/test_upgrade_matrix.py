"""Upgrade matrix runner contracts."""

from __future__ import annotations

import pytest

from scripts.aggregate_upgrade_matrix import aggregate_reports
from scripts.verify_upgrade_matrix import build_matrix


def test_local_upgrade_matrix_proves_safe_boundaries() -> None:
    report = build_matrix()

    assert report["schema_version"] == "power.upgrade-matrix.v1"
    assert report["from_version"] == "3.6.7"
    assert report["to_version"] == "3.7.2"
    assert report["current_runner"]["status"] == "pass"
    assert report["current_runner"]["checks"]["free_space_sufficient"] is True
    assert report["current_runner"]["preflight"]["migration_preview"] == "pass"
    assert report["current_runner"]["preflight"]["apply_available"] is False
    assert report["release_gate"]["local_invariants"] is True
    assert report["release_gate"]["publish_ready"] is False
    assert report["source_content"] == "not captured"
    interrupted = report["interrupted_upgrade"]
    assert interrupted["schema_version"] == "power.upgrade-interrupted-matrix.v1"
    assert interrupted["physical_previous_runtime"] is False
    assert interrupted["gate"] == {
        "all_checkpoints_pass": True,
        "source_preserved": True,
        "restart_recovered": True,
        "stale_build_rows_cleared": True,
        "no_data_loss": True,
    }
    assert {row["checkpoint"] for row in interrupted["checkpoints"]} == {
        "before_move",
        "after_move",
        "after_pointer",
    }
    assert all(row["status"] == "pass" for row in interrupted["checkpoints"])
    assert all(row["active_pointer_consistent"] for row in interrupted["checkpoints"])
    assert all(row["stale_build_rows_cleared"] for row in interrupted["checkpoints"])
    assert all(row["data_loss"] is False for row in interrupted["checkpoints"])
    assert interrupted["raw_content_in_report"] is False


def test_unexecuted_platforms_are_not_silently_green() -> None:
    report = build_matrix()

    assert report["release_gate"]["all_platforms_executed"] is True
    assert report["supported_platforms"] == ["linux"]
    assert report["deferred_platforms"] == ["macos", "windows"]
    assert "unscheduled" in report["release_gate"]["reason"]
    assert "tag-bound" in report["release_gate"]["reason"]


def _synthetic_platform_report(platform: str) -> dict[str, object]:
    """Return the content-free shape emitted by one supported runner."""
    gate = {
        "all_checkpoints_pass": True,
        "source_preserved": True,
        "restart_recovered": True,
        "stale_build_rows_cleared": True,
        "no_data_loss": True,
    }
    return {
        "schema_version": "power.upgrade-matrix.v1",
        "from_version": "3.6.7",
        "to_version": "3.7.2",
        "source_content": "not captured",
        "current_runner": {"platform": platform, "status": "pass"},
        "interrupted_upgrade": {
            "gate": gate,
            "raw_content_in_report": False,
            "physical_previous_runtime": False,
        },
        "release_gate": {"local_invariants": True},
    }


def test_upgrade_matrix_aggregation_requires_supported_platforms() -> None:
    report = aggregate_reports([_synthetic_platform_report("linux")])

    assert report["schema_version"] == "power.upgrade-matrix.aggregate.v1"
    assert report["supported_platforms"] == ["linux"]
    assert report["deferred_platforms"] == ["macos", "windows"]
    assert report["platforms"] == {"linux": "executed"}
    assert report["release_gate"]["all_platforms_executed"] is True
    assert report["release_gate"]["physical_previous_runtime"] is False
    assert "unscheduled" in report["release_gate"]["reason"]
    assert report["raw_content_in_report"] is False


def test_upgrade_matrix_aggregation_rejects_duplicate_platform() -> None:
    reports = [_synthetic_platform_report(platform) for platform in ("linux", "linux")]

    with pytest.raises(ValueError, match="duplicate"):
        aggregate_reports(reports, expected_platforms=("linux", "macos"))
