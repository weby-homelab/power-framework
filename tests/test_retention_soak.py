"""Retention policies remain bounded, explicit, and source-safe."""

from __future__ import annotations

import json
import re

from scripts.retention_soak import run_retention_soak


def test_retention_soak_emits_exact_manifest_and_restores_newest_backup() -> None:
    report = run_retention_soak()

    assert report["schema_version"] == "power.retention-soak.v1"
    assert report["content_free"] is True
    assert report["preview"]["candidate_count"] == 12
    assert report["preview"]["prune_count"] == 8
    assert report["preview"]["kept_count"] == 4
    assert re.fullmatch(r"[0-9a-f]{64}", report["preview"]["prune_manifest_sha256"])
    assert report["apply"]["removed_count"] == 8
    assert report["apply"]["remaining_count"] == 4
    assert re.fullmatch(r"[0-9a-f]{64}", report["apply"]["removed_manifest_sha256"])
    assert report["restore"]["status"] == "ok"
    assert report["bounded_growth"] == {
        "cycles": 20,
        "max_retained": 4,
        "final_retained": 4,
        "within_policy": True,
    }
    assert report["source_preserved"] is True
    assert report["control_preserved"] is True
    assert report["raw_content_in_report"] is False
    assert "fixture revision" not in json.dumps(report)
