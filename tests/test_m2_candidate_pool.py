"""Regression tests for the hash-bound M2-v2.1 candidate pool."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "build_candidate_pool.py"
)
SPEC = importlib.util.spec_from_file_location("m2_candidate_pool", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

POLICY = (
    Path(__file__).parents[1] / "benchmarks" / "human_retrieval" / "m2-v2.1-preregistration.json"
)
MODES = ("semantic", "hybrid", "reranked", "graph_assisted", "lexical", "vector")


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["status"] = "pre_registered_before_human_calibration"
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        "".join(
            json.dumps({"document_id": f"doc-{i}", "split": "development"}) + "\n"
            for i in range(1, 7)
        ),
        encoding="utf-8",
    )
    queries_path = tmp_path / "queries.jsonl"
    queries_path.write_text(
        "".join(
            json.dumps({"query_id": f"q-{i}", "question": "просте питання"}) + "\n"
            for i in range(1, 3)
        ),
        encoding="utf-8",
    )
    modes = {
        mode: {
            "status": "completed",
            "per_query": [
                {"query_id": "q-1", "result_doc_ids": ["doc-1", "doc-2"]},
                {"query_id": "q-2", "result_doc_ids": ["doc-2", "doc-3"]},
            ],
        }
        for mode in MODES
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps({"modes": modes}), encoding="utf-8")
    return policy_path, corpus_path, queries_path, receipt_path


def test_pool_is_deterministic_and_hash_bound(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = MODULE.build_pool(*inputs, first_path)
    second = MODULE.build_pool(*inputs, second_path)

    assert first["queries"] == second["queries"]
    assert first["policy_sha256"] == MODULE.sha256_file(inputs[0])
    assert first["source_receipt_sha256"] == MODULE.sha256_file(inputs[3])
    assert all(len(row["random_negative_ids"]) == 2 for row in first["queries"])
    if os.name != "nt":
        assert stat.S_IMODE(first_path.stat().st_mode) == 0o600


def test_pending_policy_is_fail_closed(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy_path = inputs[0]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="curator-approved policy status"):
        MODULE.build_pool(*inputs, tmp_path / "pool.json")


def test_missing_comparator_is_rejected(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    receipt_path = inputs[3]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    del receipt["modes"]["vector"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ValueError, match="comparator vector is missing"):
        MODULE.build_pool(*inputs, tmp_path / "pool.json")
