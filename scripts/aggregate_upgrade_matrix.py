#!/usr/bin/env python3
"""Aggregate content-free upgrade matrix reports from all supported runners."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_PLATFORMS = ("linux", "macos", "windows")
REPORT_SCHEMA = "power.upgrade-matrix.v1"
AGGREGATE_SCHEMA = "power.upgrade-matrix.aggregate.v1"
INTERRUPTED_GATE_KEYS = (
    "all_checkpoints_pass",
    "source_preserved",
    "restart_recovered",
    "stale_build_rows_cleared",
    "no_data_loss",
)


def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate and aggregate exactly one successful report per supported OS."""
    if len(reports) != len(EXPECTED_PLATFORMS):
        raise ValueError(
            f"expected {len(EXPECTED_PLATFORMS)} platform reports, received {len(reports)}"
        )

    by_platform: dict[str, dict[str, Any]] = {}
    from_version: str | None = None
    to_version: str | None = None
    for report in reports:
        if report.get("schema_version") != REPORT_SCHEMA:
            raise ValueError("unexpected upgrade matrix schema")
        if report.get("source_content") != "not captured":
            raise ValueError("upgrade matrix report must not capture source content")
        if report.get("interrupted_upgrade", {}).get("raw_content_in_report") is not False:
            raise ValueError("interrupted upgrade report must remain content-free")
        if report.get("interrupted_upgrade", {}).get("physical_3_4_5_runtime") is not False:
            raise ValueError("physical 3.4.5 runtime must not be inferred from synthetic evidence")
        platform = report.get("current_runner", {}).get("platform")
        if platform not in EXPECTED_PLATFORMS:
            raise ValueError(f"unsupported or missing runner platform: {platform!r}")
        if platform in by_platform:
            raise ValueError(f"duplicate upgrade matrix report for {platform}")
        if report.get("current_runner", {}).get("status") != "pass":
            raise ValueError(f"current runner did not pass for {platform}")
        if report.get("release_gate", {}).get("local_invariants") is not True:
            raise ValueError(f"local invariants did not pass for {platform}")
        interrupted_gate = report.get("interrupted_upgrade", {}).get("gate", {})
        if any(interrupted_gate.get(key) is not True for key in INTERRUPTED_GATE_KEYS):
            raise ValueError(f"interrupted upgrade gate did not pass for {platform}")
        if from_version is None:
            from_version = str(report.get("from_version"))
            to_version = str(report.get("to_version"))
        elif (report.get("from_version"), report.get("to_version")) != (
            from_version,
            to_version,
        ):
            raise ValueError("upgrade matrix reports use different version bounds")
        by_platform[platform] = report

    missing = sorted(set(EXPECTED_PLATFORMS) - set(by_platform))
    if missing:
        raise ValueError(f"missing upgrade matrix platforms: {', '.join(missing)}")

    return {
        "schema_version": AGGREGATE_SCHEMA,
        "from_version": from_version,
        "to_version": to_version,
        "content_free": True,
        "raw_content_in_report": False,
        "platforms": dict.fromkeys(EXPECTED_PLATFORMS, "executed"),
        "reports": [
            {
                "platform": platform,
                "status": "pass",
                "local_invariants": True,
                "interrupted_upgrade": dict.fromkeys(INTERRUPTED_GATE_KEYS, True),
                "physical_3_4_5_runtime": False,
            }
            for platform in EXPECTED_PLATFORMS
        ],
        "release_gate": {
            "local_invariants": True,
            "all_platforms_executed": True,
            "interrupted_upgrade": True,
            "physical_3_4_5_runtime": False,
            "publish_ready": False,
            "reason": "clean tag, physical 3.4.5 compatibility, and remote readback remain separate release gates",
        },
    }


def _load_reports(input_dir: Path) -> list[dict[str, Any]]:
    paths = sorted(input_dir.glob("power-upgrade-matrix-*.json"))
    if not paths:
        raise ValueError(f"no platform reports found in {input_dir}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require-all-platforms",
        action="store_true",
        required=True,
        help="require exactly one passing Linux, macOS, and Windows report",
    )
    args = parser.parse_args(argv)
    try:
        report = aggregate_reports(_load_reports(args.input_dir))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Aggregated {len(EXPECTED_PLATFORMS)} upgrade matrix reports into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
