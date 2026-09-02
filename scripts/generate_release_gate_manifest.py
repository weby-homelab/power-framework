#!/usr/bin/env python3
"""Emit the content-free gate inventory used by the 3.7.x release receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "power.release-gates.v1"
MANDATORY_GATES = (
    "locked-dependencies",
    "ruff-check",
    "ruff-format",
    "mypy",
    "doc-drift",
    "complexity-budget",
    "mkdocs-strict",
    "full-pytest",
    "warnings-as-errors",
    "maintenance-faults",
    "phase8-technical",
    "retention-soak",
    "profile-a-mcp-stdio",
    "profile-b-web-acceptance",
    "web-semantic-acceptance",
    "web-rerank-acceptance",
    "public-release-readback",
)
OPTIONAL_GATES = {
    "real-vault-quality": "real-vault neural/quality evaluation",
    "deferred-macos-windows": (
        "macOS and Windows support deferred without a scheduled release target for 3.7.11"
    ),
    "remote-release-readback": "remote release readback",
}


def build_gate_manifest(
    *,
    passed_mandatory: set[str],
    skipped_mandatory: set[str],
    failed_mandatory: set[str],
    pending_mandatory: set[str] | None = None,
    passed_optional: set[str],
    skipped_optional: set[str],
) -> dict[str, Any]:
    """Build a complete gate inventory; unfinished mandatory gates stay pending."""
    known_mandatory = set(MANDATORY_GATES)
    known_optional = set(OPTIONAL_GATES)
    pending = pending_mandatory or set()
    if not passed_mandatory <= known_mandatory:
        raise ValueError("unknown mandatory gate")
    if not skipped_mandatory <= known_mandatory:
        raise ValueError("unknown skipped mandatory gate")
    if not failed_mandatory <= known_mandatory:
        raise ValueError("unknown failed mandatory gate")
    if not pending <= known_mandatory:
        raise ValueError("unknown pending mandatory gate")
    if not passed_optional <= known_optional or not skipped_optional <= known_optional:
        raise ValueError("unknown optional gate")
    if (
        passed_mandatory & skipped_mandatory
        or passed_mandatory & failed_mandatory
        or passed_mandatory & pending
    ):
        raise ValueError("mandatory gate has conflicting statuses")
    if skipped_mandatory & failed_mandatory or skipped_mandatory & pending:
        raise ValueError("mandatory gate has conflicting statuses")
    if failed_mandatory & pending:
        raise ValueError("mandatory gate is both failed and pending")
    if passed_optional & skipped_optional:
        raise ValueError("optional gate has conflicting statuses")

    gates: list[dict[str, object]] = []
    for gate_id in MANDATORY_GATES:
        status = (
            "passed"
            if gate_id in passed_mandatory
            else "skipped"
            if gate_id in skipped_mandatory
            else "failed"
            if gate_id in failed_mandatory
            else "pending"
            if gate_id in pending
            else "missing"
        )
        gates.append({"id": gate_id, "mandatory": True, "status": status})
    for gate_id in OPTIONAL_GATES:
        status = "passed" if gate_id in passed_optional else "skipped"
        gates.append({"id": gate_id, "mandatory": False, "status": status})
    return {
        "schema_version": SCHEMA_VERSION,
        "content_free": True,
        "gates": gates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--passed-mandatory", action="append", default=[])
    parser.add_argument("--skipped-mandatory", action="append", default=[])
    parser.add_argument("--failed-mandatory", action="append", default=[])
    parser.add_argument("--pending-mandatory", action="append", default=[])
    parser.add_argument("--passed-optional", action="append", default=[])
    parser.add_argument("--skipped-optional", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        manifest = build_gate_manifest(
            passed_mandatory=set(args.passed_mandatory),
            skipped_mandatory=set(args.skipped_mandatory),
            failed_mandatory=set(args.failed_mandatory),
            pending_mandatory=set(args.pending_mandatory),
            passed_optional=set(args.passed_optional),
            skipped_optional=set(args.skipped_optional),
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Release gate manifest written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
