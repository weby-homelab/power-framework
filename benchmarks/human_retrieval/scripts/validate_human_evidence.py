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
    "recall_at_10": 0.80,
    "ndcg_at_10": 0.70,
    "mrr_at_10": 0.70,
    "citation_provenance_accuracy": 0.95,
    "stale_answer_rate_max": 0.02,
    "abstention_quality": 0.90,
    "p95_latency_ms": 1500,
}
logger = logging.getLogger(__name__)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_manifest(manifest: dict[str, Any], *, allow_sealed: bool) -> list[str]:
    """Return contract violations; never silently treats a holdout as development."""
    errors: list[str] = []
    schema_version = manifest.get("schema_version")
    if schema_version not in {"1.0", "2.0"}:
        errors.append("schema_version must be '1.0' or '2.0'")
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
        if not _is_sha256(value):
            errors.append(f"{key} must be a lowercase SHA-256 hex digest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACTS):
        errors.append("artifacts must name corpus, queries, raw_judgments, and adjudicated_qrels")
    elif not all(isinstance(path, str) and path for path in artifacts.values()):
        errors.append("artifact paths must be non-empty strings")
    expected_protocol = (
        "annotation_protocol_v2.md" if schema_version == "2.0" else "annotation_protocol.md"
    )
    if manifest.get("annotation_protocol") != expected_protocol:
        errors.append(f"annotation_protocol must be {expected_protocol}")
    if schema_version == "2.0":
        calibration = manifest.get("calibration")
        if not isinstance(calibration, dict) or calibration.get("status") != "passed":
            errors.append("schema v2 requires a passed calibration receipt")
        elif not _is_sha256(calibration.get("agreement_receipt_sha256")):
            errors.append("schema v2 calibration requires agreement_receipt_sha256")
    if manifest.get("status") == "adjudicated":
        thresholds = manifest.get("thresholds")
        if not isinstance(thresholds, dict) or set(thresholds) != set(REQUIRED_THRESHOLDS):
            errors.append("adjudicated evidence requires complete pre-registered thresholds")
        elif not all(
            isinstance(value, (int, float)) and math.isfinite(value)
            for value in thresholds.values()
        ):
            errors.append("pre-registered thresholds must be finite numbers")
        elif thresholds != REQUIRED_THRESHOLDS:
            errors.append("adjudicated evidence thresholds must match the canonical M2 policy")
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


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            rows.append(value)
    return rows


def validate_adjudicated_qrels(queries_path: Path, qrels_path: Path) -> list[str]:
    """Validate query-level consistency and joint metric feasibility."""
    queries = {str(row.get("query_id", "")): row for row in _load_jsonl(queries_path)}
    grouped: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for row in _load_jsonl(qrels_path):
        query_id = str(row.get("query_id", ""))
        document_id = str(row.get("document_id", ""))
        final = row.get("final")
        if not query_id or not document_id or not isinstance(final, dict):
            errors.append("frozen qrels require query_id, document_id and final object")
            continue
        relevance = final.get("relevance")
        if not isinstance(relevance, int) or relevance < -1 or relevance > 2:
            errors.append(f"unsupported final relevance for {query_id}/{document_id}")
            continue
        bucket = grouped.setdefault(
            query_id,
            {
                "relevance": {},
                "citation": {},
                "temporal": {},
                "abstention": set(),
                "taxonomy": set(),
            },
        )
        bucket["relevance"][document_id] = relevance
        bucket["citation"][document_id] = bool(final.get("acceptable_citation"))
        bucket["temporal"][document_id] = str(final.get("temporal_status"))
        abstention_key = (
            "query_abstention_correct"
            if "query_abstention_correct" in final
            else "abstention_correct"
        )
        bucket["abstention"].add(str(final.get(abstention_key)))
        bucket["taxonomy"].add(str(final.get("taxonomy")))

    if set(queries) != set(grouped):
        errors.append("queries and frozen qrels have different query IDs")
        return errors
    for query_id, query in queries.items():
        qrel = grouped[query_id]
        if qrel["abstention"] not in ({"yes"}, {"no"}):
            errors.append(f"{query_id}: query-level abstention labels are missing or inconsistent")
        journey = str(query.get("journey", ""))
        if qrel["taxonomy"] != {journey}:
            errors.append(f"{query_id}: qrel taxonomy must match the query journey")
        for document_id, acceptable in qrel["citation"].items():
            if acceptable and qrel["relevance"][document_id] < 1:
                errors.append(
                    f"{query_id}/{document_id}: acceptable citation requires relevance >= 1"
                )
        if journey == "current_fact" and "no" in qrel["abstention"]:
            feasible = any(
                qrel["relevance"][document_id] >= 1
                and qrel["citation"].get(document_id, False)
                and qrel["temporal"].get(document_id) == "current"
                for document_id in qrel["relevance"]
            )
            if not feasible:
                errors.append(
                    f"{query_id}: no jointly relevant, citation-acceptable and current document"
                )
    return errors


def validate_evidence_file(manifest_path: Path, *, allow_sealed: bool) -> list[str]:
    """Validate the manifest plus the exact bytes it claims to govern."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, allow_sealed=allow_sealed)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return errors
    resolved_artifacts: dict[str, Path] = {}
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
        else:
            resolved_artifacts[artifact_key] = artifact_path
    if (
        manifest.get("status") == "adjudicated"
        and "queries" in resolved_artifacts
        and "adjudicated_qrels" in resolved_artifacts
    ):
        errors.extend(
            validate_adjudicated_qrels(
                resolved_artifacts["queries"], resolved_artifacts["adjudicated_qrels"]
            )
        )
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
