"""POWER 3.8 frozen retrieval-evaluation contracts and offline verifier.

The verifier is intentionally file-bounded and offline.  It validates a
repository-owned synthetic fixture; it never loads a model, calls a network
client, executes corpus text, or treats holdout labels as tuning input.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from .context_contracts import (
    Authority,
    AwareDateTime,
    Digest,
    Identifier,
    NoiseDisposition,
    OpaqueReference,
    QueryIntentKind,
    RuntimeModel,
    SensitivityClass,
    ShortText,
    SourceReference,
    TrustState,
    canonical_bytes,
    canonical_sha256,
    register_runtime_contract,
    validate_trust_authority,
)

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_JSONL_RECORD_BYTES = 64 * 1024
MAX_JSONL_RECORDS = 4096
_QUERY_ID_PATTERN = re.compile(r"^p38-(?:dev|ho)-q[0-9]{2}$")
_FORBIDDEN_SYNTHETIC_MARKERS = (
    "/root/",
    "-----begin private key-----",
    "github_release_token=",
    "aws_secret_access_key",
)
FROZEN_PHASE5A_DIGESTS = {
    "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
    "dataset_digest": "179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0",
    "query_set_digest": "7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086",
    "development_digest": "29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289",
    "holdout_digest": "ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a",
    "disjointness_digest": "554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275",
}
FROZEN_PHASE5A_COUNTS = {"sources": 20, "development_queries": 20, "holdout_queries": 20}
ACTIVE_EVALUATION_REVISION = "v1.1"
HISTORICAL_V1_FILE_SHA256 = {
    "README.md": "b4742b926212d76a156fa0ce74208551554c3ebc4d468688cb0db93e03dddf9c",
    "corpus/p38-src-code-en.md": "6e2afab08afad604560d02bc0bdac57c2e64561b41e036c33aa97f1ccffc4f3d",
    "corpus/p38-src-code-ua.md": "78c069eae85f6ddff14a249d05e3f640a1fd0210d0ef5117f8e5fbc63a54c478",
    "corpus/p38-src-contradiction-canonical.md": "ad26827f1728789f77c645c4a773261b23ccd11987ab50ad76b4a35483305e59",
    "corpus/p38-src-contradiction-raw.md": "4ab3cda9776457bda38fe49dbed14cfbaffc5332367ac64678b7f336d74f1bc4",
    "corpus/p38-src-cross-domain.md": "024fead7cfc087304264a29b8ffb1404c0ba732ee035fbac9f0667232d8d55ed",
    "corpus/p38-src-decision-current.md": "f23e14ca7b3827c5cb1f72f64b3a94b95e3a7d04c81eaea6175ce072df940923",
    "corpus/p38-src-decision-old.md": "893e9cabd2728942907abec377d46b7cd2303e40bc627b55f12471acfa7bf5c7",
    "corpus/p38-src-decision-raw.md": "692ec5410735116a9b0137a636932bbe501f89b2ef8bbcda9739c747ea5bb889",
    "corpus/p38-src-hard-negative.md": "953041221895f577ba835d81a760e3fe4136d62667fc8b4ad6db4b014be6814d",
    "corpus/p38-src-infra-current.md": "c55d82f3587cd15b25afd8d3666e5ec06eece83410f7e794c3f5baf4f8376fdf",
    "corpus/p38-src-infra-stale.md": "e76539faafbddf2edda5c65947e4da584bc313e9c61828a3334a72075da04383",
    "corpus/p38-src-noise-injection.md": "51d2e89657ee0f794d43edefe87dfcc75c3ff1e4991628e193044ac976b8ee59",
    "corpus/p38-src-project-current-ua.md": "0a2c82a84528dfbbaf5da825bfe4b04bab5ee613adb2ad5497ff12d232c42f49",
    "corpus/p38-src-project-current.md": "5a5b8fa65a46a6e015026ffefc4e76cc3bb46ab9287917ce2f22460de359c3e8",
    "corpus/p38-src-project-raw-chat.md": "df8b10e45dd223c819a650373f84917a8b03d8ed949670d228ba4cc76f207f7d",
    "corpus/p38-src-project-superseded.md": "56c7a6e50f054908410b4acb9a2d9c217a0236ef7e37e2162c3eae98f54d3c00",
    "corpus/p38-src-research-curated.md": "ce464c98b9d4d40ef3fedb8753683a172a48cafc9f21eaac9c53336f3579116c",
    "corpus/p38-src-research-unverified.md": "c156396d712146854df8c0b4a11b56054c1aa02df59d398a11a12494b1151995",
    "corpus/p38-src-task-current.md": "b3f5c0072e4d08baed59a288096c8759f1d64c5df595829466147a799c669512",
    "corpus/p38-src-task-raw.md": "b2213109a1d8bb18bc6bdeb3f86cf65aeedac397476dafd9ed3c06b713f35fc9",
    "disjointness-proof.json": "f26234f8c805f4738097f1bde9366440f8bea40541602c94ca4ed12502b912a2",
    "ground_truth.development.jsonl": "611ef7aeaecbdbfd0d05a35f30a69761506a31d5c5bf387fa43959361de0660e",
    "ground_truth.holdout.jsonl": "eab969fd51fcdf6639602b387b70a20a9d3c24347d34f4c4d7a89df2d8cbbe8a",
    "holdout-access-receipt.json": "4bf395636738a01d54d4f50569beb279d3a4a061ef4d26d30740e6b35eaf6e3a",
    "manifest.json": "b2b3e3412501c6f977b0f5a7accfcdb5d6931adecb889cf610acc9012cea85b5",
    "queries.development.jsonl": "8ba2d94e187d12919359093b5102b838514a46c9bdd6d74828b0f02ce5d45e44",
    "queries.holdout.jsonl": "b72143da332e32d96143c21c409000bb630ae460f867849fd47fe3698d33c8a7",
    "source_metadata.jsonl": "6b6d43f0ad3a63a0b4bd4b98f23c4bb74e700b4c3f480ad207dc622294be67c9",
}
ACTIVE_V11_ROOT_FILE_SHA256 = {
    "README.md": "c9aea87e0be8cad63e3dc69f7606aa302bd4033200e746fffb7da2fa0024fc23",
    "disjointness-proof.json": "1a648120b8d7fb245d590a2c0a106f331777bd3413a2c0a2c09ed62bbe465643",
    "ground_truth.development.jsonl": "470420a4441c6f707704a77938416ae06821a10b8eafcd34820eeca51c47d48b",
    "ground_truth.holdout.jsonl": "ed6d1e78bc24582302574d8940ee5b5a89eab1d61060cdaeefeb2a5ee134ea6d",
    "holdout-access-receipt.json": "e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997",
    "manifest.json": "f464c952124c5f2892e915a0ec8a349e57a4337246d275acfb1862fbfd535979",
    "queries.development.jsonl": "f4e3adcd0d99e578bca5092eb6f36f70b3f5de72dfd33295ca6465409f1eec9d",
    "queries.holdout.jsonl": "701cb69e5d4045a6134cf7f83725eab736f32d85ec90ff9396c08a50e91974c2",
    "semantic-adjudication.json": "7c1b91e7136fbe1b322ce73c01c72b1e2c794346aa8cbbeb75b5d627416dd5de",
    "semantic-adjudication.md": "7ee822bdb11db3497bf0057fe1df3a4aa9eb5ddfa44ce1e5db191bf5f3f24c60",
    "semantic-review-a-v1.1.json": "8d19e3c56ee2d85062ccebcbb6397dd0a8de7ec62c4a1df14d0a3630b15dc158",
    "semantic-review-b-v1.1.json": "14a4549f67b6efc40489a5e708fd0eafa35f464f94e5aa7d1153969db783c7b7",
    "source_metadata.jsonl": "6b6d43f0ad3a63a0b4bd4b98f23c4bb74e700b4c3f480ad207dc622294be67c9",
}
ACTIVE_PHASE5A1_DIGESTS = {
    "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
    "dataset_digest": "d3e9f0c0697e18572d9149a9c38bf6b02b72b44927d0fab481bd9cd74203fc4d",
    "query_set_digest": "b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e",
    "development_digest": "4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95",
    "holdout_digest": "61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551",
    "disjointness_digest": "cf8054395040f17e4d21a005e248b7804fd515cc555b12b52b0afca0f32376d4",
    "semantic_adjudication_digest": "0c1c2b32cb6ad84413dddfc93fe73777a37ba735468614a49afd97fc11784c48",
    "holdout_access_receipt_digest": "e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997",
}
EVALUATION_REVISION_REGISTRY: dict[str, dict[str, Any]] = {
    "v1": {
        "active": False,
        "digests": FROZEN_PHASE5A_DIGESTS,
        "semantic_status": "SUPERSEDED_ERRATUM",
        "refs": {
            "holdout_access_audit": "holdout-access-receipt-v1",
            "sealed_artifact_ref": "power38-holdout-v1-sealed",
            "disjointness_proof_ref": "disjointness-proof-v1",
            "provenance_source_ref": "power38-ground-truth-v1",
            "provenance_method": "synthetic_fixture",
            "source_corpus_digest": None,
            "semantic_adjudication_markdown_digest": None,
            "holdout_access_receipt_digest": None,
            "planning_only": None,
            "supersedes_revision": None,
            "semantic_adjudication_ref": None,
            "reviewer_a_receipt_ref": None,
            "reviewer_b_receipt_ref": None,
        },
    },
    "v1.1": {
        "active": True,
        "digests": ACTIVE_PHASE5A1_DIGESTS,
        "semantic_status": "PASS",
        "refs": {
            "holdout_access_audit": "holdout-access-receipt-v1.1",
            "sealed_artifact_ref": "power38-holdout-v1.1-sealed",
            "disjointness_proof_ref": "disjointness-proof-v1.1",
            "provenance_source_ref": "power38-ground-truth-v1.1",
            "provenance_method": "human_adjudicated",
            "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
            "semantic_adjudication_markdown_digest": "7ee822bdb11db3497bf0057fe1df3a4aa9eb5ddfa44ce1e5db191bf5f3f24c60",
            "holdout_access_receipt_digest": "e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997",
            "planning_only": True,
            "supersedes_revision": "v1",
            "semantic_adjudication_ref": "semantic-adjudication-v1.1",
            "reviewer_a_receipt_ref": "semantic-review-a-v1.1",
            "reviewer_b_receipt_ref": "semantic-review-b-v1.1",
        },
    },
}


class EvaluationLanguage(StrEnum):
    UA = "UA"
    EN = "EN"
    MIXED_UA_EN = "MIXED_UA_EN"


class EvaluationCategory(StrEnum):
    EXACT_LOOKUP = "EXACT_LOOKUP"
    PROJECT_STATE = "PROJECT_STATE"
    DECISION = "DECISION"
    TASK = "TASK"
    CODE = "CODE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    RESEARCH = "RESEARCH"
    CROSS_DOMAIN = "CROSS_DOMAIN"
    HISTORICAL_STALE = "HISTORICAL_STALE"
    SUPERSEDED = "SUPERSEDED"
    CONTRADICTION = "CONTRADICTION"
    NOISE = "NOISE"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    HARD_NEGATIVE = "HARD_NEGATIVE"
    AUTHORITY_CONFLICT = "AUTHORITY_CONFLICT"
    UA = "UA"
    EN = "EN"
    MIXED_UA_EN = "MIXED_UA_EN"


class EvaluationSplitName(StrEnum):
    DEVELOPMENT = "development"
    HOLDOUT = "holdout"


class EvaluationRecordModel(BaseModel):
    """Strict evaluation record base whose fields may legitimately be named digest."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=False,
        validate_assignment=True,
        use_enum_values=False,
    )

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        for field_name in self.model_fields_set:
            if getattr(self, field_name, object()) is None:
                raise ValueError(f"{field_name} must be omitted rather than null")
        return self

    def to_canonical_dict(self) -> dict[str, Any]:
        dumped = self.model_dump(mode="python", exclude_none=True)
        parsed = json.loads(canonical_bytes(dumped))
        if not isinstance(parsed, dict):
            raise TypeError("evaluation record did not serialize to an object")
        return cast("dict[str, Any]", parsed)


class GroundTruthMethod(StrEnum):
    HUMAN_ADJUDICATED = "human_adjudicated"
    CANONICAL_RECORD = "canonical_record"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class TemporalExpectation(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    CONFLICTED = "conflicted"
    NOT_APPLICABLE = "not_applicable"


class AuthorityOutcome(StrEnum):
    PREFER = "prefer"
    SUPPORT = "support"
    DO_NOT_CITE = "do_not_cite"
    EXCLUDE = "exclude"
    QUARANTINE = "quarantine"
    REPORT_CONFLICT = "report_conflict"


def _unique(values: list[Any] | None) -> list[Any] | None:
    if values is None:
        return None
    if len(values) != len(set(values)):
        raise ValueError("collection items must be unique")
    return values


def _unique_sorted(values: list[Any] | None) -> list[Any] | None:
    values = _unique(values)
    if values is None:
        return None
    return sorted(values, key=lambda value: value.value if isinstance(value, StrEnum) else value)


def _sort_grades(values: list[GroundTruthGrade]) -> list[GroundTruthGrade]:
    source_ids = [value.source_id for value in values]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("ground-truth source grades must be unique")
    return sorted(values, key=lambda value: value.source_id)


class EvaluationCorpusManifest(RuntimeModel):
    """Runtime form of the frozen ``power.retrieval-eval.v1`` manifest."""

    dataset_schema_version: Literal["power.retrieval-eval.v1"]
    evaluation_revision: Literal["v1", "v1.1"] = "v1"
    dataset_digest: Digest
    source_corpus_digest: Digest | None = None
    holdout_access_receipt_digest: Digest | None = None
    query_set_digest: Digest
    language_mix: list[EvaluationLanguage] = Field(min_length=3, max_length=3)
    required_categories: list[EvaluationCategory] = Field(min_length=18, max_length=18)
    development_split: DevelopmentSplit
    holdout_split: HoldoutSplit
    ground_truth_provenance: list[GroundTruthProvenance] = Field(min_length=1, max_length=16)
    no_tuning_on_holdout: Literal[True]
    real_vault_ingestion: Literal[False]
    holdout_access_audit: OpaqueReference
    split_relation: Literal["disjoint"]
    no_shared_query_ids: Literal[True]
    sealed_artifact_ref: OpaqueReference
    disjointness_proof_ref: OpaqueReference
    disjointness_proof_digest: Digest
    planning_only: Literal[True] | None = None
    supersedes_revision: Literal["v1"] | None = None
    semantic_adjudication_ref: OpaqueReference | None = None
    semantic_adjudication_digest: Digest | None = None
    semantic_adjudication_markdown_digest: Digest | None = None

    _unique_languages = field_validator("language_mix", "required_categories")(_unique)

    @model_validator(mode="after")
    def validate_required_coverage(self) -> Self:
        expected_languages = set(EvaluationLanguage)
        if set(self.language_mix) != expected_languages:
            raise ValueError("manifest must declare UA, EN, and MIXED_UA_EN")
        if set(self.required_categories) != set(EvaluationCategory):
            raise ValueError("manifest must declare exactly the frozen category vocabulary")
        return self


class DevelopmentSplit(EvaluationRecordModel):
    name: Literal["development"]
    digest: Digest
    query_count: Annotated[StrictInt, Field(ge=1, le=MAX_JSONL_RECORDS)]
    tuning_allowed: Literal[True]


class HoldoutSplit(EvaluationRecordModel):
    name: Literal["holdout"]
    digest: Digest
    query_count: Annotated[StrictInt, Field(ge=1, le=MAX_JSONL_RECORDS)]
    tuning_allowed: Literal[False]


class GroundTruthProvenance(RuntimeModel):
    source_ref: OpaqueReference
    method: GroundTruthMethod
    reviewed: Literal[True]
    provenance_digest: Digest


class EvaluationSourceMetadata(RuntimeModel):
    source_id: OpaqueReference
    path: SourceReference
    sha256: Digest
    byte_size: Annotated[StrictInt, Field(ge=1, le=MAX_FILE_BYTES)]
    title: ShortText
    language_mix: EvaluationLanguage
    domains: list[Identifier] = Field(min_length=1, max_length=8)
    source_type: Identifier
    authority: Authority
    trust_state: TrustState
    temporal_state: Literal["current", "stale", "future", "unknown"]
    superseded_by: list[OpaqueReference] | None = Field(default=None, max_length=16)
    contradiction_group: OpaqueReference | None = None
    noise_disposition: NoiseDisposition
    sensitivity_class: SensitivityClass
    scenario_family: OpaqueReference
    synthetic: Literal[True]
    source_preserved: Literal[True]
    source_origin: Literal["repository_synthetic"]

    _unique_domains = field_validator("domains", "superseded_by")(_unique_sorted)

    @model_validator(mode="after")
    def validate_source_axes(self) -> Self:
        validate_trust_authority(self.trust_state, self.authority)
        if (
            self.noise_disposition is NoiseDisposition.QUARANTINE
            and self.trust_state is not TrustState.QUARANTINED
        ):
            raise ValueError("quarantine disposition requires QUARANTINED trust")
        if (
            self.trust_state is TrustState.QUARANTINED
            and self.noise_disposition is not NoiseDisposition.QUARANTINE
        ):
            raise ValueError("QUARANTINED source requires quarantine disposition")
        return self


class EvaluationQuery(RuntimeModel):
    query_id: OpaqueReference
    split: EvaluationSplitName
    scenario_family: OpaqueReference
    query: ShortText = Field(max_length=2048)
    language_mix: EvaluationLanguage
    categories: list[EvaluationCategory] = Field(min_length=1, max_length=8)
    intent: QueryIntentKind | None = None

    _unique_categories = field_validator("categories")(_unique_sorted)

    @model_validator(mode="after")
    def validate_id_shape(self) -> Self:
        if not _QUERY_ID_PATTERN.fullmatch(self.query_id):
            raise ValueError("query_id must use the frozen p38 split prefix")
        expected_prefix = "p38-dev-" if self.split is EvaluationSplitName.DEVELOPMENT else "p38-ho-"
        if not self.query_id.startswith(expected_prefix):
            raise ValueError("query_id prefix does not match split")
        return self


class GroundTruthGrade(RuntimeModel):
    source_id: OpaqueReference
    relevance: Annotated[StrictInt, Field(ge=0, le=3)]
    authority_outcome: AuthorityOutcome


class EvaluationGroundTruth(RuntimeModel):
    query_id: OpaqueReference
    expected_relevant_source_ids: list[OpaqueReference] = Field(max_length=64)
    graded_relevance: list[GroundTruthGrade] = Field(max_length=128)
    expected_authority_winner: OpaqueReference | None = None
    expected_exclusion_source_ids: list[OpaqueReference] = Field(max_length=64)
    expected_disposition: NoiseDisposition | None = None
    temporal_expectation: TemporalExpectation
    reason: ShortText
    provenance_ref: OpaqueReference
    provenance_digest: Digest

    _unique_source_ids = field_validator(
        "expected_relevant_source_ids", "expected_exclusion_source_ids"
    )(_unique_sorted)

    _sorted_grades = field_validator("graded_relevance")(_sort_grades)

    @model_validator(mode="after")
    def validate_grades(self) -> Self:
        grade_ids = [item.source_id for item in self.graded_relevance]
        if len(grade_ids) != len(set(grade_ids)):
            raise ValueError("ground-truth source grades must be unique")
        if not set(self.expected_relevant_source_ids) <= set(grade_ids):
            raise ValueError("expected relevant sources require graded relevance")
        return self


class SemanticAdjudicationRecord(EvaluationRecordModel):
    """One bounded, reviewable decision in the active corpus audit."""

    action: Literal["KEEP_QUERY_KEEP_GT", "REWRITE_QUERY", "CHANGE_GROUND_TRUTH"]
    query_id: OpaqueReference
    rationale_ref: OpaqueReference
    review_status: Literal["two_independent_reviews_plus_orchestrator"]
    reviewer_a: Literal["PASS", "DEFECT", "AMBIGUOUS"]
    reviewer_b: Literal["PASS", "DEFECT", "AMBIGUOUS"]
    verdict: Literal["PASS"]


class SemanticReviewReceipt(EvaluationRecordModel):
    """Bounded receipt describing one independent semantic review input."""

    algorithm_output_used: Literal[False]
    ambiguous_count: Annotated[StrictInt, Field(ge=0, le=MAX_JSONL_RECORDS)]
    defect_count: Annotated[StrictInt, Field(ge=0, le=MAX_JSONL_RECORDS)]
    input_dataset_digest: Digest
    input_query_set_digest: Digest
    input_revision: Literal["v1"]
    pass_count: Annotated[StrictInt, Field(ge=0, le=MAX_JSONL_RECORDS)]
    retrieval_metrics_observed: Literal[False]
    reviewer_id: OpaqueReference
    scope_query_count: Annotated[StrictInt, Field(ge=1, le=MAX_JSONL_RECORDS)]
    scope_source_count: Annotated[StrictInt, Field(ge=1, le=MAX_JSONL_RECORDS)]
    schema_version: Literal["power.retrieval-semantic-review.v1"]

    @model_validator(mode="after")
    def validate_scope_counts(self) -> Self:
        if self.pass_count + self.defect_count + self.ambiguous_count != self.scope_query_count:
            raise ValueError("semantic review counts must cover the declared query scope")
        return self


class SemanticAdjudicationArtifact(EvaluationRecordModel):
    """Content-addressed semantic evidence bound to one corpus revision."""

    algorithm_output_used: Literal[False]
    dataset_revision: Literal["v1.1"]
    records: list[SemanticAdjudicationRecord] = Field(min_length=1, max_length=MAX_JSONL_RECORDS)
    retrieval_metrics_observed: Literal[False]
    reviewer_a_receipt_digest: Digest
    reviewer_a_receipt_ref: OpaqueReference
    reviewer_b_receipt_digest: Digest
    reviewer_b_receipt_ref: OpaqueReference
    review_method: Literal["two_independent_reviews_plus_orchestrator"]
    router_threshold_existed: Literal[False]
    schema_version: Literal["power.retrieval-semantic-adjudication.v1"]

    @model_validator(mode="after")
    def validate_record_ids(self) -> Self:
        query_ids = [record.query_id for record in self.records]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("semantic adjudication query IDs must be unique")
        return self


class DisjointnessProof(RuntimeModel):
    schema_version: Literal["power.retrieval-disjointness.v1"]
    development_query_ids: list[OpaqueReference] = Field(min_length=1, max_length=MAX_JSONL_RECORDS)
    holdout_query_ids: list[OpaqueReference] = Field(min_length=1, max_length=MAX_JSONL_RECORDS)
    query_id_intersection_count: Literal[0]
    development_scenario_families: list[OpaqueReference] = Field(
        min_length=1, max_length=MAX_JSONL_RECORDS
    )
    holdout_scenario_families: list[OpaqueReference] = Field(
        min_length=1, max_length=MAX_JSONL_RECORDS
    )
    scenario_family_intersection_count: Literal[0]
    normalized_query_overlap_count: Literal[0]
    development_normalized_query_digests: list[Digest] = Field(
        min_length=1, max_length=MAX_JSONL_RECORDS
    )
    holdout_normalized_query_digests: list[Digest] = Field(
        min_length=1, max_length=MAX_JSONL_RECORDS
    )
    source_corpus_mode: Literal["shared_read_only"]
    document_ids_shared_allowed: Literal[True]

    _unique_proof_ids = field_validator(
        "development_query_ids",
        "holdout_query_ids",
        "development_scenario_families",
        "holdout_scenario_families",
        "development_normalized_query_digests",
        "holdout_normalized_query_digests",
    )(_unique)


class HoldoutAccessReceipt(RuntimeModel):
    schema_version: Literal["power.retrieval-holdout-access.v1"]
    purpose: Literal["integrity_verification"]
    split: Literal["holdout"]
    dataset_revision: Digest
    query_set_digest: Digest
    accessed_at: AwareDateTime
    tool_revision: OpaqueReference
    tuning_capability: Literal[False]
    raw_content_egress: Literal[False]
    max_rows: Annotated[StrictInt, Field(ge=1, le=MAX_JSONL_RECORDS)]
    max_bytes: Annotated[StrictInt, Field(ge=1, le=MAX_FILE_BYTES)]
    rows_read: Annotated[StrictInt, Field(ge=0, le=MAX_JSONL_RECORDS)]
    bytes_read: Annotated[StrictInt, Field(ge=0, le=MAX_FILE_BYTES)]


def normalize_query_text(value: str) -> str:
    """Normalize only for deterministic exact-overlap detection, not semantics."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


class EvaluationIntegrityError(ValueError):
    """Bounded verifier failure with a stable machine-readable error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class EvaluationVerificationSnapshot:
    """Verified integrity result plus counters captured during that read."""

    summary: dict[str, Any]
    manifest: EvaluationCorpusManifest
    holdout_rows_read: int
    holdout_bytes_read: int


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationIntegrityError("duplicate_json_key", "duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise EvaluationIntegrityError(
        "non_finite_json", f"non-finite JSON constant {value} is forbidden"
    )


def _read_bounded_regular_file(path: Path) -> bytes:
    """Read a regular artifact through a no-follow, bounded file descriptor."""
    fd: int | None = None
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise EvaluationIntegrityError(
                "invalid_artifact", "evaluation artifact must be a regular file"
            )
        if info.st_size > MAX_FILE_BYTES:
            raise EvaluationIntegrityError(
                "artifact_too_large", "evaluation artifact exceeds the byte bound"
            )
        with os.fdopen(fd, "rb") as stream:
            fd = None
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise EvaluationIntegrityError(
                "artifact_too_large", "evaluation artifact exceeds the byte bound"
            )
        return data
    except EvaluationIntegrityError:
        raise
    except OSError as exc:
        raise EvaluationIntegrityError(
            "missing_artifact", "evaluation artifact is unreadable"
        ) from exc
    finally:
        if fd is not None:
            os.close(fd)


def _reject_forbidden_markers(data: bytes) -> None:
    lowered = data.lower()
    if any(marker.encode("ascii") in lowered for marker in _FORBIDDEN_SYNTHETIC_MARKERS):
        raise EvaluationIntegrityError(
            "real_vault_marker", "evaluation artifacts contain a forbidden marker"
        )


def _parse_json_bytes(data: bytes, *, error_code: str, error_message: str) -> Any:
    try:
        text = data.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except EvaluationIntegrityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationIntegrityError(error_code, error_message) from exc


def _read_json(path: Path) -> Any:
    try:
        data = _read_bounded_regular_file(path)
    except EvaluationIntegrityError:
        raise
    _reject_forbidden_markers(data)
    return _parse_json_bytes(
        data,
        error_code="invalid_json",
        error_message="evaluation artifact is not valid UTF-8 JSON",
    )


def _read_jsonl_with_size(path: Path) -> tuple[list[dict[str, Any]], int]:
    try:
        data = _read_bounded_regular_file(path)
    except EvaluationIntegrityError:
        raise
    _reject_forbidden_markers(data)
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(data.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if len(raw_line) > MAX_JSONL_RECORD_BYTES:
            raise EvaluationIntegrityError(
                "record_too_large", f"JSONL record {line_number} exceeds the byte bound"
            )
        try:
            parsed = json.loads(
                raw_line.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_json_constant,
            )
        except EvaluationIntegrityError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvaluationIntegrityError(
                "invalid_jsonl", f"invalid JSONL record {line_number}"
            ) from exc
        if not isinstance(parsed, dict):
            raise EvaluationIntegrityError(
                "record_not_object", f"JSONL record {line_number} is not an object"
            )
        rows.append(parsed)
        if len(rows) > MAX_JSONL_RECORDS:
            raise EvaluationIntegrityError(
                "too_many_records", "evaluation JSONL exceeds the row bound"
            )
    return rows, len(data)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl_with_size(path)[0]


def _fixture_path(root: Path, reference: str) -> Path:
    if reference.startswith(("/", "\\")) or "\\" in reference or ".." in Path(reference).parts:
        raise EvaluationIntegrityError(
            "unsafe_reference", "fixture reference escapes the corpus root"
        )
    raw_candidate = root / reference
    for parent in (raw_candidate, *raw_candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise EvaluationIntegrityError(
                "symlink_reference", "evaluation fixtures must not be symlinks"
            )
    candidate = raw_candidate.resolve()
    resolved_root = root.resolve()
    if resolved_root != candidate and resolved_root not in candidate.parents:
        raise EvaluationIntegrityError(
            "unsafe_reference", "fixture reference escapes the corpus root"
        )
    return candidate


def _parse_models(
    root: Path,
) -> tuple[
    EvaluationCorpusManifest,
    list[EvaluationSourceMetadata],
    list[EvaluationQuery],
    list[EvaluationQuery],
    list[EvaluationGroundTruth],
    DisjointnessProof,
    HoldoutAccessReceipt,
    SemanticAdjudicationArtifact | None,
    int,
    int,
]:
    try:
        manifest = EvaluationCorpusManifest.model_validate(
            _read_json(_fixture_path(root, "manifest.json"))
        )
        source_rows = [
            EvaluationSourceMetadata.model_validate(row)
            for row in _read_jsonl(_fixture_path(root, "source_metadata.jsonl"))
        ]
        development = [
            EvaluationQuery.model_validate(row)
            for row in _read_jsonl(_fixture_path(root, "queries.development.jsonl"))
        ]
        holdout_rows, holdout_query_bytes = _read_jsonl_with_size(
            _fixture_path(root, "queries.holdout.jsonl")
        )
        holdout = [EvaluationQuery.model_validate(row) for row in holdout_rows]
        ground_truth_development = [
            EvaluationGroundTruth.model_validate(row)
            for row in _read_jsonl(_fixture_path(root, "ground_truth.development.jsonl"))
        ]
        ground_truth_holdout_rows, ground_truth_holdout_bytes = _read_jsonl_with_size(
            _fixture_path(root, "ground_truth.holdout.jsonl")
        )
        ground_truth_holdout = [
            EvaluationGroundTruth.model_validate(row) for row in ground_truth_holdout_rows
        ]
        _check_query_sets(development, holdout)
        _check_ground_truth(
            source_rows,
            development,
            [],
            ground_truth_development,
            expected_split=EvaluationSplitName.DEVELOPMENT,
        )
        _check_ground_truth(
            source_rows,
            [],
            holdout,
            ground_truth_holdout,
            expected_split=EvaluationSplitName.HOLDOUT,
        )
        ground_truth = ground_truth_development + ground_truth_holdout
        proof = DisjointnessProof.model_validate(
            _read_json(_fixture_path(root, "disjointness-proof.json"))
        )
        receipt = HoldoutAccessReceipt.model_validate(
            _read_json(_fixture_path(root, "holdout-access-receipt.json"))
        )
        semantic_adjudication = None
        if manifest.evaluation_revision == ACTIVE_EVALUATION_REVISION:
            semantic_adjudication = SemanticAdjudicationArtifact.model_validate(
                _read_json(_fixture_path(root, "semantic-adjudication.json"))
            )
    except ValidationError as exc:
        raise EvaluationIntegrityError(
            "schema_mismatch", "evaluation record failed strict validation"
        ) from exc
    return (
        manifest,
        source_rows,
        development,
        holdout,
        ground_truth,
        proof,
        receipt,
        semantic_adjudication,
        holdout_query_bytes + ground_truth_holdout_bytes,
        len(ground_truth_holdout),
    )


def _source_entries(
    root: Path, source_rows: list[EvaluationSourceMetadata]
) -> list[dict[str, Any]]:
    if len(source_rows) != FROZEN_PHASE5A_COUNTS["sources"]:
        raise EvaluationIntegrityError("source_count", "source count is not admitted")
    corpus_dir = root / "corpus"
    if corpus_dir.is_symlink() or not corpus_dir.is_dir():
        raise EvaluationIntegrityError("corpus_inventory", "corpus directory is missing or unsafe")
    try:
        corpus_files = list(corpus_dir.iterdir())
    except OSError as exc:
        raise EvaluationIntegrityError(
            "corpus_inventory", "corpus directory is unreadable"
        ) from exc
    actual_paths: set[str] = set()
    for path in corpus_files:
        if path.is_symlink() or not path.is_file() or path.suffix != ".md":
            raise EvaluationIntegrityError(
                "corpus_inventory", "corpus contains an unlisted or non-Markdown artifact"
            )
        actual_paths.add(path.relative_to(root).as_posix())
    if not actual_paths:
        raise EvaluationIntegrityError("corpus_inventory", "corpus must contain source fixtures")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    declared_paths: set[str] = set()
    for source in source_rows:
        if source.source_id in seen:
            raise EvaluationIntegrityError("duplicate_source_id", "source IDs must be unique")
        seen.add(source.source_id)
        source_reference = Path(source.path)
        if source_reference.parent != Path("corpus") or source_reference.suffix != ".md":
            raise EvaluationIntegrityError(
                "corpus_inventory", "source metadata must reference a direct corpus Markdown file"
            )
        declared_path = source_reference.as_posix()
        if declared_path in declared_paths:
            raise EvaluationIntegrityError("duplicate_source_path", "source paths must be unique")
        declared_paths.add(declared_path)
        source_path = _fixture_path(root, source.path)
        try:
            content = _read_bounded_regular_file(source_path)
        except EvaluationIntegrityError as exc:
            raise EvaluationIntegrityError(
                exc.code, "ground-truth source file is unreadable"
            ) from exc
        if (
            not content
            or len(content) != source.byte_size
            or _sha256_bytes(content) != source.sha256
        ):
            raise EvaluationIntegrityError(
                "source_digest_mismatch", "source metadata digest does not match bytes"
            )
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvaluationIntegrityError(
                "invalid_source_encoding", "source fixture is not valid UTF-8"
            ) from exc
        if (
            not decoded.startswith("---\n")
            or "\ntype:" not in decoded
            or "\ntimestamp:" not in decoded
        ):
            raise EvaluationIntegrityError(
                "source_format", "source fixture must be Markdown with basic OKF frontmatter"
            )
        lowered = decoded.lower()
        if any(marker in lowered for marker in _FORBIDDEN_SYNTHETIC_MARKERS):
            raise EvaluationIntegrityError(
                "real_vault_marker", "synthetic corpus contains a forbidden marker"
            )
        entries.append(
            {
                **source.to_canonical_dict(),
                "content_sha256": source.sha256,
                "content_bytes": source.byte_size,
            }
        )
    if declared_paths != actual_paths:
        raise EvaluationIntegrityError(
            "corpus_inventory", "source metadata does not exactly enumerate corpus Markdown files"
        )
    return sorted(entries, key=lambda item: item["source_id"])


def _check_historical_v1_bytes(root: Path) -> None:
    actual: dict[str, str] = {}
    try:
        paths = list(root.rglob("*"))
    except OSError as exc:
        raise EvaluationIntegrityError(
            "historical_v1_immutability", "historical v1 inventory is unreadable"
        ) from exc
    for path in paths:
        if path.is_symlink():
            raise EvaluationIntegrityError(
                "historical_v1_immutability", "historical v1 contains a symlink"
            )
        if path.is_dir():
            continue
        try:
            actual[path.relative_to(root).as_posix()] = _sha256_bytes(
                _read_bounded_regular_file(path)
            )
        except EvaluationIntegrityError as exc:
            raise EvaluationIntegrityError(
                "historical_v1_immutability", "historical v1 file is unreadable"
            ) from exc
    if actual != HISTORICAL_V1_FILE_SHA256:
        raise EvaluationIntegrityError(
            "historical_v1_immutability", "historical v1 bytes or inventory changed"
        )


def _check_active_v11_inventory(root: Path) -> None:
    actual: dict[str, str] = {}
    try:
        paths = list(root.iterdir())
    except OSError as exc:
        raise EvaluationIntegrityError(
            "active_v11_inventory", "active v1.1 inventory is unreadable"
        ) from exc
    for path in paths:
        if path.is_symlink():
            raise EvaluationIntegrityError("active_v11_inventory", "active v1.1 contains a symlink")
        if path.is_dir():
            if path.name != "corpus":
                raise EvaluationIntegrityError(
                    "active_v11_inventory", "active v1.1 contains an unlisted directory"
                )
            continue
        try:
            actual[path.relative_to(root).as_posix()] = _sha256_bytes(
                _read_bounded_regular_file(path)
            )
        except EvaluationIntegrityError as exc:
            raise EvaluationIntegrityError(
                "active_v11_inventory", "active v1.1 root artifact is unreadable"
            ) from exc
    if actual != ACTIVE_V11_ROOT_FILE_SHA256:
        raise EvaluationIntegrityError(
            "active_v11_inventory", "active v1.1 root bytes or inventory changed"
        )


def _check_query_sets(
    development: list[EvaluationQuery], holdout: list[EvaluationQuery]
) -> tuple[set[str], set[str], set[str], set[str], set[str], set[str]]:
    all_queries = development + holdout
    ids = [item.query_id for item in all_queries]
    if len(ids) != len(set(ids)):
        raise EvaluationIntegrityError("duplicate_query_id", "query IDs must be globally unique")
    development_ids = {item.query_id for item in development}
    holdout_ids = {item.query_id for item in holdout}
    if development_ids & holdout_ids:
        raise EvaluationIntegrityError(
            "split_query_overlap", "development and holdout query IDs overlap"
        )
    development_families = {item.scenario_family for item in development}
    holdout_families = {item.scenario_family for item in holdout}
    if development_families & holdout_families:
        raise EvaluationIntegrityError(
            "split_family_overlap", "scenario families overlap across splits"
        )
    development_normalized = {normalize_query_text(item.query) for item in development}
    holdout_normalized = {normalize_query_text(item.query) for item in holdout}
    if len(development_normalized) != len(development):
        raise EvaluationIntegrityError(
            "duplicate_normalized_query", "development queries normalize to duplicates"
        )
    if len(holdout_normalized) != len(holdout):
        raise EvaluationIntegrityError(
            "duplicate_normalized_query", "holdout queries normalize to duplicates"
        )
    if development_normalized & holdout_normalized:
        raise EvaluationIntegrityError(
            "normalized_query_overlap", "normalized query text overlaps across splits"
        )
    return (
        development_ids,
        holdout_ids,
        development_families,
        holdout_families,
        development_normalized,
        holdout_normalized,
    )


def _check_coverage(
    manifest: EvaluationCorpusManifest,
    development: list[EvaluationQuery],
    holdout: list[EvaluationQuery],
) -> None:
    high_risk = {
        EvaluationCategory.PROJECT_STATE,
        EvaluationCategory.DECISION,
        EvaluationCategory.TASK,
        EvaluationCategory.SUPERSEDED,
        EvaluationCategory.CONTRADICTION,
        EvaluationCategory.PROMPT_INJECTION,
        EvaluationCategory.HARD_NEGATIVE,
        EvaluationCategory.AUTHORITY_CONFLICT,
    }
    for name, records in (("development", development), ("holdout", holdout)):
        languages = {item.language_mix for item in records}
        if languages != set(EvaluationLanguage):
            raise EvaluationIntegrityError(
                "language_coverage", f"{name} lacks a required language stratum"
            )
        categories = {category for item in records for category in item.categories}
        if not high_risk <= categories:
            raise EvaluationIntegrityError(
                "high_risk_coverage", f"{name} lacks a high-risk category"
            )
    actual: set[str] = {
        category.value for item in development + holdout for category in item.categories
    }
    actual |= {item.language_mix.value for item in development + holdout}
    if {category.value for category in manifest.required_categories} - actual:
        raise EvaluationIntegrityError(
            "category_coverage", "manifest category coverage is not present in records"
        )


def _revision_spec(manifest: EvaluationCorpusManifest) -> dict[str, Any]:
    try:
        return EVALUATION_REVISION_REGISTRY[manifest.evaluation_revision]
    except KeyError as exc:
        raise EvaluationIntegrityError(
            "revision_unknown", "evaluation revision is not registered"
        ) from exc


def _check_pinned_manifest(manifest: EvaluationCorpusManifest) -> dict[str, Any]:
    spec = _revision_spec(manifest)
    expected = spec["digests"]
    if manifest.dataset_digest != expected["dataset_digest"]:
        raise EvaluationIntegrityError(
            "manifest_pin", "manifest is not bound to the admitted dataset"
        )
    if manifest.query_set_digest != expected["query_set_digest"]:
        raise EvaluationIntegrityError(
            "manifest_pin", "manifest is not bound to the admitted query set"
        )
    if manifest.development_split.digest != expected["development_digest"]:
        raise EvaluationIntegrityError("manifest_pin", "development split is not admitted")
    if manifest.holdout_split.digest != expected["holdout_digest"]:
        raise EvaluationIntegrityError("manifest_pin", "holdout split is not admitted")
    if manifest.disjointness_proof_digest != expected["disjointness_digest"]:
        raise EvaluationIntegrityError("manifest_pin", "disjointness proof is not admitted")
    refs = spec["refs"]
    if (
        manifest.holdout_access_audit != refs["holdout_access_audit"]
        or manifest.sealed_artifact_ref != refs["sealed_artifact_ref"]
        or manifest.disjointness_proof_ref != refs["disjointness_proof_ref"]
    ):
        raise EvaluationIntegrityError("manifest_pin", "manifest references are not admitted")
    if manifest.development_split.query_count != FROZEN_PHASE5A_COUNTS["development_queries"]:
        raise EvaluationIntegrityError("manifest_pin", "development count is not admitted")
    if manifest.holdout_split.query_count != FROZEN_PHASE5A_COUNTS["holdout_queries"]:
        raise EvaluationIntegrityError("manifest_pin", "holdout count is not admitted")
    if (
        manifest.planning_only != refs["planning_only"]
        or manifest.supersedes_revision != refs["supersedes_revision"]
        or manifest.semantic_adjudication_ref != refs["semantic_adjudication_ref"]
        or manifest.source_corpus_digest != refs["source_corpus_digest"]
        or manifest.semantic_adjudication_markdown_digest
        != refs["semantic_adjudication_markdown_digest"]
    ):
        raise EvaluationIntegrityError("manifest_pin", "revision identity is not admitted")
    expected_semantic_digest = expected.get("semantic_adjudication_digest")
    if manifest.semantic_adjudication_digest != expected_semantic_digest:
        raise EvaluationIntegrityError("manifest_pin", "semantic adjudication is not admitted")
    return spec


def _check_manifest_provenance(manifest: EvaluationCorpusManifest, spec: dict[str, Any]) -> None:
    if len(manifest.ground_truth_provenance) != 1:
        raise EvaluationIntegrityError("provenance", "frozen corpus requires one provenance record")
    provenance = manifest.ground_truth_provenance[0]
    refs = spec["refs"]
    if (
        provenance.source_ref != refs["provenance_source_ref"]
        or provenance.method.value != refs["provenance_method"]
        or provenance.provenance_digest
        != canonical_sha256(
            {"source_ref": provenance.source_ref, "method": provenance.method.value}
        )
    ):
        raise EvaluationIntegrityError(
            "provenance", "ground-truth provenance is not bound to the fixture"
        )


def _check_semantic_adjudication(
    root: Path,
    manifest: EvaluationCorpusManifest,
    artifact: SemanticAdjudicationArtifact | None,
    query_ids: set[str],
) -> str | None:
    spec = _revision_spec(manifest)
    expected_digest = spec["digests"].get("semantic_adjudication_digest")
    if expected_digest is None:
        if artifact is not None:
            raise EvaluationIntegrityError(
                "semantic_adjudication", "historical revision must not carry active adjudication"
            )
        return None
    if artifact is None:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "active revision requires semantic adjudication"
        )
    if artifact.dataset_revision != manifest.evaluation_revision:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "semantic adjudication revision does not match manifest"
        )
    if {record.query_id for record in artifact.records} != query_ids:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "semantic adjudication does not cover every query"
        )
    if canonical_sha256(artifact.to_canonical_dict()) != expected_digest:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "semantic adjudication digest mismatch"
        )
    receipt_expectations = (
        ("reviewer_a_receipt_ref", "reviewer_a_receipt_digest", "semantic-review-a-v1.1"),
        ("reviewer_b_receipt_ref", "reviewer_b_receipt_digest", "semantic-review-b-v1.1"),
    )
    for ref_field, digest_field, expected_ref in receipt_expectations:
        receipt_ref = getattr(artifact, ref_field)
        if receipt_ref != expected_ref or receipt_ref != spec["refs"][ref_field]:
            raise EvaluationIntegrityError(
                "semantic_adjudication", "independent review receipt reference is not admitted"
            )
        try:
            receipt_bytes = _read_bounded_regular_file(_fixture_path(root, f"{receipt_ref}.json"))
        except EvaluationIntegrityError as exc:
            raise EvaluationIntegrityError(
                "semantic_adjudication", "independent review receipt is unreadable"
            ) from exc
        _reject_forbidden_markers(receipt_bytes)
        receipt_data = _parse_json_bytes(
            receipt_bytes,
            error_code="semantic_adjudication",
            error_message="independent review receipt is invalid JSON",
        )
        try:
            review_receipt = SemanticReviewReceipt.model_validate(receipt_data)
        except ValidationError as exc:
            raise EvaluationIntegrityError(
                "semantic_adjudication", "independent review receipt failed validation"
            ) from exc
        expected_counts = (28, 4, 8) if receipt_ref.endswith("a-v1.1") else (27, 5, 8)
        if (
            review_receipt.reviewer_id != receipt_ref
            or review_receipt.input_revision != "v1"
            or review_receipt.input_dataset_digest != FROZEN_PHASE5A_DIGESTS["dataset_digest"]
            or review_receipt.input_query_set_digest != FROZEN_PHASE5A_DIGESTS["query_set_digest"]
            or review_receipt.scope_query_count != 40
            or review_receipt.scope_source_count != 20
            or (
                review_receipt.pass_count,
                review_receipt.defect_count,
                review_receipt.ambiguous_count,
            )
            != expected_counts
        ):
            raise EvaluationIntegrityError(
                "semantic_adjudication", "independent review receipt is not bound to the audit"
            )
        if _sha256_bytes(receipt_bytes) != getattr(artifact, digest_field):
            raise EvaluationIntegrityError(
                "semantic_adjudication", "independent review receipt digest mismatch"
            )
    markdown_digest = manifest.semantic_adjudication_markdown_digest
    if markdown_digest is None:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "active revision requires adjudication rationale evidence"
        )
    try:
        rationale_bytes = _read_bounded_regular_file(
            _fixture_path(root, "semantic-adjudication.md")
        )
    except EvaluationIntegrityError as exc:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "semantic adjudication rationale evidence is unreadable"
        ) from exc
    _reject_forbidden_markers(rationale_bytes)
    if _sha256_bytes(rationale_bytes) != markdown_digest:
        raise EvaluationIntegrityError(
            "semantic_adjudication", "semantic adjudication rationale digest mismatch"
        )
    for record in artifact.records:
        if record.rationale_ref.encode("ascii") not in rationale_bytes:
            raise EvaluationIntegrityError(
                "semantic_adjudication", "semantic adjudication rationale reference is missing"
            )
    return markdown_digest


def _check_holdout_receipt_digest(root: Path, manifest: EvaluationCorpusManifest) -> str | None:
    spec = _revision_spec(manifest)
    expected_digest = cast("str | None", spec["digests"].get("holdout_access_receipt_digest"))
    if expected_digest is None:
        return None
    try:
        receipt_bytes = _read_bounded_regular_file(
            _fixture_path(root, "holdout-access-receipt.json")
        )
    except EvaluationIntegrityError as exc:
        raise EvaluationIntegrityError(
            "holdout_receipt_binding", "holdout receipt bytes are unreadable"
        ) from exc
    if _sha256_bytes(receipt_bytes) != expected_digest:
        raise EvaluationIntegrityError(
            "holdout_receipt_binding", "holdout receipt digest is not admitted"
        )
    if manifest.holdout_access_receipt_digest != expected_digest:
        raise EvaluationIntegrityError(
            "holdout_receipt_binding", "manifest receipt digest is not admitted"
        )
    return expected_digest


def _check_ground_truth(
    source_rows: list[EvaluationSourceMetadata],
    development: list[EvaluationQuery],
    holdout: list[EvaluationQuery],
    ground_truth: list[EvaluationGroundTruth],
    *,
    expected_split: EvaluationSplitName | None = None,
) -> dict[str, list[EvaluationGroundTruth]]:
    source_by_id = {item.source_id: item for item in source_rows}
    source_ids = set(source_by_id)
    query_ids = {item.query_id for item in development + holdout}
    if len(ground_truth) != len(query_ids):
        raise EvaluationIntegrityError(
            "ground_truth_count", "every query must have one ground-truth record"
        )
    if len({item.query_id for item in ground_truth}) != len(ground_truth):
        raise EvaluationIntegrityError(
            "duplicate_ground_truth", "ground-truth query IDs must be unique"
        )
    by_split: dict[str, list[EvaluationGroundTruth]] = {"development": [], "holdout": []}
    query_split = {item.query_id: item.split.value for item in development + holdout}
    for record in ground_truth:
        if expected_split is not None:
            expected_prefix = (
                "p38-dev-" if expected_split is EvaluationSplitName.DEVELOPMENT else "p38-ho-"
            )
            if not record.query_id.startswith(expected_prefix):
                raise EvaluationIntegrityError(
                    "ground_truth_split", "ground truth file contains a different split"
                )
        if record.query_id not in query_ids:
            raise EvaluationIntegrityError(
                "unknown_ground_truth_query", "ground truth references an unknown query"
            )
        if expected_split is not None and query_split[record.query_id] != expected_split.value:
            raise EvaluationIntegrityError(
                "ground_truth_split", "ground truth file contains a different split"
            )
        referenced = set(record.expected_relevant_source_ids) | set(
            record.expected_exclusion_source_ids
        )
        referenced |= {grade.source_id for grade in record.graded_relevance}
        if record.expected_authority_winner is not None:
            referenced.add(record.expected_authority_winner)
        if not referenced <= source_ids:
            raise EvaluationIntegrityError(
                "unknown_ground_truth_source", "ground truth references an unknown source"
            )
        relevant_ids = set(record.expected_relevant_source_ids)
        excluded_ids = set(record.expected_exclusion_source_ids)
        if relevant_ids & excluded_ids:
            raise EvaluationIntegrityError(
                "ground_truth_overlap", "a source cannot be both relevant and excluded"
            )
        grade_by_source = {grade.source_id: grade for grade in record.graded_relevance}
        if not grade_by_source:
            raise EvaluationIntegrityError(
                "empty_ground_truth", "every ground-truth record needs bounded judgments"
            )
        if not relevant_ids <= set(grade_by_source):
            raise EvaluationIntegrityError(
                "ground_truth_grade", "relevant sources need graded relevance"
            )
        for source_id in relevant_ids:
            if grade_by_source[source_id].relevance < 1:
                raise EvaluationIntegrityError(
                    "ground_truth_grade", "relevant sources need a positive relevance grade"
                )
        for source_id in excluded_ids:
            if grade_by_source[source_id].relevance != 0:
                raise EvaluationIntegrityError(
                    "ground_truth_grade", "excluded sources must have zero relevance"
                )
        for grade in grade_by_source.values():
            if grade.relevance == 0 and grade.authority_outcome not in {
                AuthorityOutcome.EXCLUDE,
                AuthorityOutcome.QUARANTINE,
            }:
                raise EvaluationIntegrityError(
                    "ground_truth_grade", "zero-relevance sources need an exclusion outcome"
                )
        if record.expected_authority_winner is not None and (
            record.expected_authority_winner not in relevant_ids
            or record.expected_authority_winner in excluded_ids
        ):
            raise EvaluationIntegrityError(
                "ground_truth_winner", "authority winner must be a relevant non-excluded source"
            )
        if record.expected_disposition is NoiseDisposition.QUARANTINE:
            if relevant_ids or not excluded_ids:
                raise EvaluationIntegrityError(
                    "ground_truth_disposition", "quarantine ground truth must exclude a source"
                )
            if any(
                source_by_id[source_id].noise_disposition is not NoiseDisposition.QUARANTINE
                for source_id in excluded_ids
            ):
                raise EvaluationIntegrityError(
                    "ground_truth_disposition",
                    "quarantine expectation must reference quarantined source",
                )
        by_split[query_split[record.query_id]].append(record)
    return by_split


def _ground_truth_provenance_digest(record: EvaluationGroundTruth, revision: str) -> str:
    payload = record.to_canonical_dict()
    payload.pop("provenance_digest", None)
    return canonical_sha256({"ground_truth": payload, "revision": revision})


def _check_ground_truth_provenance(
    ground_truth: list[EvaluationGroundTruth], revision: str
) -> None:
    if revision != ACTIVE_EVALUATION_REVISION:
        return
    if any(
        record.provenance_digest != _ground_truth_provenance_digest(record, revision)
        for record in ground_truth
    ):
        raise EvaluationIntegrityError(
            "ground_truth_provenance", "active ground-truth provenance digest mismatch"
        )


def _check_proof(
    proof: DisjointnessProof,
    development: list[EvaluationQuery],
    holdout: list[EvaluationQuery],
) -> None:
    dev_ids, ho_ids, dev_families, ho_families, dev_norm, ho_norm = _check_query_sets(
        development, holdout
    )
    if set(proof.development_query_ids) != dev_ids or set(proof.holdout_query_ids) != ho_ids:
        raise EvaluationIntegrityError(
            "proof_query_ids", "disjointness proof query IDs do not match"
        )
    if proof.development_query_ids != sorted(proof.development_query_ids):
        raise EvaluationIntegrityError(
            "proof_order", "development proof IDs must be canonical-sorted"
        )
    if proof.holdout_query_ids != sorted(proof.holdout_query_ids):
        raise EvaluationIntegrityError("proof_order", "holdout proof IDs must be canonical-sorted")
    if proof.development_scenario_families != sorted(proof.development_scenario_families):
        raise EvaluationIntegrityError(
            "proof_order", "development proof families must be canonical-sorted"
        )
    if proof.holdout_scenario_families != sorted(proof.holdout_scenario_families):
        raise EvaluationIntegrityError(
            "proof_order", "holdout proof families must be canonical-sorted"
        )
    if proof.development_normalized_query_digests != sorted(
        proof.development_normalized_query_digests
    ):
        raise EvaluationIntegrityError(
            "proof_order", "development normalized-query proof must be sorted"
        )
    if proof.holdout_normalized_query_digests != sorted(proof.holdout_normalized_query_digests):
        raise EvaluationIntegrityError(
            "proof_order", "holdout normalized-query proof must be sorted"
        )
    if (
        set(proof.development_scenario_families) != dev_families
        or set(proof.holdout_scenario_families) != ho_families
    ):
        raise EvaluationIntegrityError("proof_families", "disjointness proof families do not match")
    if set(proof.development_normalized_query_digests) != {
        canonical_sha256(normalize_query_text(item.query)) for item in development
    }:
        raise EvaluationIntegrityError(
            "proof_normalized_queries", "development normalized-query proof mismatch"
        )
    if set(proof.holdout_normalized_query_digests) != {
        canonical_sha256(normalize_query_text(item.query)) for item in holdout
    }:
        raise EvaluationIntegrityError(
            "proof_normalized_queries", "holdout normalized-query proof mismatch"
        )
    if dev_ids & ho_ids or dev_families & ho_families or dev_norm & ho_norm:
        raise EvaluationIntegrityError("proof_overlap", "disjointness proof contains an overlap")


def _split_digest(queries: list[EvaluationQuery], ground_truth: list[EvaluationGroundTruth]) -> str:
    return canonical_sha256(
        {
            "queries": [
                item.to_canonical_dict() for item in sorted(queries, key=lambda item: item.query_id)
            ],
            "ground_truth": [
                item.to_canonical_dict()
                for item in sorted(ground_truth, key=lambda item: item.query_id)
            ],
        }
    )


def _source_corpus_digest(entries: list[dict[str, Any]]) -> str:
    return canonical_sha256({"corpus_files": entries})


def _query_set_digest(development: list[EvaluationQuery], holdout: list[EvaluationQuery]) -> str:
    return canonical_sha256(
        {
            "development": [
                item.to_canonical_dict()
                for item in sorted(development, key=lambda item: item.query_id)
            ],
            "holdout": [
                item.to_canonical_dict() for item in sorted(holdout, key=lambda item: item.query_id)
            ],
        }
    )


def verify_evaluation_corpus(
    root: Path, *, expected_revision: str | None = None, return_snapshot: bool = False
) -> dict[str, Any] | EvaluationVerificationSnapshot:
    """Verify one explicitly identified corpus revision offline."""
    root = root.resolve()
    (
        manifest,
        source_rows,
        development,
        holdout,
        ground_truth,
        proof,
        receipt,
        semantic_adjudication,
        holdout_bytes_read,
        holdout_ground_truth_count,
    ) = _parse_models(root)
    if expected_revision is not None and manifest.evaluation_revision != expected_revision:
        raise EvaluationIntegrityError(
            "revision_mismatch", "requested revision is not the manifest"
        )
    spec = _check_pinned_manifest(manifest)
    _check_manifest_provenance(manifest, spec)
    _check_coverage(manifest, development, holdout)
    _check_proof(proof, development, holdout)
    ground_truth_by_split = _check_ground_truth(source_rows, development, holdout, ground_truth)
    semantic_markdown_digest = _check_semantic_adjudication(
        root,
        manifest,
        semantic_adjudication,
        {item.query_id for item in development + holdout},
    )
    _check_ground_truth_provenance(ground_truth, manifest.evaluation_revision)
    receipt_digest = _check_holdout_receipt_digest(root, manifest)
    if (
        receipt.dataset_revision != manifest.dataset_digest
        or receipt.query_set_digest != manifest.query_set_digest
        or receipt.tool_revision != "verify-retrieval-eval-v1"
    ):
        raise EvaluationIntegrityError(
            "holdout_receipt_binding", "holdout receipt is not bound to the manifest"
        )
    holdout_rows_read = len(holdout) + holdout_ground_truth_count
    if receipt.max_rows < holdout_rows_read or receipt.rows_read != holdout_rows_read:
        raise EvaluationIntegrityError(
            "holdout_receipt_budget", "holdout receipt row evidence is invalid"
        )
    if receipt.max_bytes < holdout_bytes_read or receipt.bytes_read != holdout_bytes_read:
        raise EvaluationIntegrityError(
            "holdout_receipt_budget", "holdout receipt byte evidence is invalid"
        )
    entries = _source_entries(root, source_rows)
    source_corpus_digest = _source_corpus_digest(entries)
    if (
        manifest.source_corpus_digest is not None
        and manifest.source_corpus_digest != source_corpus_digest
    ):
        raise EvaluationIntegrityError(
            "source_digest_mismatch", "manifest source corpus digest does not match bytes"
        )
    if manifest.evaluation_revision == "v1":
        _check_historical_v1_bytes(root)
    elif manifest.evaluation_revision == ACTIVE_EVALUATION_REVISION:
        _check_active_v11_inventory(root)
    dataset_payload: dict[str, Any] = {
        "corpus_files": entries,
        "ground_truth": [
            item.to_canonical_dict()
            for item in sorted(ground_truth, key=lambda item: item.query_id)
        ],
    }
    if semantic_adjudication is not None:
        dataset_payload["semantic_adjudication"] = semantic_adjudication.to_canonical_dict()
        dataset_payload["semantic_adjudication_markdown_digest"] = semantic_markdown_digest
    dataset_digest = canonical_sha256(dataset_payload)
    query_set_digest = _query_set_digest(development, holdout)
    development_digest = _split_digest(development, ground_truth_by_split["development"])
    holdout_digest = _split_digest(holdout, ground_truth_by_split["holdout"])
    proof_digest = proof.digest()
    if manifest.dataset_digest != dataset_digest:
        raise EvaluationIntegrityError(
            "dataset_digest_mismatch", "dataset digest does not match frozen bytes"
        )
    if manifest.query_set_digest != query_set_digest:
        raise EvaluationIntegrityError(
            "query_digest_mismatch", "query-set digest does not match records"
        )
    if manifest.development_split.digest != development_digest:
        raise EvaluationIntegrityError("development_digest_mismatch", "development digest mismatch")
    if manifest.holdout_split.digest != holdout_digest:
        raise EvaluationIntegrityError("holdout_digest_mismatch", "holdout digest mismatch")
    if manifest.disjointness_proof_digest != proof_digest:
        raise EvaluationIntegrityError(
            "proof_digest_mismatch", "disjointness proof digest mismatch"
        )
    if manifest.development_split.query_count != len(
        development
    ) or manifest.holdout_split.query_count != len(holdout):
        raise EvaluationIntegrityError(
            "query_count_mismatch", "manifest split counts do not match JSONL"
        )
    summary = {
        "status": "PASS",
        "evaluation_revision": manifest.evaluation_revision,
        "semantic_adjudication_status": spec["semantic_status"],
        "dataset_digest": dataset_digest,
        "source_corpus_digest": source_corpus_digest,
        "query_set_digest": query_set_digest,
        "development_digest": development_digest,
        "holdout_digest": holdout_digest,
        "disjointness_digest": proof_digest,
        "source_count": len(source_rows),
        "development_query_count": len(development),
        "holdout_query_count": len(holdout),
        "holdout_policy": "SEALED_NOT_SECRET_NO_TUNING",
    }
    if manifest.semantic_adjudication_digest is not None:
        summary["semantic_adjudication_digest"] = manifest.semantic_adjudication_digest
    if semantic_markdown_digest is not None:
        summary["semantic_adjudication_markdown_digest"] = semantic_markdown_digest
    if receipt_digest is not None:
        summary["holdout_access_receipt_digest"] = receipt_digest
    if return_snapshot:
        return EvaluationVerificationSnapshot(
            summary=summary,
            manifest=manifest,
            holdout_rows_read=holdout_rows_read,
            holdout_bytes_read=holdout_bytes_read,
        )
    return summary


def load_development_for_tuning(
    root: Path, *, expected_revision: str | None = None
) -> list[EvaluationQuery]:
    """Load only development queries; holdout is not a tuning input surface."""
    root = root.resolve()
    try:
        manifest = EvaluationCorpusManifest.model_validate(
            _read_json(_fixture_path(root, "manifest.json"))
        )
        if expected_revision is not None and manifest.evaluation_revision != expected_revision:
            raise EvaluationIntegrityError(
                "revision_mismatch", "requested revision is not the manifest"
            )
        spec = _check_pinned_manifest(manifest)
        _check_manifest_provenance(manifest, spec)
        source_rows = [
            EvaluationSourceMetadata.model_validate(row)
            for row in _read_jsonl(_fixture_path(root, "source_metadata.jsonl"))
        ]
        source_entries = _source_entries(root, source_rows)
        expected = spec["digests"]
        if _source_corpus_digest(source_entries) != expected["source_corpus_digest"]:
            raise EvaluationIntegrityError(
                "source_digest_mismatch", "development tuning source corpus is not frozen"
            )
        development = [
            EvaluationQuery.model_validate(row)
            for row in _read_jsonl(_fixture_path(root, "queries.development.jsonl"))
        ]
        ground_truth = [
            EvaluationGroundTruth.model_validate(row)
            for row in _read_jsonl(_fixture_path(root, "ground_truth.development.jsonl"))
        ]
        _check_ground_truth(source_rows, development, [], ground_truth)
        digest = _split_digest(development, ground_truth)
        if digest != manifest.development_split.digest or digest != expected["development_digest"]:
            raise EvaluationIntegrityError(
                "development_digest_mismatch", "development tuning input is not frozen"
            )
        _check_ground_truth_provenance(ground_truth, manifest.evaluation_revision)
        if manifest.evaluation_revision == "v1":
            _check_historical_v1_bytes(root)
        if len(development) != manifest.development_split.query_count:
            raise EvaluationIntegrityError(
                "query_count_mismatch", "development tuning count does not match manifest"
            )
        return development
    except EvaluationIntegrityError:
        raise
    except ValidationError as exc:
        raise EvaluationIntegrityError(
            "schema_mismatch", "development tuning input failed strict validation"
        ) from exc


def build_holdout_access_receipt(
    manifest: EvaluationCorpusManifest,
    *,
    rows_read: int,
    bytes_read: int,
    tool_revision: str = "verify-retrieval-eval-v1",
    accessed_at: datetime | None = None,
) -> HoldoutAccessReceipt:
    """Create bounded metadata for one official integrity-only holdout read."""
    if accessed_at is None:
        accessed_at = datetime.now(UTC)
    return HoldoutAccessReceipt(
        schema_version="power.retrieval-holdout-access.v1",
        purpose="integrity_verification",
        split="holdout",
        dataset_revision=manifest.dataset_digest,
        query_set_digest=manifest.query_set_digest,
        accessed_at=accessed_at,
        tool_revision=tool_revision,
        tuning_capability=False,
        raw_content_egress=False,
        max_rows=MAX_JSONL_RECORDS,
        max_bytes=MAX_FILE_BYTES,
        rows_read=rows_read,
        bytes_read=bytes_read,
    )


def reject_holdout_tuning(split: str) -> None:
    if split != "development":
        raise EvaluationIntegrityError(
            "holdout_tuning_rejected", "holdout cannot be loaded by tuning tooling"
        )


EvaluationCorpusManifest.model_rebuild()
HoldoutAccessReceipt.model_rebuild()
register_runtime_contract("EvaluationCorpusManifest", EvaluationCorpusManifest)


__all__ = [
    "ACTIVE_EVALUATION_REVISION",
    "ACTIVE_PHASE5A1_DIGESTS",
    "EVALUATION_REVISION_REGISTRY",
    "FROZEN_PHASE5A_COUNTS",
    "FROZEN_PHASE5A_DIGESTS",
    "DevelopmentSplit",
    "DisjointnessProof",
    "EvaluationCategory",
    "EvaluationCorpusManifest",
    "EvaluationGroundTruth",
    "EvaluationIntegrityError",
    "EvaluationLanguage",
    "EvaluationQuery",
    "EvaluationSourceMetadata",
    "EvaluationVerificationSnapshot",
    "GroundTruthMethod",
    "GroundTruthProvenance",
    "HoldoutAccessReceipt",
    "HoldoutSplit",
    "SemanticAdjudicationArtifact",
    "SemanticAdjudicationRecord",
    "SemanticReviewReceipt",
    "build_holdout_access_receipt",
    "load_development_for_tuning",
    "normalize_query_text",
    "reject_holdout_tuning",
    "verify_evaluation_corpus",
]
