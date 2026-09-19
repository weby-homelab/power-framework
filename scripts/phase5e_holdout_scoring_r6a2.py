"""R6A.2 ground-truth-only scoring stage.

The scorer consumes an already frozen raw-output artifact and verified GT.  It
contains no ApplicationService, RetrievalPlanner, or retrieval client import by
design: scoring cannot execute a second retrieval epoch.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

from pydantic import Field, StrictFloat, StrictInt

from power_framework.core.context_contracts import Digest, RuntimeModel, canonical_sha256
from power_framework.core.evaluation_contracts import (
    EvaluationGroundTruth,
    SealedRevisionSpec,
    load_bounded_json,
    load_verified_holdout_ground_truth_for_scoring,
    validate_sealed_revision_spec,
)
from power_framework.core.evaluation_execution import EpochBinding, RawRetrievalOutputArtifact


class RawOutputScoringArtifact(RuntimeModel):
    """Metrics bound to raw output, GT, and the metric contract only."""

    schema_version: Literal["power.retrieval-scoring.v1"] = "power.retrieval-scoring.v1"
    evaluation_revision: str = Field(pattern=r"^v1(?:\.[0-9]+)?$")
    raw_output_digest: Digest
    ground_truth_digest: Digest
    metric_contract_digest: Digest
    query_count: StrictInt = Field(ge=1)
    recall_at_5: StrictFloat = Field(ge=0, le=1)
    mrr: StrictFloat = Field(ge=0, le=1)
    map: StrictFloat = Field(ge=0, le=1)
    ndcg_at_10: StrictFloat = Field(ge=0, le=1)
    exclusion_leaks: StrictInt = Field(ge=0)


def _recall_at_k(returned: list[str], relevant: set[str], k: int) -> float:
    return len(set(returned[:k]) & relevant) / len(relevant) if relevant else 0.0


def _mrr(returned: list[str], relevant: set[str]) -> float:
    for index, source_id in enumerate(returned, start=1):
        if source_id in relevant:
            return 1.0 / index
    return 0.0


def _average_precision(returned: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    hits = 0
    total = 0.0
    for index, source_id in enumerate(returned, start=1):
        if source_id in relevant:
            hits += 1
            total += hits / index
    return total / len(relevant)


def _ndcg_at_k(returned: list[str], graded: Mapping[str, int], k: int) -> float:
    def gain(relevance: int) -> float:
        return float((2**relevance) - 1)

    dcg = sum(
        gain(graded.get(source_id, 0)) / math.log2(index + 2)
        for index, source_id in enumerate(returned[:k])
    )
    ideal = sorted((gain(value) for value in graded.values()), reverse=True)[:k]
    idcg = sum(value / math.log2(index + 2) for index, value in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def _ground_truth_digest(rows: tuple[EvaluationGroundTruth, ...]) -> str:
    return canonical_sha256(
        {
            "ground_truth": [
                row.to_canonical_dict() for row in sorted(rows, key=lambda item: item.query_id)
            ]
        }
    )


def score_raw_output_artifact(
    *,
    raw_output_path: Path,
    eval_corpus: Path,
    expected_revision: str,
    revision_spec: SealedRevisionSpec | Mapping[str, Any],
    metric_contract_digest: str,
    epoch_receipt_path: Path,
    epoch_binding: EpochBinding,
) -> RawOutputScoringArtifact:
    """Score only an immutable raw output; no retrieval call is available here."""

    if not re.fullmatch(r"[0-9a-f]{64}", metric_contract_digest):
        raise ValueError("metric_contract_digest must be a lowercase SHA-256 digest")
    if metric_contract_digest != epoch_binding.metric_contract_digest:
        raise ValueError("metric contract digest does not match the one-shot epoch binding")
    spec = validate_sealed_revision_spec(revision_spec)
    raw = RawRetrievalOutputArtifact.model_validate(load_bounded_json(raw_output_path))
    raw_digest = raw.digest()
    if raw.evaluation_revision != expected_revision or raw.revision_spec_digest != spec.digest():
        raise ValueError("raw output is not bound to the requested candidate revision")
    ground_truth = load_verified_holdout_ground_truth_for_scoring(
        eval_corpus,
        expected_revision=expected_revision,
        revision_spec=spec,
        raw_output_path=raw_output_path,
        epoch_receipt_path=epoch_receipt_path,
        raw_output_digest=raw_digest,
        expected_epoch_fields=epoch_binding.model_dump(mode="python"),
    )
    by_query = {row.query_id: row for row in ground_truth}
    if {record.query_id for record in raw.records} != set(by_query):
        raise ValueError("raw output query scope does not match verified holdout GT")
    recall_values: list[float] = []
    mrr_values: list[float] = []
    map_values: list[float] = []
    ndcg_values: list[float] = []
    exclusion_leaks = 0
    for record in raw.records:
        row = by_query[record.query_id]
        relevant = set(row.expected_relevant_source_ids)
        graded = {grade.source_id: grade.relevance for grade in row.graded_relevance}
        returned = list(record.shadow_candidate_ids)
        recall_values.append(_recall_at_k(returned, relevant, 5))
        mrr_values.append(_mrr(returned, relevant))
        map_values.append(_average_precision(returned, relevant))
        ndcg_values.append(_ndcg_at_k(returned, graded, 10))
        exclusion_leaks += sum(
            1 for source_id in returned[:10] if source_id in set(row.expected_exclusion_source_ids)
        )
    count = len(raw.records)
    return RawOutputScoringArtifact(
        evaluation_revision=expected_revision,
        raw_output_digest=raw_digest,
        ground_truth_digest=_ground_truth_digest(ground_truth),
        metric_contract_digest=metric_contract_digest,
        query_count=count,
        recall_at_5=sum(recall_values) / count,
        mrr=sum(mrr_values) / count,
        map=sum(map_values) / count,
        ndcg_at_10=sum(ndcg_values) / count,
        exclusion_leaks=exclusion_leaks,
    )


__all__ = ["RawOutputScoringArtifact", "score_raw_output_artifact"]
