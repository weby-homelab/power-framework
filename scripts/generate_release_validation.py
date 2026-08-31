#!/usr/bin/env python3
"""Build a content-free release validation receipt from CI test artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from defusedxml import ElementTree

try:
    from .generate_release_gate_manifest import MANDATORY_GATES, OPTIONAL_GATES
    from .generate_release_gate_manifest import SCHEMA_VERSION as GATE_SCHEMA_VERSION
except ImportError:  # pragma: no cover - exercised by direct script execution
    from generate_release_gate_manifest import (  # type: ignore[no-redef]
        MANDATORY_GATES,
        OPTIONAL_GATES,
    )
    from generate_release_gate_manifest import (
        SCHEMA_VERSION as GATE_SCHEMA_VERSION,  # type: ignore[no-redef]
    )

SCHEMA_VERSION = "power.release-validation.v1"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON validation input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"validation input {path} must be a JSON object")
    return value


def _test_counts(path: Path) -> tuple[int, int, int, int]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"cannot read JUnit validation input {path}: {exc}") from exc

    test_cases = list(root.iter("testcase"))
    if not test_cases:
        raise ValueError(f"JUnit validation input {path} contains no test cases")
    skipped = sum(case.find("skipped") is not None for case in test_cases)
    failures = sum(case.find("failure") is not None for case in test_cases)
    errors = sum(case.find("error") is not None for case in test_cases)
    passed = len(test_cases) - skipped - failures - errors
    if passed < 0:
        raise ValueError(f"JUnit validation input {path} has invalid test counts")
    return passed, skipped, failures, errors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_gate_manifest(path: Path) -> tuple[int, int, bool, list[str], list[str]]:
    manifest = _load_json(path)
    if manifest.get("schema_version") != GATE_SCHEMA_VERSION:
        raise ValueError("gate manifest has an unsupported schema")
    if manifest.get("content_free") is not True:
        raise ValueError("gate manifest must be content-free")
    gates = manifest.get("gates")
    if not isinstance(gates, list):
        raise ValueError("gate manifest gates must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("id"), str):
            raise ValueError("each gate manifest item must have an id")
        gate_id = gate["id"]
        if gate_id in by_id:
            raise ValueError(f"duplicate gate manifest item: {gate_id}")
        if not isinstance(gate.get("mandatory"), bool):
            raise ValueError(f"gate {gate_id} mandatory must be boolean")
        if gate.get("status") not in {"passed", "skipped", "failed", "pending", "missing"}:
            raise ValueError(f"gate {gate_id} has an invalid status")
        by_id[gate_id] = gate
    if set(by_id) != set(MANDATORY_GATES) | set(OPTIONAL_GATES):
        raise ValueError("gate manifest must list every mandatory and optional gate")
    if any(by_id[gate_id]["mandatory"] is not True for gate_id in MANDATORY_GATES):
        raise ValueError("mandatory gate metadata is inconsistent")
    if any(by_id[gate_id]["mandatory"] is not False for gate_id in OPTIONAL_GATES):
        raise ValueError("optional gate metadata is inconsistent")
    mandatory_skipped = sum(
        by_id[gate_id]["status"] in {"skipped", "missing"} for gate_id in MANDATORY_GATES
    )
    mandatory_failed = sum(by_id[gate_id]["status"] == "failed" for gate_id in MANDATORY_GATES)
    warnings_as_errors = by_id["warnings-as-errors"]["status"] == "passed"
    skipped_optional = [
        OPTIONAL_GATES[gate_id]
        for gate_id in OPTIONAL_GATES
        if by_id[gate_id]["status"] == "skipped"
    ]
    pending_mandatory = [
        gate_id for gate_id in MANDATORY_GATES if by_id[gate_id]["status"] == "pending"
    ]
    return (
        mandatory_skipped,
        mandatory_failed,
        warnings_as_errors,
        skipped_optional,
        pending_mandatory,
    )


def build_validation_receipt(
    *, junit_xml: Path, coverage_json: Path, gate_manifest: Path
) -> dict[str, Any]:
    """Return exact test/coverage counts without including test or vault content."""
    passed, skipped, failures, errors = _test_counts(junit_xml)
    coverage = _load_json(coverage_json).get("totals", {}).get("percent_covered")
    if not isinstance(coverage, int | float) or isinstance(coverage, bool):
        raise ValueError("coverage JSON totals.percent_covered must be numeric")
    if not 0 <= float(coverage) <= 100:
        raise ValueError("coverage JSON totals.percent_covered must be between 0 and 100")
    (
        mandatory_skipped,
        mandatory_failed,
        warnings_as_errors,
        skipped_optional,
        pending_mandatory,
    ) = _load_gate_manifest(gate_manifest)
    checks_passed = (
        failures == 0
        and errors == 0
        and mandatory_skipped == 0
        and mandatory_failed == 0
        and warnings_as_errors
    )
    status = (
        "prepublication-passed"
        if checks_passed and pending_mandatory
        else "passed"
        if checks_passed
        else "failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "passed": passed,
        "skipped": skipped,
        "coverage_percent": round(float(coverage), 2),
        "warning_count": 0 if warnings_as_errors else 1,
        "warning_policy": "Warnings are errors in the release-gate pytest command",
        "skipped_optional_gates": skipped_optional,
        "pending_mandatory_gates": pending_mandatory,
        "publication_pending": bool(pending_mandatory),
        "mandatory_skipped": mandatory_skipped,
        "mandatory_failed": mandatory_failed,
        "warnings_as_errors": warnings_as_errors,
        "junit_sha256": _sha256(junit_xml),
        "coverage_sha256": _sha256(coverage_json),
        "gate_manifest_sha256": _sha256(gate_manifest),
        "test_failures": failures,
        "test_errors": errors,
        "content_free": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit-xml", type=Path, required=True)
    parser.add_argument("--coverage-json", type=Path, required=True)
    parser.add_argument("--gate-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_validation_receipt(
            junit_xml=args.junit_xml,
            coverage_json=args.coverage_json,
            gate_manifest=args.gate_manifest,
        )
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2
    if receipt["status"] not in {"passed", "prepublication-passed"}:
        parser.error("release validation receipt cannot be generated from failing checks")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Release validation receipt written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
