"""Validate the M2 human-retrieval evidence boundary without scoring it."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

REQUIRED_JOURNEYS = {
    "current_fact",
    "historical_fact",
    "provenance_trace",
    "abstention",
    "candidate_boundary",
}
REQUIRED_HASHES = {
    "corpus_sha256",
    "queries_sha256",
    "raw_judgments_sha256",
    "adjudicated_qrels_sha256",
}
VALID_SPLITS = {"development", "sealed_holdout"}
logger = logging.getLogger(__name__)


def validate_manifest(manifest: dict[str, Any], *, allow_sealed: bool) -> list[str]:
    """Return contract violations; never silently treats a holdout as development."""
    errors: list[str] = []
    if manifest.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if manifest.get("status") not in {"pending_human_annotation", "adjudicated"}:
        errors.append("status must be pending_human_annotation or adjudicated")
    split = manifest.get("split")
    if split not in VALID_SPLITS:
        errors.append("split must be development or sealed_holdout")
    elif split == "sealed_holdout" and not allow_sealed:
        errors.append("sealed_holdout requires --allow-sealed")
    if set(manifest.get("journeys", [])) != REQUIRED_JOURNEYS:
        errors.append("journeys must contain each required M2 journey exactly once")
    for key in REQUIRED_HASHES:
        value = manifest.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            errors.append(f"{key} must be a lowercase SHA-256 hex digest")
    if manifest.get("status") == "adjudicated" and not isinstance(manifest.get("thresholds"), dict):
        errors.append("adjudicated evidence requires pre-registered thresholds")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--allow-sealed", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, allow_sealed=args.allow_sealed)
    if errors:
        logger.error(
            "M2 evidence contract failed:\n%s", "\n".join(f"- {error}" for error in errors)
        )
        return 1
    logger.info(
        "M2 evidence manifest valid: split=%s status=%s", manifest["split"], manifest["status"]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
