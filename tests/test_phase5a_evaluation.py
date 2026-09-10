"""Frozen POWER 3.8 evaluation-corpus integrity tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest

from power_framework.core.evaluation_contracts import (
    EvaluationIntegrityError,
    load_development_for_tuning,
    reject_holdout_tuning,
    verify_evaluation_corpus,
)

ROOT = Path(__file__).parents[1] / "benchmarks" / "power38" / "retrieval_eval" / "v1"
EXPECTED = {
    "dataset_digest": "b902fb658df371b24335cec9813afd197995fda5de228dfb6957b85cc6fba3a1",
    "query_set_digest": "0b7596a4da4f21096ca3720712a65d45a5f426f046c6b3aabfde15d52fb70e68",
    "development_digest": "629a7ef0c88694ad53ee04b66bf8b8fd00ecf036166983cefb41dc821ce179a2",
    "holdout_digest": "2fefbb94b9ddf63b50b6226df862b033c41c16838f2ca72d675594f28dc4cedb",
    "disjointness_digest": "554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275",
}


def copied_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "eval"
    shutil.copytree(ROOT, target)
    return target


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_frozen_corpus_verifies_with_reproducible_digests() -> None:
    first = verify_evaluation_corpus(ROOT)
    second = verify_evaluation_corpus(ROOT)
    assert first == second
    assert {key: first[key] for key in EXPECTED} == EXPECTED
    assert first["source_count"] == 20
    assert first["development_query_count"] == 20
    assert first["holdout_query_count"] == 20
    assert first["holdout_policy"] == "SEALED_NOT_SECRET_NO_TUNING"


def test_development_tuning_loader_never_loads_holdout() -> None:
    assert len(load_development_for_tuning(ROOT)) == 20
    with pytest.raises(EvaluationIntegrityError, match="holdout cannot"):
        reject_holdout_tuning("holdout")


def test_integrity_read_is_distinct_from_tuning() -> None:
    result = verify_evaluation_corpus(ROOT)
    assert result["holdout_policy"] == "SEALED_NOT_SECRET_NO_TUNING"
    with pytest.raises(EvaluationIntegrityError):
        reject_holdout_tuning("holdout")


def test_manifest_digest_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_digest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(EvaluationIntegrityError, match="manifest"):
        verify_evaluation_corpus(fixture)


def test_source_byte_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    source = fixture / "corpus" / "p38-src-project-current.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
    with pytest.raises(EvaluationIntegrityError, match="source metadata digest"):
        verify_evaluation_corpus(fixture)


def test_duplicate_query_id_across_splits_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    holdout_path = fixture / "queries.holdout.jsonl"
    rows = read_jsonl(holdout_path)
    rows[0]["query_id"] = "p38-dev-q01"
    write_jsonl(holdout_path, rows)
    with pytest.raises(EvaluationIntegrityError, match="strict validation"):
        verify_evaluation_corpus(fixture)


def test_scenario_family_leak_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    holdout_path = fixture / "queries.holdout.jsonl"
    rows = read_jsonl(holdout_path)
    rows[0]["scenario_family"] = "family-dev-lookup-ua"
    write_jsonl(holdout_path, rows)
    with pytest.raises(EvaluationIntegrityError, match="scenario families"):
        verify_evaluation_corpus(fixture)


def test_normalized_query_overlap_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    development = read_jsonl(fixture / "queries.development.jsonl")
    holdout = read_jsonl(fixture / "queries.holdout.jsonl")
    holdout[0]["query"] = development[0]["query"]
    write_jsonl(fixture / "queries.holdout.jsonl", holdout)
    with pytest.raises(EvaluationIntegrityError, match="normalized query"):
        verify_evaluation_corpus(fixture)


def test_nonexistent_ground_truth_source_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    path = fixture / "ground_truth.jsonl"
    rows = read_jsonl(path)
    rows[0]["expected_relevant_source_ids"] = ["p38-src-does-not-exist"]
    rows[0]["graded_relevance"][0]["source_id"] = "p38-src-does-not-exist"  # type: ignore[index]
    write_jsonl(path, rows)
    with pytest.raises(EvaluationIntegrityError, match="unknown source"):
        verify_evaluation_corpus(fixture)


def test_unknown_query_field_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    path = fixture / "queries.development.jsonl"
    rows = read_jsonl(path)
    rows[0]["untrusted_extra"] = "reject"
    write_jsonl(path, rows)
    with pytest.raises(EvaluationIntegrityError, match="strict validation"):
        verify_evaluation_corpus(fixture)


def test_holdout_receipt_is_bounded_and_digest_bound() -> None:
    receipt = json.loads((ROOT / "holdout-access-receipt.json").read_text(encoding="utf-8"))
    assert receipt["purpose"] == "integrity_verification"
    assert receipt["split"] == "holdout"
    assert receipt["tuning_capability"] is False
    assert receipt["raw_content_egress"] is False
    assert "p38-dev-q01" not in json.dumps(receipt)


def test_planning_schemas_remain_meta_schema_valid() -> None:
    planning = Path(__file__).parents[1] / "artifacts" / "project-state" / "planning"
    for filename in (
        "context-retrieval-contracts-v1.schema.json",
        "context-retrieval-contracts-v2.schema.json",
        "retrieval-eval-v1.schema.json",
    ):
        schema = json.loads((planning / filename).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
