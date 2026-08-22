"""Fail a CI gate when the mandatory hermetic neural contract is skipped."""

from __future__ import annotations

import argparse
from pathlib import Path

from defusedxml import ElementTree


def verify_report(path: Path) -> tuple[int, int]:
    """Return ``(tests, skipped)`` and reject an empty or unhealthy contract run."""

    root = ElementTree.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    if tests == 0:
        raise ValueError("mandatory neural contract collected zero tests")
    if failures or errors:
        raise ValueError(
            f"mandatory neural contract has {failures} failure(s) and {errors} error(s)"
        )
    if skipped:
        raise ValueError(f"mandatory neural contract skipped {skipped} test(s)")
    return tests, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", type=Path)
    args = parser.parse_args()
    tests, skipped = verify_report(args.junit_xml)
    print(f"mandatory hermetic neural contract passed: tests={tests}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
