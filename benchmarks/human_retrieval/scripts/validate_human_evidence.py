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
VALID_STATUSES = {"pending_calibration", "pending_human_annotation", "adjudicated"}
ARTIFACTS = {
    "corpus": "corpus_sha256",
    "queries": "queries_sha256",
    "raw_judgments": "raw_judgments_sha256",
    "adjudicated_qrels": "adjudicated_qrels_sha256",
}
REQUIRED_THRESHOLDS = {
    "recall_at_10": 0.75,
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
    if manifest.get("status") not in VALID_STATUSES:
        errors.append("status must be pending_calibration, pending_human_annotation or adjudicated")
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
        if manifest.get("language") != "uk":
            errors.append("schema v2 requires language=uk")
        calibration = manifest.get("calibration")
        if not isinstance(calibration, dict):
            errors.append("schema v2 requires a calibration object")
        else:
            calibration_status = calibration.get("status")
            if manifest.get("status") == "pending_calibration" and calibration_status != "pending":
                errors.append("pending_calibration requires calibration status=pending")
            if manifest.get("status") in {"pending_human_annotation", "adjudicated"}:
                if calibration_status != "passed":
                    errors.append("v2 annotation requires a passed calibration receipt")
                elif (
                    not isinstance(calibration.get("agreement_receipt"), str)
                    or not calibration["agreement_receipt"]
                ):
                    errors.append("passed v2 calibration requires agreement_receipt path")
                elif not _is_sha256(calibration.get("agreement_receipt_sha256")):
                    errors.append("passed v2 calibration requires agreement_receipt_sha256")
            elif calibration_status not in {"pending", "passed"}:
                errors.append("calibration status must be pending or passed")
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
        agreement = manifest.get("agreement")
        if not isinstance(agreement, dict):
            errors.append("adjudicated evidence requires an agreement receipt")
        else:
            if not isinstance(agreement.get("receipt"), str) or not agreement["receipt"]:
                errors.append("adjudicated evidence requires agreement.receipt path")
            if not _is_sha256(agreement.get("receipt_sha256")):
                errors.append("adjudicated evidence requires agreement.receipt_sha256")
    return errors


def _artifact_path(root: Path, value: str) -> Path | None:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _validate_receipt_binding(
    manifest_root: Path,
    *,
    relative_path: object,
    expected_sha256: object,
    label: str,
    expected_raw_sha256: str | None = None,
) -> list[str]:
    """Verify a de-identified agreement receipt is present and hash-bound."""
    errors: list[str] = []
    if not isinstance(relative_path, str) or not relative_path:
        return [f"{label} receipt path must be a non-empty string"]
    receipt_path = _artifact_path(manifest_root, relative_path)
    if receipt_path is None:
        return [f"{label} receipt path must stay under the manifest directory"]
    if not receipt_path.is_file():
        return [f"{label} receipt is missing"]
    actual_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        errors.append(f"{label} receipt SHA-256 does not match its manifest binding")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [*errors, f"{label} receipt is not valid JSON"]
    if receipt.get("schema_version") != "power.m2.human-agreement.v2":
        errors.append(f"{label} receipt has an unsupported schema")
    if receipt.get("annotation_protocol_version") != "2.0":
        errors.append(f"{label} receipt must use annotation protocol 2.0")
    if receipt.get("status") != "calibration_passed":
        errors.append(f"{label} receipt is not calibration_passed")
    if (
        expected_raw_sha256 is not None
        and receipt.get("raw_judgments_sha256") != expected_raw_sha256
    ):
        errors.append(f"{label} receipt raw judgments do not match the manifest")
    return errors


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


def validate_adjudicated_qrels(
    queries_path: Path, qrels_path: Path, *, schema_version: str = "1.0"
) -> list[str]:
    """Validate qrels consistency and joint metric feasibility."""
    queries = {str(row.get("query_id", "")): row for row in _load_jsonl(queries_path)}
    grouped: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    seen_units: set[tuple[str, str]] = set()
    for row in _load_jsonl(qrels_path):
        query_id = str(row.get("query_id", ""))
        document_id = str(row.get("document_id", ""))
        final = row.get("final")
        if not query_id or not document_id or not isinstance(final, dict):
            errors.append("frozen qrels require query_id, document_id and final object")
            continue
        unit = (query_id, document_id)
        if unit in seen_units:
            errors.append(f"duplicate frozen qrel for {query_id}/{document_id}")
            continue
        seen_units.add(unit)
        relevance = final.get("relevance")
        minimum_relevance = 0 if schema_version == "2.0" else -1
        if (
            not isinstance(relevance, int)
            or isinstance(relevance, bool)
            or relevance < minimum_relevance
            or relevance > 2
        ):
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
        citation = final.get("acceptable_citation")
        if schema_version == "2.0" and not isinstance(citation, bool):
            errors.append(
                f"{query_id}/{document_id}: v2 acceptable_citation must be a JSON boolean"
            )
        bucket["citation"][document_id] = bool(citation)
        temporal = final.get("temporal_status")
        if schema_version == "2.0" and temporal not in {
            "current",
            "historical",
            "not_applicable",
        }:
            errors.append(f"{query_id}/{document_id}: v2 temporal_status is invalid")
        bucket["temporal"][document_id] = str(temporal)
        if schema_version == "2.0":
            if "query_abstention_correct" in final or "abstention_correct" in final:
                errors.append(f"{query_id}: v2 forbids manual query-level abstention labels")
            if "taxonomy" in final:
                errors.append(f"{query_id}: v2 taxonomy is derived, not a human qrel field")
        else:
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
        journey = str(query.get("journey", ""))
        if schema_version != "2.0":
            if qrel["abstention"] not in ({"yes"}, {"no"}):
                errors.append(
                    f"{query_id}: query-level abstention labels are missing or inconsistent"
                )
            if qrel["taxonomy"] != {journey}:
                errors.append(f"{query_id}: qrel taxonomy must match the query journey")
        for document_id, acceptable in qrel["citation"].items():
            minimum_for_citation = 2 if schema_version == "2.0" else 1
            if acceptable and qrel["relevance"][document_id] < minimum_for_citation:
                errors.append(
                    f"{query_id}/{document_id}: acceptable citation requires direct relevance"
                )
        answerable = (
            any(value >= 2 for value in qrel["relevance"].values())
            if schema_version == "2.0"
            else "no" in qrel["abstention"]
        )
        if schema_version == "2.0" and journey == "abstention" and answerable:
            errors.append(f"{query_id}: abstention journey has a direct answer")
        if journey == "current_fact" and answerable:
            feasible = any(
                qrel["relevance"][document_id] >= (2 if schema_version == "2.0" else 1)
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
    if str(manifest.get("schema_version")) == "2.0":
        calibration = manifest.get("calibration")
        if isinstance(calibration, dict) and calibration.get("status") == "passed":
            errors.extend(
                _validate_receipt_binding(
                    manifest_path.parent,
                    relative_path=calibration.get("agreement_receipt"),
                    expected_sha256=calibration.get("agreement_receipt_sha256"),
                    label="calibration",
                )
            )
        agreement = manifest.get("agreement")
        if manifest.get("status") == "adjudicated" and isinstance(agreement, dict):
            errors.extend(
                _validate_receipt_binding(
                    manifest_path.parent,
                    relative_path=agreement.get("receipt"),
                    expected_sha256=agreement.get("receipt_sha256"),
                    label="adjudication",
                    expected_raw_sha256=(
                        str(manifest.get("raw_judgments_sha256"))
                        if _is_sha256(manifest.get("raw_judgments_sha256"))
                        else None
                    ),
                )
            )
    if (
        manifest.get("status") == "adjudicated"
        and "queries" in resolved_artifacts
        and "adjudicated_qrels" in resolved_artifacts
    ):
        errors.extend(
            validate_adjudicated_qrels(
                resolved_artifacts["queries"],
                resolved_artifacts["adjudicated_qrels"],
                schema_version=str(manifest.get("schema_version", "1.0")),
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
