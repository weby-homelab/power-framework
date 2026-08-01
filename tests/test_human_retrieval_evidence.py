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
        agreement={},
    )
    assert MODULE.REQUIRED_THRESHOLDS == CANONICAL_THRESHOLDS
    assert MODULE.validate_manifest(manifest, allow_sealed=False) == []
    for key, value in CANONICAL_THRESHOLDS.items():
        manifest["thresholds"] = {**CANONICAL_THRESHOLDS, key: value + 1}
        assert "adjudicated evidence thresholds must match the canonical M2 policy" in (
            MODULE.validate_manifest(manifest, allow_sealed=False)
        )


def test_protocol_v2_requires_hash_bound_passed_calibration() -> None:
    manifest = _manifest(
        schema_version="2.0",
        annotation_protocol="annotation_protocol_v2.md",
    )

    assert "schema v2 requires a passed calibration receipt" in MODULE.validate_manifest(
        manifest, allow_sealed=False
    )

    manifest["calibration"] = {
        "status": "passed",
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
