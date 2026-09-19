"""R6A.2 execution-admission tests using synthetic, non-benchmark fixtures only."""

from __future__ import annotations

import hashlib
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from pydantic import ValidationError

from power_framework.core import evaluation_contracts
from power_framework.core.context_contracts import canonical_sha256
from power_framework.core.evaluation_contracts import (
    EVALUATION_REVISION_REGISTRY,
    EvaluationGroundTruth,
    EvaluationIntegrityError,
    GroundTruthGrade,
    SealedRevisionFile,
    SealedRevisionSpec,
    TemporalExpectation,
    register_evaluation_revision,
)
from power_framework.core.evaluation_execution import (
    EpochBinding,
    HoldoutExecutionDescriptor,
    OneShotEpochGuard,
    OneShotEvaluationEpochReceipt,
    QueryOnlyRecord,
    RawRetrievalOutputArtifact,
    RawRetrievalOutputRecord,
    VerifiedHoldoutExecution,
    execute_query_only_once,
    write_raw_output_artifact,
)
from scripts import phase5e_holdout_scoring_r6a2 as scoring
from scripts import phase5e_holdout_stage_a_r6a2 as stage_a


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _spec(*, revision: str = "v1.6") -> SealedRevisionSpec:
    files = [
        SealedRevisionFile(
            path="ground_truth.development.jsonl", sha256=_digest("dev-gt"), byte_size=1
        ),
        SealedRevisionFile(path="ground_truth.holdout.jsonl", sha256=_digest("ho-gt"), byte_size=1),
        SealedRevisionFile(path="manifest.json", sha256=_digest("manifest"), byte_size=1),
        SealedRevisionFile(path="queries.development.jsonl", sha256=_digest("dev-q"), byte_size=1),
        SealedRevisionFile(path="queries.holdout.jsonl", sha256=_digest("ho-q"), byte_size=1),
    ]
    inventory_digest = canonical_sha256({"files": [item.to_canonical_dict() for item in files]})
    return SealedRevisionSpec(
        schema_version="power.retrieval-evaluation-revision-spec.v1",
        revision=revision,
        lifecycle_status="SEALED_NOT_SECRET_NO_TUNING",
        dataset_digest=_digest("dataset"),
        query_set_digest=_digest("queries"),
        development_digest=_digest("development"),
        holdout_digest=_digest("holdout"),
        source_corpus_digest=_digest("sources"),
        source_metadata_digest=_digest("source-metadata"),
        disjointness_digest=_digest("disjointness"),
        disjointness_proof_ref="disjointness-proof.json",
        provenance_source_ref="ground-truth-provenance",
        provenance_method="human_adjudicated",
        semantic_adjudication_digest=_digest("adjudication"),
        semantic_adjudication_markdown_digest=_digest("adjudication-markdown"),
        review_contract_version="power.retrieval-semantic-review.v2",
        capability_contract_revision="power.retrieval-fast-capability.v1",
        review_a_ref="semantic-review-a.json",
        review_a_digest=_digest("review-a"),
        review_b_ref="semantic-review-b.json",
        review_b_digest=_digest("review-b"),
        holdout_integrity_receipt_ref="holdout-access-receipt.json",
        holdout_integrity_receipt_digest=_digest("holdout-receipt"),
        semantic_adjudication_ref="semantic-adjudication.json",
        sealed_artifact_ref="synthetic-sealed-artifact",
        root_inventory=files,
        root_inventory_digest=inventory_digest,
    )


def _binding() -> EpochBinding:
    return EpochBinding(
        evaluation_revision="v1.6",
        revision_spec_digest=_spec().digest(),
        dataset_digest=_digest("dataset"),
        query_set_digest=_digest("queries"),
        holdout_digest=_digest("holdout"),
        source_corpus_digest=_digest("sources"),
        r6a2_freeze_digest=_digest("freeze"),
        r6a2_freeze_ref="artifacts/phase5e_protocol_r6a2_freeze.json",
        runtime_digest=_digest("runtime"),
        execution_runner_digest=_digest("runner"),
        fixture_digest=_digest("fixture"),
        ownership_contract_digest=_digest("ownership"),
        fast_capability_contract_digest=_digest("fast"),
        metric_contract_digest=_digest("metric"),
    )


def _receipt() -> OneShotEvaluationEpochReceipt:
    return OneShotEvaluationEpochReceipt.start(binding=_binding())


def _record(query_id: str = "p38-ho-q01") -> RawRetrievalOutputRecord:
    return RawRetrievalOutputRecord(
        query_id=query_id,
        legacy_candidate_ids=["source-a"],
        shadow_candidate_ids=["source-a"],
        shadow_candidates=[],
        latency_ms=1.0,
        token_cost=2,
        pack_bytes=3,
        security_observations={"scope_escape": 0, "query_side_writes": 0},
    )


def test_candidate_spec_rejects_historical_override() -> None:
    with pytest.raises(ValidationError):
        _spec(revision="v1.4")
    with pytest.raises(ValidationError):
        _spec(revision="v1.5")


def test_historical_registry_cannot_be_mutated_by_registration() -> None:
    before = tuple(EVALUATION_REVISION_REGISTRY)
    with pytest.raises(EvaluationIntegrityError, match="explicit sealed revision spec"):
        register_evaluation_revision("v1.6", {"digests": {}}, override=True)
    assert tuple(EVALUATION_REVISION_REGISTRY) == before


def test_candidate_spec_rejects_unsafe_inventory_path() -> None:
    with pytest.raises(ValidationError):
        SealedRevisionFile(path="../outside.json", sha256=_digest("x"), byte_size=1)


def test_candidate_spec_accepts_nested_repository_relative_inventory_path() -> None:
    item = SealedRevisionFile(path="corpus/source.md", sha256=_digest("x"), byte_size=1)
    assert item.path == "corpus/source.md"


def test_candidate_spec_rejects_inventory_digest_mismatch() -> None:
    values = {
        key: value for key, value in _spec().model_dump(mode="python").items() if value is not None
    }
    values["root_inventory_digest"] = _digest("wrong")
    with pytest.raises(ValidationError):
        SealedRevisionSpec.model_validate(values)


def test_epoch_receipt_has_no_ground_truth_or_raw_query_fields() -> None:
    with pytest.raises(ValidationError):
        OneShotEvaluationEpochReceipt.model_validate(
            {**_receipt().model_dump(mode="python"), "ground_truth": []}
        )


def test_query_only_record_has_no_ground_truth_fields() -> None:
    fields = set(QueryOnlyRecord.model_fields)
    assert "expected_relevant_source_ids" not in fields
    assert "expected_authority_winner" not in fields
    assert "reason" not in fields


def test_raw_output_contract_rejects_ground_truth_fields() -> None:
    with pytest.raises(ValidationError):
        RawRetrievalOutputArtifact(
            schema_version="power.retrieval-raw-output.v1",
            evaluation_revision="v9.9",
            revision_spec_digest=_spec().digest(),
            query_set_digest=_digest("queries"),
            source_corpus_digest=_digest("sources"),
            runtime_digest=_digest("runtime"),
            execution_runner_digest=_digest("runner"),
            fixture_digest=_digest("fixture"),
            records=[{**_record().model_dump(mode="python"), "ground_truth": {}}],
        )


def test_atomic_guard_allows_one_and_rejects_second(tmp_path: Path) -> None:
    receipt = _receipt()
    guard = OneShotEpochGuard.acquire(tmp_path, receipt, allowed_root=tmp_path)
    guard.interrupt()
    with pytest.raises(EvaluationIntegrityError, match="epoch"):
        OneShotEpochGuard.acquire(tmp_path, receipt, allowed_root=tmp_path)


def test_concurrent_guard_acquisition_has_exactly_one_winner(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    winners: list[OneShotEpochGuard] = []
    failures: list[Exception] = []

    def attempt() -> None:
        try:
            barrier.wait()
            winners.append(OneShotEpochGuard.acquire(tmp_path, _receipt(), allowed_root=tmp_path))
        except Exception as exc:  # pragma: no cover - assertion below records the race
            failures.append(exc)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert len(failures) == 1
    winners[0].interrupt()


def test_same_epoch_binding_is_rejected_in_a_second_output_directory(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    guard = OneShotEpochGuard.acquire(first, _receipt(), allowed_root=tmp_path)
    with pytest.raises(EvaluationIntegrityError, match="epoch"):
        OneShotEpochGuard.acquire(second, _receipt(), allowed_root=tmp_path)
    guard.interrupt()


def test_executor_requires_explicit_one_shot_intent(tmp_path: Path) -> None:
    prepared = (QueryOnlyRecord(query_id="p38-ho-q01", query="synthetic", budget_class="FAST"),)
    with pytest.raises(EvaluationIntegrityError, match="one-shot"):
        execute_query_only_once(
            queries=prepared,
            binding=_binding(),
            output_root=tmp_path,
            allowed_root=tmp_path,
            one_shot_intent="development",
            executor=lambda query: _record(query.query_id),
        )


def test_failure_after_guard_consumes_epoch_without_retry(tmp_path: Path) -> None:
    prepared = (QueryOnlyRecord(query_id="p38-ho-q01", query="synthetic", budget_class="FAST"),)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        execute_query_only_once(
            queries=prepared,
            binding=_binding(),
            output_root=tmp_path,
            allowed_root=tmp_path,
            one_shot_intent="fresh_holdout_one_shot",
            executor=lambda query: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
        )
    with pytest.raises(EvaluationIntegrityError, match="epoch"):
        execute_query_only_once(
            queries=prepared,
            binding=_binding(),
            output_root=tmp_path,
            allowed_root=tmp_path,
            one_shot_intent="fresh_holdout_one_shot",
            executor=lambda query: _record(query.query_id),
        )


def test_executor_never_receives_ground_truth(tmp_path: Path) -> None:
    prepared = (QueryOnlyRecord(query_id="p38-ho-q01", query="synthetic", budget_class="FAST"),)
    seen: list[QueryOnlyRecord] = []

    def executor(query: QueryOnlyRecord) -> RawRetrievalOutputRecord:
        seen.append(query)
        assert not hasattr(query, "expected_relevant_source_ids")
        return _record(query.query_id)

    artifact, receipt = execute_query_only_once(
        queries=prepared,
        binding=_binding(),
        output_root=tmp_path,
        allowed_root=tmp_path,
        one_shot_intent="fresh_holdout_one_shot",
        executor=executor,
    )

    assert seen == list(prepared)
    assert artifact.digest() == receipt.raw_output_digest
    assert receipt.status == "COMPLETED_PASS"


def test_fixture_setup_failure_happens_before_guard_or_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prepared = VerifiedHoldoutExecution(
        queries=(QueryOnlyRecord(query_id="p38-ho-q01", query="synthetic"),),
        descriptor=HoldoutExecutionDescriptor(
            evaluation_revision="v1.6",
            revision_spec_digest=_spec().digest(),
            dataset_digest=_digest("dataset"),
            query_set_digest=_digest("queries"),
            holdout_digest=_digest("holdout"),
            source_corpus_digest=_digest("sources"),
            query_count=1,
        ),
    )
    monkeypatch.setattr(
        stage_a, "prepare_verified_holdout_execution", lambda *args, **kwargs: prepared
    )
    calls = 0

    def failing_setup(_: HoldoutExecutionDescriptor) -> Any:
        nonlocal calls
        calls += 1
        raise RuntimeError("fixture fidelity failure")

    with pytest.raises(RuntimeError, match="fixture fidelity"):
        stage_a.run_verified_holdout_stage_a(
            eval_corpus=tmp_path,
            expected_revision="v1.6",
            revision_spec=_spec(),
            binding=_binding(),
            output_root=tmp_path,
            allowed_root=tmp_path,
            one_shot_intent="fresh_holdout_one_shot",
            fixture_setup=failing_setup,
        )

    assert calls == 1
    assert not (tmp_path / "one-shot-epoch.json").exists()


def test_verification_failure_happens_before_guard_or_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def failing_prepare(*args: object, **kwargs: object) -> VerifiedHoldoutExecution:
        raise EvaluationIntegrityError("revision_inventory", "synthetic verification failure")

    monkeypatch.setattr(stage_a, "prepare_verified_holdout_execution", failing_prepare)
    calls = 0

    def fixture_setup(_: HoldoutExecutionDescriptor) -> Any:
        nonlocal calls
        calls += 1
        return lambda query: _record(query.query_id)

    with pytest.raises(EvaluationIntegrityError, match="verification"):
        stage_a.run_verified_holdout_stage_a(
            eval_corpus=tmp_path,
            expected_revision="v1.6",
            revision_spec=_spec(),
            binding=_binding(),
            output_root=tmp_path,
            allowed_root=tmp_path,
            one_shot_intent="fresh_holdout_one_shot",
            fixture_setup=fixture_setup,
        )

    assert calls == 0
    assert not (tmp_path / "one-shot-epoch.json").exists()


def test_explicit_inventory_rejects_symlink(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    target = corpus / "real.md"
    target.write_text("safe", encoding="utf-8")
    link = corpus / "link.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable in this environment")
    item = SealedRevisionFile(path="link.md", sha256=_digest("safe"), byte_size=4)
    values = {
        key: value for key, value in _spec().model_dump(mode="python").items() if value is not None
    }
    values["root_inventory"] = [item]
    values["root_inventory_digest"] = canonical_sha256({"files": [item.to_canonical_dict()]})
    candidate = SealedRevisionSpec.model_validate(values)
    with pytest.raises(EvaluationIntegrityError, match="symlink"):
        evaluation_contracts._check_explicit_revision_inventory(corpus, candidate)


def test_scoring_loads_gt_only_after_raw_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = RawRetrievalOutputArtifact(
        schema_version="power.retrieval-raw-output.v1",
        evaluation_revision="v1.6",
        revision_spec_digest=_spec().digest(),
        query_set_digest=_digest("queries"),
        source_corpus_digest=_digest("sources"),
        runtime_digest=_digest("runtime"),
        execution_runner_digest=_digest("runner"),
        fixture_digest=_digest("fixture"),
        records=[_record()],
    )
    guard = OneShotEpochGuard.acquire(tmp_path, _receipt(), allowed_root=tmp_path)
    raw_path = write_raw_output_artifact(artifact, output_root=tmp_path, allowed_root=tmp_path)
    guard.complete(raw_output_digest=artifact.digest(), raw_output_ref=raw_path.name)
    gt = EvaluationGroundTruth(
        query_id="p38-ho-q01",
        expected_relevant_source_ids=["source-a"],
        graded_relevance=[
            GroundTruthGrade(source_id="source-a", relevance=3, authority_outcome="prefer")
        ],
        expected_exclusion_source_ids=[],
        temporal_expectation=TemporalExpectation.CURRENT,
        reason="synthetic scoring test",
        provenance_ref="synthetic",
        provenance_digest=_digest("gt"),
    )
    observed_digest: list[str] = []

    def fake_gt_loader(*args: object, **kwargs: object) -> tuple[EvaluationGroundTruth, ...]:
        observed_digest.append(str(kwargs["raw_output_digest"]))
        return (gt,)

    monkeypatch.setattr(scoring, "load_verified_holdout_ground_truth_for_scoring", fake_gt_loader)
    result = scoring.score_raw_output_artifact(
        raw_output_path=raw_path,
        eval_corpus=tmp_path,
        expected_revision="v1.6",
        revision_spec=_spec(),
        metric_contract_digest=_digest("metric"),
        epoch_receipt_path=tmp_path / "one-shot-epoch.json",
        epoch_binding=_binding(),
    )

    assert observed_digest == [artifact.digest()]
    assert result.raw_output_digest == artifact.digest()
    assert result.recall_at_5 == 1.0
    assert not hasattr(scoring, "ApplicationService")
