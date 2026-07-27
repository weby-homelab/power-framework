#!/usr/bin/env python3
"""Validate a reproducible POWER benchmark evidence manifest.

The JSON schema guards structure; the additional checks below protect the
cross-references and release-evidence rules that JSON Schema cannot express.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = REPO_ROOT / "release" / "evidence" / "benchmark-manifest.schema.json"
REQUIRED_MODEL_ROLES = frozenset({"embedding", "reranker"})
MEASUREMENT_CLASSIFICATIONS = frozenset({"cold", "warm"})


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object or report a precise, actionable validation error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return structural and evidence-integrity errors for one manifest."""
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [error.message for error in sorted(validator.iter_errors(manifest), key=str)]
    if errors:
        return errors

    artifacts = manifest["artifacts"]
    artifact_hashes = {artifact["sha256"] for artifact in artifacts}
    artifact_paths = [artifact["path"] for artifact in artifacts]
    errors.extend(
        "artifact paths must be relative and must not escape the evidence directory"
        for path in artifact_paths
        if Path(path).is_absolute() or ".." in Path(path).parts
    )
    if len(artifact_paths) != len(set(artifact_paths)):
        errors.append("artifact paths must be unique")

    model_roles = {model["role"] for model in manifest["models"]}
    missing_roles = REQUIRED_MODEL_ROLES - model_roles
    if missing_roles:
        errors.append(f"models missing required role(s): {', '.join(sorted(missing_roles))}")

    measurement_classes = {
        measurement["classification"] for measurement in manifest["measurements"]
    }
    missing_classes = MEASUREMENT_CLASSIFICATIONS - measurement_classes
    if missing_classes:
        errors.append(
            f"measurements missing required classification(s): {', '.join(sorted(missing_classes))}"
        )

    errors.extend(
        f"measurement {measurement['name']!r} references an unknown artifact checksum"
        for measurement in manifest["measurements"]
        if measurement["artifact_sha256"] not in artifact_hashes
    )
    for claim in manifest["claims"]:
        if claim["evidence_artifact_sha256"] not in artifact_hashes:
            errors.append(f"claim {claim['id']!r} references an unknown artifact checksum")
        if claim["state"] == "measured" and manifest["source"]["dirty"]:
            errors.append(f"measured claim {claim['id']!r} requires source.dirty=false")
    return errors


def main() -> int:
    """Validate a manifest, or check that the schema itself is well-formed."""
    parser = argparse.ArgumentParser(description="Validate POWER benchmark evidence manifests")
    parser.add_argument("manifest", type=Path, nargs="?", help="Manifest JSON to validate")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema JSON path")
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Validate the schema without requiring a benchmark manifest",
    )
    args = parser.parse_args()

    if args.schema_only == (args.manifest is not None):
        parser.error("provide exactly one of a manifest path or --schema-only")

    try:
        schema = _load_json(args.schema)
        Draft202012Validator.check_schema(schema)
        if args.schema_only:
            print(f"Benchmark manifest schema is valid: {args.schema}")
            return 0
        assert args.manifest is not None
        errors = validate_manifest(_load_json(args.manifest), schema)
    except ValueError as exc:
        print(f"Manifest validation failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Manifest validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Benchmark manifest is valid: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
