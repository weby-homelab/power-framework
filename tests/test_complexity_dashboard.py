"""Complexity budget report is deterministic and explicit about unmet gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.complexity_dashboard import build_report


def test_complexity_dashboard_reports_frozen_metrics() -> None:
    report = build_report(Path(__file__).resolve().parents[1])

    assert report["schema_version"] == "power.complexity-dashboard.v1"
    assert report["baseline_revision"] == "v3.4.5"
    assert report["current"]["cli_commands"] == 25
    assert report["current"]["mcp_tools"] == 20
    assert report["canonical_workflows"] <= 7
    assert report["budget"]["duplicate_skill_sources_zero"] is True
    assert report["budget"]["negative_net_core_complexity"] is True
    assert report["budget"]["base_dependency_bytes_reduced_50_percent"] is True


def test_complexity_dashboard_cli_require_budget_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/complexity_dashboard.py",
            "--baseline-revision",
            "v3.4.5",
            "--require-budget",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_core_import_does_not_eagerly_load_experimental_adapters() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import power_framework; import power_framework.core; "
                "assert 'power_framework.experimental.embeddings' not in sys.modules; "
                "assert 'power_framework.experimental.relations' not in sys.modules"
            ),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
