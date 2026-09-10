"""Frozen POWER 3.8 evaluation-corpus integrity tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

import power_framework.core.evaluation_contracts as evaluation_contracts
from power_framework.core.evaluation_contracts import (
    EvaluationIntegrityError,
    load_development_for_tuning,
    reject_holdout_tuning,
    verify_evaluation_corpus,
)

ROOT = Path(__file__).parents[1] / "benchmarks" / "power38" / "retrieval_eval" / "v1"
EXPECTED = {
    "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
    "dataset_digest": "179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0",
    "query_set_digest": "7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086",
    "development_digest": "29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289",
    "holdout_digest": "ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a",
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
    assert first["source_corpus_digest"] == EXPECTED["source_corpus_digest"]
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
    rows[1]["query_id"] = "p38-ho-q01"
    write_jsonl(holdout_path, rows)
    with pytest.raises(EvaluationIntegrityError, match="query IDs"):
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
    path = fixture / "ground_truth.development.jsonl"
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


def test_duplicate_json_key_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    digest = manifest["dataset_digest"]
    (fixture / "manifest.json").write_text(
        '{"dataset_digest":"' + digest + '","dataset_digest":"' + "0" * 64 + '"}',
        encoding="utf-8",
    )
    with pytest.raises(EvaluationIntegrityError, match="duplicate JSON"):
        verify_evaluation_corpus(fixture)


def test_extra_corpus_artifact_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    (fixture / "corpus" / "extra.md").write_text("not admitted", encoding="utf-8")
    with pytest.raises(EvaluationIntegrityError, match="enumerate"):
        verify_evaluation_corpus(fixture)


def test_symlinked_corpus_artifact_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    try:
        (fixture / "corpus" / "link.md").symlink_to(
            fixture / "corpus" / "p38-src-project-current.md"
        )
    except OSError:
        pytest.skip("symlinks unavailable in this environment")
    with pytest.raises(EvaluationIntegrityError, match=r"non-Markdown|symlink"):
        verify_evaluation_corpus(fixture)


def test_tuning_loader_validates_only_pinned_development_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = copied_fixture(tmp_path)
    original = evaluation_contracts._read_jsonl

    def no_holdout_read(path: Path) -> list[dict[str, object]]:
        assert "holdout" not in path.name
        return original(path)

    monkeypatch.setattr(evaluation_contracts, "_read_jsonl", no_holdout_read)
    assert len(load_development_for_tuning(fixture)) == 20


def test_tuning_loader_rejects_changed_development_bytes(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    path = fixture / "queries.development.jsonl"
    rows = read_jsonl(path)
    rows[0]["query"] = "changed development query"
    write_jsonl(path, rows)
    with pytest.raises(EvaluationIntegrityError, match="not frozen"):
        load_development_for_tuning(fixture)


def test_ground_truth_relevant_and_excluded_overlap_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    path = fixture / "ground_truth.development.jsonl"
    rows = read_jsonl(path)
    rows[0]["expected_exclusion_source_ids"] = rows[0]["expected_relevant_source_ids"]
    write_jsonl(path, rows)
    with pytest.raises(EvaluationIntegrityError, match="both relevant and excluded"):
        verify_evaluation_corpus(fixture)


def test_receipt_row_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    path = fixture / "holdout-access-receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["rows_read"] = 19
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(EvaluationIntegrityError, match="row evidence"):
        verify_evaluation_corpus(fixture)


def test_canonical_datetime_serialization_matches_across_processes() -> None:
    code = (
        "from datetime import UTC, datetime, timezone; "
        "from power_framework.core.context_contracts import BitemporalEvidence; "
        "item=BitemporalEvidence(observed_at=datetime(2026,1,1,tzinfo=UTC), "
        "recorded_at=datetime(2026,1,1,2,tzinfo=timezone.utc)); "
        "print(item.to_canonical_json()); print(item.digest())"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    outputs = []
    for seed in ("1", "2"):
        process = subprocess.run(  # noqa: S603 -- fixed interpreter and source.
            [sys.executable, "-c", code],
            env={**env, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=False,
        )
        assert process.returncode == 0, process.stderr
        outputs.append(process.stdout)
    assert outputs[0] == outputs[1]


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
