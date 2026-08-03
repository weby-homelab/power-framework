"""Contract tests for the M2 human-evidence boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "validate_human_evidence.py"
)
SPEC = importlib.util.spec_from_file_location("m2_evidence", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANONICAL_THRESHOLDS = {
    "recall_at_10": 0.80,
    "ndcg_at_10": 0.70,
    "mrr_at_10": 0.70,
    "citation_provenance_accuracy": 0.95,
    "stale_answer_rate_max": 0.02,
    "abstention_quality": 0.90,
    "p95_latency_ms": 1500,
}


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "status": "pending_human_annotation",
        "split": "development",
        "corpus_sha256": "a" * 64,
        "queries_sha256": "b" * 64,
        "raw_judgments_sha256": "c" * 64,
        "adjudicated_qrels_sha256": "d" * 64,
        "artifacts": {
            "corpus": "corpus.jsonl",
            "queries": "queries.jsonl",
            "raw_judgments": "raw-judgments.jsonl",
            "adjudicated_qrels": "adjudicated-qrels.jsonl",
        },
        "annotation_protocol": "annotation_protocol.md",
        "journeys": sorted(MODULE.REQUIRED_JOURNEYS),
        "thresholds": None,
    }
    manifest.update(overrides)
    return manifest


def test_development_manifest_is_valid_before_annotation() -> None:
    assert MODULE.validate_manifest(_manifest(), allow_sealed=False) == []


def test_sealed_holdout_requires_explicit_release_review() -> None:
    manifest = _manifest(split="sealed_holdout")
    assert "sealed_holdout requires --allow-sealed" in MODULE.validate_manifest(
        manifest, allow_sealed=False
    )
    assert MODULE.validate_manifest(manifest, allow_sealed=True) == []


def test_adjudicated_manifest_requires_preregistered_thresholds() -> None:
    errors = MODULE.validate_manifest(_manifest(status="adjudicated"), allow_sealed=False)
    assert "adjudicated evidence requires complete pre-registered thresholds" in errors


def test_adjudicated_manifest_requires_canonical_threshold_values() -> None:
    manifest = _manifest(
        status="adjudicated",
        thresholds=dict(CANONICAL_THRESHOLDS),
        annotator_count=2,
        agreement={"receipt": "agreement.v2.json", "receipt_sha256": "e" * 64},
    )
    assert MODULE.REQUIRED_THRESHOLDS == CANONICAL_THRESHOLDS
    assert MODULE.validate_manifest(manifest, allow_sealed=False) == []
    for key, value in CANONICAL_THRESHOLDS.items():
        manifest["thresholds"] = {**CANONICAL_THRESHOLDS, key: value + 1}
        assert "adjudicated evidence thresholds must match the m2-v2 policy" in (
            MODULE.validate_manifest(manifest, allow_sealed=False)
        )


def test_v21_threshold_profile_is_explicit_and_separate() -> None:
    manifest = _manifest(
        schema_version="2.0",
        annotation_protocol="annotation_protocol_v2.md",
        language="uk",
        status="adjudicated",
        threshold_profile="m2-v2.1",
        thresholds=dict(MODULE.V21_THRESHOLDS),
        annotator_count=2,
        agreement={"receipt": "agreement.v2.json", "receipt_sha256": "e" * 64},
        calibration={
            "status": "passed",
            "agreement_receipt": "calibration-agreement.v2.json",
            "agreement_receipt_sha256": "f" * 64,
        },
    )
    assert MODULE.validate_manifest(manifest, allow_sealed=False) == []

    manifest.pop("threshold_profile")
    assert "adjudicated evidence thresholds must match the m2-v2 policy" in (
        MODULE.validate_manifest(manifest, allow_sealed=False)
    )


def test_protocol_v2_starts_pending_and_requires_hash_bound_calibration() -> None:
    manifest = _manifest(
        schema_version="2.0",
        annotation_protocol="annotation_protocol_v2.md",
        language="uk",
        status="pending_calibration",
        calibration={"status": "pending", "agreement_receipt_sha256": None},
    )

    assert MODULE.validate_manifest(manifest, allow_sealed=False) == []

    manifest["status"] = "pending_human_annotation"
    manifest["calibration"] = {
        "status": "passed",
        "agreement_receipt": "calibration-agreement.v2.json",
        "agreement_receipt_sha256": "e" * 64,
    }
    assert MODULE.validate_manifest(manifest, allow_sealed=False) == []


def test_evidence_file_binds_each_artifact_to_its_declared_hash(tmp_path: Path) -> None:
    artifacts = _manifest()["artifacts"]
    assert isinstance(artifacts, dict)
    manifest = _manifest()
    for key, filename in artifacts.items():
        content = f"{key}\n"
        (tmp_path / filename).write_text(content, encoding="utf-8")
        manifest[f"{key}_sha256" if key != "raw_judgments" else "raw_judgments_sha256"] = (
            hashlib.sha256(content.encode()).hexdigest()
        )
    manifest["adjudicated_qrels_sha256"] = hashlib.sha256(
        (tmp_path / artifacts["adjudicated_qrels"]).read_bytes()
    ).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert MODULE.validate_evidence_file(manifest_path, allow_sealed=False) == []
    (tmp_path / artifacts["queries"]).write_text("tampered\n", encoding="utf-8")
    assert "queries SHA-256 does not match queries_sha256" in MODULE.validate_evidence_file(
        manifest_path, allow_sealed=False
    )


def test_v2_evidence_binds_calibration_receipt_bytes(tmp_path: Path) -> None:
    manifest = _manifest(
        schema_version="2.0",
        annotation_protocol="annotation_protocol_v2.md",
        language="uk",
        status="pending_human_annotation",
        calibration={
            "status": "passed",
            "agreement_receipt": "calibration-agreement.v2.json",
            "agreement_receipt_sha256": "0" * 64,
        },
    )
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    for key, filename in artifacts.items():
        content = f"{key}\n".encode()
        (tmp_path / filename).write_bytes(content)
        digest_key = "raw_judgments_sha256" if key == "raw_judgments" else f"{key}_sha256"
        manifest[digest_key] = hashlib.sha256(content).hexdigest()
    receipt = {
        "schema_version": "power.m2.human-agreement.v2",
        "annotation_protocol_version": "2.0",
        "status": "calibration_passed",
    }
    receipt_path = tmp_path / "calibration-agreement.v2.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest["calibration"]["agreement_receipt_sha256"] = hashlib.sha256(  # type: ignore[index]
        receipt_path.read_bytes()
    ).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert MODULE.validate_evidence_file(manifest_path, allow_sealed=False) == []
    receipt_path.write_text("tampered\n", encoding="utf-8")
    assert "calibration receipt SHA-256 does not match its manifest binding" in (
        MODULE.validate_evidence_file(manifest_path, allow_sealed=False)
    )


def test_v2_qrels_derive_answerability_and_reject_old_fields(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.jsonl"
    queries.write_text(
        json.dumps({"query_id": "q-current", "journey": "current_fact"}) + "\n",
        encoding="utf-8",
    )
    qrels.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "query_id": "q-current",
                    "document_id": "doc-current",
                    "final": {
                        "relevance": 2,
                        "acceptable_citation": True,
                        "temporal_status": "current",
                    },
                },
                {
                    "query_id": "q-current",
                    "document_id": "doc-other",
                    "final": {
                        "relevance": 0,
                        "acceptable_citation": False,
                        "temporal_status": "not_applicable",
                    },
                },
            )
        ),
        encoding="utf-8",
    )
    assert MODULE.validate_adjudicated_qrels(queries, qrels, schema_version="2.0") == []

    invalid = json.loads(qrels.read_text(encoding="utf-8").splitlines()[0])
    invalid["final"]["relevance"] = -1
    invalid["final"]["abstention_correct"] = "no"
    qrels.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
    errors = MODULE.validate_adjudicated_qrels(queries, qrels, schema_version="2.0")
    assert any("unsupported final relevance" in error for error in errors)


def test_v2_qrels_reject_non_boolean_citation(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.jsonl"
    queries.write_text(
        json.dumps({"query_id": "q-current", "journey": "current_fact"}) + "\n",
        encoding="utf-8",
    )
    qrels.write_text(
        json.dumps(
            {
                "query_id": "q-current",
                "document_id": "doc-current",
                "final": {
                    "relevance": 2,
                    "acceptable_citation": "true",
                    "temporal_status": "current",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = MODULE.validate_adjudicated_qrels(queries, qrels, schema_version="2.0")

    assert "q-current/doc-current: v2 acceptable_citation must be a JSON boolean" in errors


def test_v2_qrels_reject_missing_temporal_status(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.jsonl"
    queries.write_text(
        json.dumps({"query_id": "q-current", "journey": "current_fact"}) + "\n",
        encoding="utf-8",
    )
    qrels.write_text(
        json.dumps(
            {
                "query_id": "q-current",
                "document_id": "doc-current",
                "final": {"relevance": 2, "acceptable_citation": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = MODULE.validate_adjudicated_qrels(queries, qrels, schema_version="2.0")

    assert "q-current/doc-current: v2 temporal_status is invalid" in errors


def test_adjudicated_qrels_reject_jointly_infeasible_current_fact(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.jsonl"
    queries.write_text(
        json.dumps(
            {
                "query_id": "q-current",
                "journey": "current_fact",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    qrels.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "query_id": "q-current",
                    "document_id": "doc-history",
                    "final": {
                        "relevance": 2,
                        "acceptable_citation": True,
                        "temporal_status": "historical",
                        "abstention_correct": "no",
                        "taxonomy": "current_fact",
                    },
                },
                {
                    "query_id": "q-current",
                    "document_id": "doc-current",
                    "final": {
                        "relevance": 1,
                        "acceptable_citation": False,
                        "temporal_status": "current",
                        "abstention_correct": "yes",
                        "taxonomy": "historical_fact",
                    },
                },
            )
        ),
        encoding="utf-8",
    )

    errors = MODULE.validate_adjudicated_qrels(queries, qrels)

    assert "q-current: query-level abstention labels are missing or inconsistent" in errors
    assert "q-current: qrel taxonomy must match the query journey" in errors
    assert "q-current: no jointly relevant, citation-acceptable and current document" in errors
