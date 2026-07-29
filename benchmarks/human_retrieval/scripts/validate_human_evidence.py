"""Validate the M2 human-retrieval evidence boundary without scoring it."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
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
ARTIFACTS = {
    "corpus": "corpus_sha256",
    "queries": "queries_sha256",
    "raw_judgments": "raw_judgments_sha256",
    "adjudicated_qrels": "adjudicated_qrels_sha256",
}
REQUIRED_THRESHOLDS = {
    "recall_at_10",
    "ndcg_at_10",
    "mrr_at_10",
    "citation_provenance_accuracy",
    "stale_answer_rate_max",
    "abstention_quality",
    "p95_latency_ms",
}
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
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACTS):
        errors.append("artifacts must name corpus, queries, raw_judgments, and adjudicated_qrels")
    elif not all(isinstance(path, str) and path for path in artifacts.values()):
        errors.append("artifact paths must be non-empty strings")
    if manifest.get("status") == "adjudicated":
        thresholds = manifest.get("thresholds")
        if not isinstance(thresholds, dict) or set(thresholds) != REQUIRED_THRESHOLDS:
            errors.append("adjudicated evidence requires complete pre-registered thresholds")
        elif not all(
            isinstance(value, (int, float)) and math.isfinite(value)
            for value in thresholds.values()
        ):
            errors.append("pre-registered thresholds must be finite numbers")
        if not isinstance(manifest.get("annotator_count"), int) or manifest["annotator_count"] < 2:
            errors.append("adjudicated evidence requires at least two independent annotators")
        if not isinstance(manifest.get("agreement"), dict):
            errors.append("adjudicated evidence requires an agreement receipt")
    return errors


def _artifact_path(root: Path, value: str) -> Path | None:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def validate_evidence_file(manifest_path: Path, *, allow_sealed: bool) -> list[str]:
    """Validate the manifest plus the exact bytes it claims to govern."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, allow_sealed=allow_sealed)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return errors
    for artifact_key, digest_key in ARTIFACTS.items():
        relative_path = artifacts.get(artifact_key)
        if not isinstance(relative_path, str):
            continue
        artifact_path = _artifact_path(manifest_path.parent, relative_path)
        if artifact_path is None:
            errors.append(f"{artifact_key} path must stay under the manifest directory")
        elif not artifact_path.is_file():
            errors.append(f"{artifact_key} artifact is missing")
        elif hashlib.sha256(artifact_path.read_bytes()).hexdigest() != manifest.get(digest_key):
            errors.append(f"{artifact_key} SHA-256 does not match {digest_key}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--allow-sealed", action="store_true")
    args = parser.parse_args()
    errors = validate_evidence_file(args.manifest, allow_sealed=args.allow_sealed)
    if errors:
        logger.error(
            "M2 evidence contract failed:\n%s", "\n".join(f"- {error}" for error in errors)
        )
        return 1
    logger.info("M2 evidence manifest valid: %s", args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
