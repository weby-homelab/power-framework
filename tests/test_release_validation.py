"""Tests for the content-free CI validation receipt."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.generate_release_gate_manifest import (
    MANDATORY_GATES,
    OPTIONAL_GATES,
    build_gate_manifest,
)
from scripts.generate_release_validation import build_validation_receipt

if TYPE_CHECKING:
    from pathlib import Path


def _inputs(tmp_path: Path, *, failing: bool = False) -> tuple[Path, Path]:
    failure = "<failure message='failed'/>" if failing else ""
    junit = tmp_path / "junit.xml"
    junit.write_text(
        "<testsuite>"
        f"<testcase name='passed'/><testcase name='skipped'><skipped/></testcase>"
        f"<testcase name='failed'>{failure}</testcase>"
        "</testsuite>",
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 81.66}}), encoding="utf-8")
    return junit, coverage


def _gate_manifest(tmp_path: Path, *, skip_mandatory: bool = False) -> Path:
    path = tmp_path / "gates.json"
    manifest = build_gate_manifest(
        passed_mandatory=set(MANDATORY_GATES) - ({"mypy"} if skip_mandatory else set()),
        skipped_mandatory={"mypy"} if skip_mandatory else set(),
        failed_mandatory=set(),
        passed_optional=set(),
        skipped_optional=set(OPTIONAL_GATES),
    )
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_validation_receipt_uses_junit_and_coverage_counts(tmp_path: Path) -> None:
    junit, coverage = _inputs(tmp_path)
    gates = _gate_manifest(tmp_path)

    receipt = build_validation_receipt(junit_xml=junit, coverage_json=coverage, gate_manifest=gates)

    assert receipt["schema_version"] == "power.release-validation.v1"
    assert receipt["status"] == "passed"
    assert receipt["passed"] == 2
    assert receipt["skipped"] == 1
    assert receipt["coverage_percent"] == 81.66
    assert receipt["test_failures"] == 0
    assert receipt["test_errors"] == 0
    assert receipt["content_free"] is True
    assert receipt["mandatory_skipped"] == 0
    assert receipt["warnings_as_errors"] is True
    assert len(receipt["junit_sha256"]) == 64
    assert len(receipt["gate_manifest_sha256"]) == 64


def test_validation_receipt_marks_failed_tests(tmp_path: Path) -> None:
    junit, coverage = _inputs(tmp_path, failing=True)
    gates = _gate_manifest(tmp_path)

    receipt = build_validation_receipt(junit_xml=junit, coverage_json=coverage, gate_manifest=gates)

    assert receipt["status"] == "failed"
    assert receipt["test_failures"] == 1


def test_validation_receipt_rejects_missing_test_cases(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text("<testsuite />", encoding="utf-8")
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 80}}), encoding="utf-8")
    gates = _gate_manifest(tmp_path)

    with pytest.raises(ValueError, match="contains no test cases"):
        build_validation_receipt(junit_xml=junit, coverage_json=coverage, gate_manifest=gates)


def test_validation_receipt_counts_missing_mandatory_gate(tmp_path: Path) -> None:
    junit, coverage = _inputs(tmp_path)
    gates = _gate_manifest(tmp_path, skip_mandatory=True)

    receipt = build_validation_receipt(junit_xml=junit, coverage_json=coverage, gate_manifest=gates)

    assert receipt["status"] == "failed"
    assert receipt["mandatory_skipped"] == 1
