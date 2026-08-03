"""Regression tests for the machine-only M2-AUTO contract and verifier."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

EVALUATION_DIR = Path(__file__).resolve().parent.parent / "scripts" / "evaluation"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import run_m2_auto  # noqa: E402
import verify_m2_auto  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_evidence() -> dict:
    contract_path = run_m2_auto.CONTRACT_DEFAULT
    dataset = run_m2_auto.DATASET_V1
    return {
        "schema_version": "m2-auto-evidence/v1",
        "contract_sha256": _sha256(contract_path),
        "scope": "machine_only",
        "human_evidence_used": False,
        "sealed_accessed": False,
        "benchmark_version": "power31.v1",
        "source": {"commit": "a" * 40, "dirty_tree": False},
        "dataset": {
            "manifest_sha256": _sha256(dataset / "corpus-manifest.json"),
            "queries_sha256": _sha256(dataset / "queries.jsonl"),
            "qrels_sha256": _sha256(dataset / "qrels.synthetic.jsonl"),
            "query_count": 228,
            "document_count": 100,
            "qrel_count": 416,
        },
        "modes": {"baseline": "fts", "candidate": "hybrid"},
        "metrics": {
            "baseline": {
                "ndcg@10": 0.58,
                "mrr@10": 0.71,
                "recall@5": 0.62,
                "precision@5": 0.25,
            },
            "candidate": {
                "ndcg@10": 0.59,
                "mrr@10": 0.72,
                "recall@5": 0.63,
                "precision@5": 0.24,
            },
            "paired": {
                "ndcg@10": {"delta": 0.01},
                "mrr@10": {"delta": 0.01},
                "recall@5": {"delta": 0.01},
                "precision@5": {"delta": -0.01},
            },
        },
        "runtime_seconds": 12.0,
        "failures": [],
        "quality_gate": "PASS",
    }


def test_contract_is_machine_only_and_bounded() -> None:
    contract = json.loads(run_m2_auto.CONTRACT_DEFAULT.read_text(encoding="utf-8"))
    run_m2_auto._validate_contract(contract)
    assert contract["scope"] == "machine_only"
    assert contract["human_evidence_used"] is False
    assert contract["sealed_accessed"] is False
    assert contract["max_runtime_seconds"] == 45


def test_verifier_accepts_valid_machine_only_evidence() -> None:
    assert verify_m2_auto.verify(
        _write_fixture(_valid_evidence()), run_m2_auto.CONTRACT_DEFAULT
    ) == []


def test_verifier_rejects_human_or_sealed_markers() -> None:
    evidence = _valid_evidence()
    evidence["human_evidence_used"] = True
    evidence["limitations"] = ["sealed_holdout/evaluation-v2 was read"]
    errors = verify_m2_auto.verify(
        _write_fixture(evidence), run_m2_auto.CONTRACT_DEFAULT
    )
    assert any("human evidence" in error for error in errors)
    assert any("forbidden" in error for error in errors)


def _write_fixture(evidence: dict) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(copy.deepcopy(evidence), handle)
        return Path(handle.name)
