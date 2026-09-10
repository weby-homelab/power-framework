"""Frozen POWER 3.8 evaluation-corpus integrity tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from power_framework.core.evaluation_contracts import (
    EvaluationIntegrityError,
    load_development_for_tuning,
    reject_holdout_tuning,
    verify_evaluation_corpus,
)

evaluation_contracts = sys.modules[EvaluationIntegrityError.__module__]

ROOT = Path(__file__).parents[1] / "benchmarks" / "power38" / "retrieval_eval" / "v1"
ACTIVE_ROOT = Path(__file__).parents[1] / "benchmarks" / "power38" / "retrieval_eval" / "v1.1"
EXPECTED = {
    "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
    "dataset_digest": "179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0",
    "query_set_digest": "7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086",
    "development_digest": "29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289",
    "holdout_digest": "ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a",
    "disjointness_digest": "554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275",
}
ACTIVE_EXPECTED = {
    "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
    "dataset_digest": "d3e9f0c0697e18572d9149a9c38bf6b02b72b44927d0fab481bd9cd74203fc4d",
    "query_set_digest": "b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e",
    "development_digest": "4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95",
    "holdout_digest": "61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551",
    "disjointness_digest": "cf8054395040f17e4d21a005e248b7804fd515cc555b12b52b0afca0f32376d4",
    "semantic_adjudication_digest": "0c1c2b32cb6ad84413dddfc93fe73777a37ba735468614a49afd97fc11784c48",
    "semantic_adjudication_markdown_digest": "7ee822bdb11db3497bf0057fe1df3a4aa9eb5ddfa44ce1e5db191bf5f3f24c60",
    "holdout_access_receipt_digest": "e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997",
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


def test_historical_v1_remains_verifiable_but_is_not_active() -> None:
    result = verify_evaluation_corpus(ROOT)

    assert result["evaluation_revision"] == "v1"
    assert result["semantic_adjudication_status"] == "SUPERSEDED_ERRATUM"
    assert evaluation_contracts.ACTIVE_EVALUATION_REVISION == "v1.1"


def test_active_v11_revision_verifies_with_reproducible_digests() -> None:
    first = verify_evaluation_corpus(ACTIVE_ROOT)
    second = verify_evaluation_corpus(ACTIVE_ROOT)

    assert first == second
    assert {key: first[key] for key in ACTIVE_EXPECTED} == ACTIVE_EXPECTED
    assert first["evaluation_revision"] == "v1.1"
    assert first["semantic_adjudication_status"] == "PASS"
    assert first["source_count"] == 20
    assert first["development_query_count"] == 20
    assert first["holdout_query_count"] == 20


def test_active_revision_semantic_design_evidence_covers_corrections() -> None:
    records = json.loads((ACTIVE_ROOT / "semantic-adjudication.json").read_text(encoding="utf-8"))[
        "records"
    ]
    by_id = {record["query_id"]: record for record in records}
    development_gt = {
        row["query_id"]: row for row in read_jsonl(ACTIVE_ROOT / "ground_truth.development.jsonl")
    }
    holdout_gt = {
        row["query_id"]: row for row in read_jsonl(ACTIVE_ROOT / "ground_truth.holdout.jsonl")
    }

    assert len(records) == 40
    assert {record["query_id"] for record in records} == {
        row["query_id"]
        for path in ("queries.development.jsonl", "queries.holdout.jsonl")
        for row in read_jsonl(ACTIVE_ROOT / path)
    }
    assert {record["verdict"] for record in records} == {"PASS"}

    for query_id in ("p38-ho-q06", "p38-ho-q11", "p38-ho-q16"):
        assert by_id[query_id]["action"] == "REWRITE_QUERY"
        assert by_id[query_id]["verdict"] == "PASS"
    for prefix in ("p38-dev", "p38-ho"):
        for suffix in ("q10", "q14", "q15"):
            query_id = f"{prefix}-{suffix}"
            assert by_id[query_id]["verdict"] == "PASS"
            gt = development_gt.get(query_id) or holdout_gt[query_id]
            assert gt["expected_disposition"] == "QUARANTINE"
            assert gt["temporal_expectation"] == "not_applicable"
    for query_id in ("p38-dev-q20", "p38-ho-q20"):
        assert by_id[query_id]["action"] == "REWRITE_QUERY"
        assert by_id[query_id]["verdict"] == "PASS"
    for query_id in ("p38-dev-q19", "p38-ho-q19"):
        assert by_id[query_id]["action"] == "CHANGE_GROUND_TRUTH"
        assert by_id[query_id]["verdict"] == "PASS"
        gt = development_gt.get(query_id) or holdout_gt[query_id]
        assert gt["expected_relevant_source_ids"] == ["p38-src-infra-current"]
        assert gt["graded_relevance"] == [
            {
                "authority_outcome": "prefer",
                "relevance": 3,
                "source_id": "p38-src-infra-current",
            }
        ]


def test_active_manifest_is_valid_against_declared_planning_schema() -> None:
    planning_schema = Path(__file__).parents[1] / "artifacts" / "project-state" / "planning"
    schema = json.loads((planning_schema / "retrieval-eval-v1.schema.json").read_text())
    manifest = json.loads((ACTIVE_ROOT / "manifest.json").read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(manifest)


def test_active_semantic_adjudication_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = tmp_path / "eval"
    shutil.copytree(ACTIVE_ROOT, fixture)
    path = fixture / "semantic-adjudication.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["records"][0]["rationale_ref"] = "adjudication-r40"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(EvaluationIntegrityError, match="semantic adjudication"):
        verify_evaluation_corpus(fixture)


def test_active_holdout_receipt_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = tmp_path / "eval"
    shutil.copytree(ACTIVE_ROOT, fixture)
    path = fixture / "holdout-access-receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["accessed_at"] = "2026-09-10T19:00:00.000000Z"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(EvaluationIntegrityError, match="receipt digest"):
        verify_evaluation_corpus(fixture)


def test_active_v11_extra_root_artifact_fails_closed(tmp_path: Path) -> None:
    fixture = tmp_path / "eval"
    shutil.copytree(ACTIVE_ROOT, fixture)
    (fixture / "unlisted.json").write_text("{}", encoding="utf-8")

    with pytest.raises(EvaluationIntegrityError, match="root bytes or inventory"):
        verify_evaluation_corpus(fixture)


def test_verifier_rejects_non_regular_and_oversized_artifacts(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO fixtures require POSIX")

    (tmp_path / "fifo").mkdir()
    fifo_fixture = copied_fixture(tmp_path / "fifo")
    manifest = fifo_fixture / "manifest.json"
    manifest.unlink()
    os.mkfifo(manifest)
    with pytest.raises(EvaluationIntegrityError, match="regular file"):
        verify_evaluation_corpus(fifo_fixture)

    (tmp_path / "large").mkdir()
    large_fixture = copied_fixture(tmp_path / "large")
    (large_fixture / "manifest.json").write_bytes(b"0" * (evaluation_contracts.MAX_FILE_BYTES + 1))
    with pytest.raises(EvaluationIntegrityError, match="byte bound"):
        verify_evaluation_corpus(large_fixture)


def test_ground_truth_files_reject_cross_split_records(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    development = fixture / "ground_truth.development.jsonl"
    holdout = fixture / "ground_truth.holdout.jsonl"
    development_bytes = development.read_bytes()
    holdout_bytes = holdout.read_bytes()
    development.write_bytes(holdout_bytes)
    holdout.write_bytes(development_bytes)

    with pytest.raises(EvaluationIntegrityError, match="different split"):
        verify_evaluation_corpus(fixture)


def test_historical_v1_root_artifact_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = copied_fixture(tmp_path)
    (fixture / "README.md").write_text(
        (fixture / "README.md").read_text(encoding="utf-8") + "\nchanged\n",
        encoding="utf-8",
    )

    with pytest.raises(EvaluationIntegrityError, match="historical v1"):
        verify_evaluation_corpus(fixture)


def test_cli_verifies_explicit_historical_and_active_revisions() -> None:
    script = Path(__file__).parents[1] / "scripts" / "verify_retrieval_eval.py"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    process = subprocess.run(  # noqa: S603 -- fixed local verifier and fixtures.
        [sys.executable, str(script), str(ROOT), "--expected-revision", "v1"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["semantic_adjudication_status"] == "SUPERSEDED_ERRATUM"

    active = subprocess.run(  # noqa: S603 -- fixed local verifier and fixtures.
        [sys.executable, str(script), str(ACTIVE_ROOT), "--expected-revision", "v1.1"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert active.returncode == 0
    assert json.loads(active.stdout)["semantic_adjudication_status"] == "PASS"

    wrong_revision = subprocess.run(  # noqa: S603 -- fixed local verifier and fixtures.
        [sys.executable, str(script), str(ACTIVE_ROOT), "--expected-revision", "v1"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert wrong_revision.returncode == 1
    assert json.loads(wrong_revision.stdout)["error_code"] == "revision_mismatch"

    wrong_tuning_revision = subprocess.run(  # noqa: S603 -- fixed local verifier and fixtures.
        [
            sys.executable,
            str(script),
            str(ROOT),
            "--mode",
            "tuning",
            "--expected-revision",
            "v1.1",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert wrong_tuning_revision.returncode == 1
    assert json.loads(wrong_tuning_revision.stdout)["error_code"] == "revision_mismatch"

    active_wrong_tuning_revision = subprocess.run(  # noqa: S603 -- fixed local verifier and fixtures.
        [
            sys.executable,
            str(script),
            str(ACTIVE_ROOT),
            "--mode",
            "tuning",
            "--expected-revision",
            "v1",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert active_wrong_tuning_revision.returncode == 1
    assert json.loads(active_wrong_tuning_revision.stdout)["error_code"] == "revision_mismatch"


def test_cli_receipt_output_uses_verified_active_snapshot(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "verify_retrieval_eval.py"
    receipt_path = tmp_path / "receipt.json"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}

    process = subprocess.run(  # noqa: S603 -- fixed local verifier and fixtures.
        [
            sys.executable,
            str(script),
            str(ACTIVE_ROOT),
            "--expected-revision",
            "v1.1",
            "--receipt-out",
            str(receipt_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0
    result = json.loads(process.stdout)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result["receipt_generated"] is True
    assert result["receipt_digest"]
    assert receipt["dataset_revision"] == result["dataset_digest"]
    assert receipt["query_set_digest"] == result["query_set_digest"]
    assert receipt["rows_read"] == 40


def test_historical_v1_bytes_match_the_immutability_baseline() -> None:
    proof_path = (
        Path(__file__).parents[1]
        / "artifacts"
        / "project-state"
        / "phase-5a"
        / "v1-immutability-proof.json"
    )
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    actual_paths = sorted(
        path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()
    )

    assert proof["status"] == "PASS"
    assert proof["file_count"] == len(actual_paths)
    assert proof["v1_file_sha256"] == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in actual_paths
    }


def test_active_revision_development_tuning_loader_keeps_holdout_separate() -> None:
    assert len(load_development_for_tuning(ACTIVE_ROOT)) == 20
    with pytest.raises(EvaluationIntegrityError, match="holdout cannot"):
        reject_holdout_tuning("holdout")


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
