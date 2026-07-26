#!/usr/bin/env python3
"""Compare pytest JUnit XML failures without hand-counted Markdown tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from defusedxml import ElementTree


def failed_nodeids(path: Path) -> set[str]:
    """Return pytest node identifiers with an error or failure in a JUnit report."""
    root = ElementTree.parse(path).getroot()
    failed: set[str] = set()
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        failed.add(f"{classname}::{name}" if classname else name)
    return failed


def totals(path: Path) -> dict[str, int]:
    """Sum test-result attributes across JUnit testsuites."""
    root = ElementTree.parse(path).getroot()
    values = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in root.iter("testsuite"):
        for key in values:
            values[key] += int(suite.attrib.get(key, "0"))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--pr", dest="pr_report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline = failed_nodeids(args.baseline)
    pr = failed_nodeids(args.pr_report)
    comparison = {
        "baseline_totals": totals(args.baseline),
        "pr_totals": totals(args.pr_report),
        "baseline_failed_nodeids": sorted(baseline),
        "pr_failed_nodeids": sorted(pr),
        "fixed_failures": sorted(baseline - pr),
        "new_failures": sorted(pr - baseline),
        "common_failures": sorted(baseline & pr),
    }
    json_path = args.output_dir / "pytest-baseline-comparison.json"
    json_path.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")

    def section(name: str, values: list[str]) -> list[str]:
        entries = [f"- `{item}`" for item in values] or ["- None"]
        return [f"## {name}", "", *entries, ""]

    markdown = ["# Pytest baseline comparison", ""]
    markdown.extend(section("Baseline failed nodeids", comparison["baseline_failed_nodeids"]))
    markdown.extend(section("PR failed nodeids", comparison["pr_failed_nodeids"]))
    markdown.extend(section("Fixed failures", comparison["fixed_failures"]))
    markdown.extend(section("New failures", comparison["new_failures"]))
    markdown.extend(section("Common failures", comparison["common_failures"]))
    (args.output_dir / "pytest-baseline-comparison.md").write_text(
        "\n".join(markdown), encoding="utf-8"
    )
    known = ["# Known baseline failures", ""]
    known.extend(f"- `{item}`" for item in comparison["common_failures"])
    if not comparison["common_failures"]:
        known.append("- None")
    (args.output_dir / "known-baseline-failures.md").write_text(
        "\n".join(known) + "\n", encoding="utf-8"
    )
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
