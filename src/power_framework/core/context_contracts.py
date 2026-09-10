"""POWER 3.8 Phase 5A runtime context contracts.

This module contains typed, side-effect-free data boundaries.  It deliberately
does not import a searcher, indexer, model runtime, network client, or planning
file.  The planning schemas remain governance evidence; this module exposes the
independent runtime identity ``power.context-runtime.v2``.
"""

from __future__ import annotations

import hashlib
import math
import re
from copy import deepcopy
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical_json import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Mapping

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_ENCODED_REFERENCE = re.compile(r"%(?:2e|2f|3a|5c)", re.IGNORECASE)
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"
_OPAQUE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$"
_DIGEST_PATTERN = r"^[a-f0-9]{64}$"
_SECRET_FREE_REASON_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,255}$"  # noqa: S105
_POLICY_ENGINE_TOKEN = object()
_AUTHORIZATION_BOUNDARY_TOKEN = object()
MAX_CONTEXT_PACK_BYTES = 2_000_000


def _validate_identifier(value: str) -> str:
    """Validate an identifier without giving it path, URL, or shell semantics."""
    if not re.fullmatch(_IDENTIFIER_PATTERN, value):
        raise ValueError("identifier has an unsupported shape")
    if value.startswith(("/", "\\")) or _WINDOWS_DRIVE.match(value):
        raise ValueError("identifier cannot be an absolute or drive path")
    if "://" in value or "\\" in value or _ENCODED_REFERENCE.search(value):
        raise ValueError("identifier cannot be a URI or escaped reference")
    if any(part == ".." for part in value.split("/")):
        raise ValueError("identifier cannot contain traversal segments")
    return value


def _validate_source_reference(value: str) -> str:
    """Validate a non-dereferenced, safe relative source reference."""
    if not value or len(value) > 512:
        raise ValueError("source reference must contain 1..512 characters")
    if value.startswith(("/", "\\")) or _WINDOWS_DRIVE.match(value):
        raise ValueError("source reference cannot be absolute")
    if _CONTROL_CHARACTERS.search(value):
        raise ValueError("source reference cannot contain control characters")
    if value.lower().startswith(("file:", "http:", "https:", "data:", "javascript:")):
        raise ValueError("source reference cannot use a URI scheme")
    if "://" in value or "\\" in value or _ENCODED_REFERENCE.search(value):
        raise ValueError("source reference contains an unsafe URI or escape")
    if any(part == ".." for part in value.split("/")):
        raise ValueError("source reference cannot contain traversal segments")
    return value


def _validate_opaque_reference(value: str) -> str:
    if not re.fullmatch(_OPAQUE_PATTERN, value):
        raise ValueError("opaque reference has an unsupported shape")
    return value


def _validate_digest(value: str) -> str:
    if not re.fullmatch(_DIGEST_PATTERN, value):
        raise ValueError("digest must be lowercase SHA-256 hexadecimal")
    return value


def _validate_reason(value: str) -> str:
    if not re.fullmatch(_SECRET_FREE_REASON_PATTERN, value):
        raise ValueError("reason must be bounded and secret-free")
    return value


def _require_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        if "T" not in value or not (value.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", value)):
            raise ValueError("timestamps must use RFC3339 date-time syntax")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamps must be valid RFC3339 datetimes") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return parsed
    raise ValueError("timestamps must be datetime or RFC3339 string values")


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _require_date(value: object) -> date:
    if isinstance(value, datetime):
        raise ValueError("temporal boundary must be a date without time")
    if isinstance(value, date):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("temporal boundary must be a valid ISO date") from exc
    raise ValueError("temporal boundary must be a date or ISO date string")


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("NaN and Infinity values are forbidden")
    return value


def _unique(values: list[Any] | None) -> list[Any] | None:
    if values is None:
        return None
    try:
        if len(values) != len(set(values)):
            raise ValueError("collection items must be unique")
    except TypeError as exc:
        raise ValueError("collection items must be hashable") from exc
    return values


def _canonicalize(value: Any) -> Any:
    """Convert validated model values to JSON primitives deterministically."""
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return _normalize_datetime(value).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON objects require string keys")
            result[key] = _canonicalize(nested)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, float):
        return _finite(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return compact UTF-8 canonical JSON bytes for validated values."""
    return canonical_json_bytes(_canonicalize(value))


def canonical_sha256(value: Any) -> str:
    """Return SHA-256 of :func:`canonical_bytes` as lowercase hexadecimal."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# Strict aliases keep booleans, numeric strings, and unbounded text from being
# silently coerced at a runtime boundary.
type Identifier = Annotated[
    StrictStr,
    Field(min_length=1, max_length=256),
    AfterValidator(_validate_identifier),
]
type SourceReference = Annotated[
    StrictStr,
    Field(min_length=1, max_length=512),
    AfterValidator(_validate_source_reference),
]
type OpaqueReference = Annotated[
    StrictStr,
    Field(min_length=1, max_length=256),
    AfterValidator(_validate_opaque_reference),
]
type Digest = Annotated[
    StrictStr,
    Field(min_length=64, max_length=64),
    AfterValidator(_validate_digest),
]
type ShortText = Annotated[StrictStr, Field(min_length=1, max_length=2048)]
type ReasonText = Annotated[
    StrictStr,
    Field(min_length=1, max_length=256),
    AfterValidator(_validate_reason),
]
type AwareDateTime = Annotated[
    datetime,
    BeforeValidator(_require_datetime),
    AfterValidator(_normalize_datetime),
]
type FiniteFloat = Annotated[StrictFloat, AfterValidator(_finite)]
type BoundedScore = Annotated[
    StrictFloat, Field(ge=-1_000_000_000, le=1_000_000_000), AfterValidator(_finite)
]
type PositiveInt = Annotated[StrictInt, Field(ge=1)]


class QueryIntentKind(StrEnum):
    LOOKUP = "lookup"
    PROJECT_STATE = "project_state"
    DECISION = "decision"
    TASK = "task"
    CODE = "code"
    INFRASTRUCTURE = "infrastructure"
    RESEARCH = "research"
    GOVERNANCE = "governance"
    CONVERSATION = "conversation"
    LOG = "log"
    CROSS_DOMAIN = "cross_domain"
    UNKNOWN = "unknown"


class BudgetClass(StrEnum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    DEEP = "DEEP"


class TrustState(StrEnum):
    RAW = "RAW"
    PROPOSED = "PROPOSED"
    CURATED = "CURATED"
    VERIFIED = "VERIFIED"
    CANONICAL = "CANONICAL"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    QUARANTINED = "QUARANTINED"
    NOISE = "NOISE"


class Authority(StrEnum):
    CANONICAL = "canonical"
    VERIFIED = "verified"
    CURATED = "curated"
    PROPOSED = "proposed"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"


class RetrievalStage(StrEnum):
    PROJECT_STATE = "project_state"
    METADATA = "metadata"
    FTS = "fts"
    TF = "tf"
    SEMANTIC = "semantic"
    GRAPH_ASSISTED = "graph_assisted"
    RRF = "rrf"
    TEMPORAL = "temporal"
    NOISE_GATE = "noise_gate"
    RERANK = "rerank"
    RAW_FALLBACK = "raw_fallback"
    MATERIALIZED_VIEW = "materialized_view"


class IndexPriority(StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class NoiseDisposition(StrEnum):
    INCLUDE = "INCLUDE"
    DOWNRANK = "DOWNRANK"
    EXCLUDE_FROM_RETRIEVAL = "EXCLUDE_FROM_RETRIEVAL"
    QUARANTINE = "QUARANTINE"


class MemoryDisposition(StrEnum):
    NOOP = "NOOP"
    RAW_ONLY = "RAW_ONLY"
    SESSION = "SESSION"
    WORKING = "WORKING"
    DURABLE_PROPOSAL = "DURABLE_PROPOSAL"
    CORRECTION_PROPOSAL = "CORRECTION_PROPOSAL"
    QUARANTINE = "QUARANTINE"
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"


class MemoryActionKind(StrEnum):
    NOOP = "NOOP"
    INDEX_FTS = "INDEX_FTS"
    QUEUE_DENSE = "QUEUE_DENSE"
    REFRESH_DOMAIN = "REFRESH_DOMAIN"
    RUN_DENSE = "RUN_DENSE"
    RUN_RERANK = "RUN_RERANK"
    PROMOTE_TO_WORKING = "PROMOTE_TO_WORKING"
    PROPOSE_DURABLE_MEMORY = "PROPOSE_DURABLE_MEMORY"
    PROPOSE_CORRECTION = "PROPOSE_CORRECTION"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    RUN_MAINTENANCE = "RUN_MAINTENANCE"
    REBUILD_PROJECTION = "REBUILD_PROJECTION"
    DEFER = "DEFER"
    QUARANTINE = "QUARANTINE"
    QUEUE_NEW_REVISION = "QUEUE_NEW_REVISION"


class RetentionClass(StrEnum):
    EPHEMERAL = "EPHEMERAL"
    SESSION = "SESSION"
    WORKING = "WORKING"
    DURABLE = "DURABLE"
    AUDIT_METADATA = "AUDIT_METADATA"


class SensitivityClass(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"
    SECRET = "SECRET"  # noqa: S105 - sensitivity vocabulary, not a credential.


class ResourceProfileClass(StrEnum):
    LOW_RESOURCE = "LOW_RESOURCE"
    STANDARD = "STANDARD"
    PERFORMANCE = "PERFORMANCE"
    CUSTOM = "CUSTOM"


class ModelLoadPolicy(StrEnum):
    FORBIDDEN = "forbidden"
    SELECTED_DOMAIN_ONLY = "selected_domain_only"
    EXPLICIT_REQUEST_OR_ESCALATION = "explicit_request_or_escalation"


class NoiseLayer(StrEnum):
    DETERMINISTIC_CHEAP = "deterministic_cheap"
    SEMANTIC = "semantic"
    UNSAFE_QUARANTINE = "unsafe_quarantine"


class Freshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    FUTURE = "future"
    UNKNOWN = "unknown"


class ContradictionState(StrEnum):
    NONE = "none"
    UNRESOLVED = "unresolved"
    CONFLICTED = "conflicted"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


class NoiseState(StrEnum):
    CLEAN = "clean"
    DOWNRANKED = "downranked"
    EXCLUDED = "excluded"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


class AuthorityBasis(StrEnum):
    CANONICAL_LEDGER = "canonical_ledger"
    VERIFIED_PROJECTION = "verified_projection"
    CURATED_NOTE = "curated_note"
    PROPOSAL = "proposal"
    RAW_CAPTURE = "raw_capture"
    UNKNOWN = "unknown"


class QueueState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DEFERRED = "deferred"
    COMPLETE = "complete"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class ReceiptKind(StrEnum):
    TOMBSTONE = "TOMBSTONE"
    DELETION = "DELETION"


class TombstonePayloadAction(StrEnum):
    RETAINED = "RETAINED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


class DefaultMemoryClass(StrEnum):
    LOW = "LOW"
    STANDARD = "STANDARD"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class DefaultModelPolicy(StrEnum):
    NO_MODEL_LOAD = "NO_MODEL_LOAD"
    OPTIONAL_LOCAL = "OPTIONAL_LOCAL"
    PROFILE_SELECTED = "PROFILE_SELECTED"


class BudgetLayerSource(StrEnum):
    STRUCTURAL_ABSOLUTE_SAFETY_CEILING = "structural_absolute_safety_ceiling"
    RESOURCE_PROFILE_DEFAULT = "resource_profile_default"
    DOMAIN_POLICY_CAP = "domain_policy_cap"
    CALLER_HINT = "caller_hint"


class RetryStrategy(StrEnum):
    EXPONENTIAL = "exponential"
    BOUNDED_EXPONENTIAL = "bounded_exponential"


class IntentClass(StrEnum):
    PROJECT_STATE = "project_state"
    DECISION = "decision"
    TASK = "task"
    GOVERNANCE = "governance"
    OTHER = "other"


class ContractName(StrEnum):
    QUERY_INTENT = "QueryIntent"
    RETRIEVAL_BUDGET = "RetrievalBudget"
    SEARCH_SCOPE = "SearchScope"
    DOMAIN_MATCH = "DomainMatch"
    RETRIEVAL_STAGE = "RetrievalStage"
    RETRIEVAL_PLAN = "RetrievalPlan"
    NOISE_ASSESSMENT = "NoiseAssessment"
    CONTEXT_ITEM = "ContextItem"
    CONTEXT_PACK = "ContextPack"
    INDEX_WORK_ITEM = "IndexWorkItem"
    INDEX_COST_ESTIMATE = "IndexCostEstimate"
    MEMORY_DISPOSITION = "MemoryDisposition"
    MEMORY_ACTION = "MemoryAction"
    RETENTION_CLASS = "RetentionClass"
    SENSITIVITY_CLASS = "SensitivityClass"
    PAYLOAD_RETENTION_POLICY = "PayloadRetentionPolicy"
    TOMBSTONE_RECEIPT = "TombstoneReceipt"
    BITEMPORAL_EVIDENCE = "BitemporalEvidence"
    EVIDENCE_ORDERING_POLICY = "EvidenceOrderingPolicy"
    RESOURCE_PROFILE = "ResourceProfile"
    HOST_CAPABILITY_PROFILE = "HostCapabilityProfile"
    RETRIEVAL_BUDGET_POLICY = "RetrievalBudgetPolicy"
    RETRY_POLICY = "RetryPolicy"
    EVALUATION_CORPUS_MANIFEST = "EvaluationCorpusManifest"


class RuntimeModel(BaseModel):
    """Frozen strict base for all Phase 5A DTOs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        # Strict scalar aliases below reject unsafe numeric/bool coercion while
        # enum values retain the repository's normal string-backed wire form.
        strict=False,
        validate_assignment=True,
        use_enum_values=False,
        revalidate_instances="never",
    )

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        for field_name in self.model_fields_set:
            if getattr(self, field_name, object()) is None:
                raise ValueError(f"{field_name} must be omitted rather than null")
        return self

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Revalidate copies and revoke server-issued private authority markers."""
        data = self.model_dump(mode="python", exclude_none=True)
        if deep:
            data = deepcopy(data)
        if update:
            data.update(update)
        if hasattr(self, "_issuer_token"):
            return type(self).model_construct(**data)
        return type(self).model_validate(data)

    def to_canonical_dict(self) -> dict[str, Any]:
        dumped = self.model_dump(mode="python", exclude_none=True)
        result = _canonicalize(dumped)
        if not isinstance(result, dict):
            raise TypeError("runtime model did not serialize to an object")
        return cast("dict[str, Any]", result)

    def to_canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_dict())

    def to_canonical_json(self) -> str:
        return self.to_canonical_bytes().decode("utf-8")

    def digest(self) -> str:
        return hashlib.sha256(self.to_canonical_bytes()).hexdigest()


class TemporalBoundary(RuntimeModel):
    as_of: date
    include_historical: StrictBool

    _strict_as_of = field_validator("as_of", mode="before")(_require_date)


class QueryIntent(RuntimeModel):
    query: ShortText
    intent: QueryIntentKind
    budget_class: BudgetClass
    domain_hints: list[Identifier] | None = Field(default=None, max_length=32)
    project_ids: list[Identifier] | None = Field(default=None, max_length=128)
    temporal_boundary: TemporalBoundary | None = None
    include_archived: StrictBool = False
    include_quarantine: StrictBool = False
    max_tokens: Annotated[StrictInt, Field(ge=1, le=30_000)] | None = None

    _unique_domain_hints = field_validator("domain_hints", "project_ids")(_unique)


class RetrievalBudget(RuntimeModel):
    budget_class: BudgetClass
    max_candidates: Annotated[StrictInt, Field(ge=1, le=10_000)]
    max_tokens: Annotated[StrictInt, Field(ge=1, le=100_000)]
    max_domains: Annotated[StrictInt, Field(ge=1, le=64)]
    max_graph_hops: Annotated[StrictInt, Field(ge=0, le=8)]
    stages: list[RetrievalStage] = Field(min_length=1, max_length=16)
    model_load: ModelLoadPolicy
    dense_allowed: StrictBool
    reranker_allowed: StrictBool
    graph_allowed: StrictBool
    deep_expansion_allowed: StrictBool
    raw_fallback_allowed: StrictBool

    _unique_stages = field_validator("stages")(_unique)

    @model_validator(mode="after")
    def validate_class_capabilities(self) -> Self:
        caps = {
            BudgetClass.FAST: (40, 4_000, 3, 0),
            BudgetClass.BALANCED: (120, 12_000, 4, 0),
            BudgetClass.DEEP: (400, 30_000, 16, 3),
        }[self.budget_class]
        if self.max_candidates > caps[0] or self.max_tokens > caps[1]:
            raise ValueError("budget exceeds the selected structural class cap")
        if self.max_domains > caps[2] or self.max_graph_hops > caps[3]:
            raise ValueError("budget exceeds the selected class domain/hop cap")
        if self.budget_class is BudgetClass.FAST:
            if self.model_load is not ModelLoadPolicy.FORBIDDEN or any(
                (
                    self.dense_allowed,
                    self.reranker_allowed,
                    self.graph_allowed,
                    self.deep_expansion_allowed,
                    self.raw_fallback_allowed,
                )
            ):
                raise ValueError("FAST budget cannot enable model or deep stages")
            if any(
                stage in self.stages
                for stage in (
                    RetrievalStage.SEMANTIC,
                    RetrievalStage.GRAPH_ASSISTED,
                    RetrievalStage.RERANK,
                    RetrievalStage.RAW_FALLBACK,
                )
            ):
                raise ValueError("FAST budget cannot plan expensive stages")
        if self.budget_class is BudgetClass.BALANCED:
            if self.model_load is not ModelLoadPolicy.SELECTED_DOMAIN_ONLY:
                raise ValueError("BALANCED budget requires selected-domain model policy")
            if not self.dense_allowed or not self.reranker_allowed:
                raise ValueError("BALANCED budget requires dense and reranker flags")
            if self.graph_allowed or self.deep_expansion_allowed or self.raw_fallback_allowed:
                raise ValueError("BALANCED budget cannot enable deep graph/raw fallback")
            if (
                RetrievalStage.GRAPH_ASSISTED in self.stages
                or RetrievalStage.RAW_FALLBACK in self.stages
            ):
                raise ValueError("BALANCED budget cannot plan graph/raw fallback")
        if (
            self.budget_class is BudgetClass.DEEP
            and self.model_load is not ModelLoadPolicy.EXPLICIT_REQUEST_OR_ESCALATION
        ):
            raise ValueError("DEEP budget requires explicit escalation model policy")
        if self.budget_class is BudgetClass.DEEP and not all(
            (
                self.dense_allowed,
                self.reranker_allowed,
                self.graph_allowed,
                self.deep_expansion_allowed,
                self.raw_fallback_allowed,
            )
        ):
            raise ValueError("DEEP budget requires all escalation flags")
        return self


class SearchScope(RuntimeModel):
    domain_ids: list[Identifier] = Field(default_factory=list, max_length=64)
    path_prefixes: list[SourceReference] = Field(default_factory=list, max_length=128)
    source_types: list[Identifier] = Field(default_factory=list, max_length=64)
    trust_states: list[TrustState] = Field(default_factory=list, max_length=9)
    temporal_boundary: TemporalBoundary
    project_ids: list[Identifier] = Field(default_factory=list, max_length=128)
    include_archived: StrictBool = False
    include_quarantine: StrictBool = False

    _unique_scope_values = field_validator(
        "domain_ids", "path_prefixes", "source_types", "trust_states", "project_ids"
    )(_unique)


class DomainMatch(RuntimeModel):
    domain: Identifier
    score: Annotated[StrictFloat, Field(ge=0.0, le=1.0), AfterValidator(_finite)]
    reasons: list[ShortText] = Field(min_length=1, max_length=16)

    _unique_reasons = field_validator("reasons")(_unique)


class Provenance(RuntimeModel):
    source_refs: list[SourceReference] = Field(min_length=1, max_length=128)
    source_revision: Identifier
    event_ids: list[Identifier] | None = Field(default=None, max_length=128)
    authority_basis: AuthorityBasis

    _unique_refs = field_validator("source_refs", "event_ids")(_unique)


class RetrievalPlan(RuntimeModel):
    planner_revision: Identifier
    stages: list[RetrievalStage] = Field(min_length=1, max_length=16)
    attempted_stages: list[RetrievalStage] = Field(default_factory=list, max_length=16)
    skipped_stages: list[RetrievalStage] = Field(default_factory=list, max_length=16)
    domain_matches: list[DomainMatch] = Field(max_length=64)
    scope: SearchScope
    budget: RetrievalBudget
    escalation_reason: str = Field(max_length=2048)

    _unique_plan_stages = field_validator("stages", "attempted_stages", "skipped_stages")(_unique)

    @model_validator(mode="after")
    def validate_stage_partition(self) -> Self:
        planned = set(self.stages)
        attempted = set(self.attempted_stages)
        skipped = set(self.skipped_stages)
        if not attempted <= planned or not skipped <= planned:
            raise ValueError("attempted and skipped stages must be planned")
        if attempted & skipped:
            raise ValueError("a stage cannot be both attempted and skipped")
        if attempted | skipped != planned:
            raise ValueError("every planned stage must be attempted or skipped")
        if RetrievalStage.SEMANTIC in planned and not self.budget.dense_allowed:
            raise ValueError("semantic stage requires dense permission")
        if RetrievalStage.RERANK in planned and not self.budget.reranker_allowed:
            raise ValueError("rerank stage requires reranker permission")
        if RetrievalStage.GRAPH_ASSISTED in planned and not self.budget.graph_allowed:
            raise ValueError("graph stage requires graph permission")
        if RetrievalStage.RAW_FALLBACK in planned and not self.budget.raw_fallback_allowed:
            raise ValueError("raw fallback stage requires raw fallback permission")
        return self


class NoiseAssessment(RuntimeModel):
    action: NoiseDisposition
    layers: list[NoiseLayer] = Field(min_length=1, max_length=3)
    reasons: list[ShortText] = Field(min_length=1, max_length=16)
    confidence: Annotated[StrictFloat, Field(ge=0.0, le=1.0), AfterValidator(_finite)]
    source_preserved: Literal[True]
    trust_state: TrustState

    _unique_layers = field_validator("layers", "reasons")(_unique)

    @model_validator(mode="after")
    def validate_quarantine(self) -> Self:
        if NoiseLayer.UNSAFE_QUARANTINE in self.layers:
            if self.action is not NoiseDisposition.QUARANTINE:
                raise ValueError("unsafe quarantine layer requires QUARANTINE")
            if self.trust_state is not TrustState.QUARANTINED:
                raise ValueError("quarantine disposition requires QUARANTINED trust")
        if (
            self.action is NoiseDisposition.QUARANTINE
            and self.trust_state is not TrustState.QUARANTINED
        ):
            raise ValueError("QUARANTINE requires QUARANTINED trust")
        return self


_TRUST_AUTHORITY_COMPATIBILITY: dict[TrustState, set[Authority]] = {
    TrustState.RAW: {Authority.UNKNOWN, Authority.PROPOSED, Authority.UNVERIFIED},
    TrustState.QUARANTINED: {Authority.UNKNOWN, Authority.PROPOSED, Authority.UNVERIFIED},
    TrustState.CANONICAL: {Authority.CANONICAL},
    TrustState.VERIFIED: {Authority.VERIFIED, Authority.CANONICAL},
    TrustState.CURATED: {Authority.CURATED, Authority.VERIFIED, Authority.CANONICAL},
    TrustState.PROPOSED: {Authority.PROPOSED, Authority.UNVERIFIED, Authority.UNKNOWN},
    TrustState.SUPERSEDED: set(Authority),
    TrustState.ARCHIVED: set(Authority),
    TrustState.NOISE: {Authority.UNKNOWN, Authority.PROPOSED, Authority.UNVERIFIED},
}

_AUTHORITY_BASIS_COMPATIBILITY: dict[Authority, set[AuthorityBasis]] = {
    Authority.CANONICAL: {
        AuthorityBasis.CANONICAL_LEDGER,
        AuthorityBasis.VERIFIED_PROJECTION,
        AuthorityBasis.CURATED_NOTE,
    },
    Authority.VERIFIED: {AuthorityBasis.CANONICAL_LEDGER, AuthorityBasis.VERIFIED_PROJECTION},
    Authority.CURATED: {AuthorityBasis.CURATED_NOTE, AuthorityBasis.VERIFIED_PROJECTION},
    Authority.PROPOSED: {
        AuthorityBasis.PROPOSAL,
        AuthorityBasis.RAW_CAPTURE,
        AuthorityBasis.UNKNOWN,
    },
    Authority.UNVERIFIED: {
        AuthorityBasis.PROPOSAL,
        AuthorityBasis.RAW_CAPTURE,
        AuthorityBasis.UNKNOWN,
    },
    Authority.UNKNOWN: {
        AuthorityBasis.PROPOSAL,
        AuthorityBasis.RAW_CAPTURE,
        AuthorityBasis.UNKNOWN,
    },
}


def validate_trust_authority(trust_state: TrustState, authority: Authority) -> None:
    """Enforce the approved v1 trust↔authority compatibility matrix."""
    if authority not in _TRUST_AUTHORITY_COMPATIBILITY[trust_state]:
        raise ValueError("trust state cannot claim the supplied authority")


class ContextItem(RuntimeModel):
    source_id: Identifier
    source_type: Identifier
    authority: Authority
    trust_state: TrustState
    domain: Identifier
    domains: list[Identifier] = Field(min_length=1, max_length=64)
    score: BoundedScore
    retrieval_stage: RetrievalStage
    provenance: Provenance
    freshness: Freshness
    contradiction_state: ContradictionState
    noise_state: NoiseState
    token_cost: Annotated[StrictInt, Field(ge=0, le=100_000)]
    excerpt: str = Field(max_length=12_000)
    content_kind: Literal["excerpt", "reference"]
    redaction_status: Literal["not_applicable", "redacted", "verified_safe"]

    _unique_domains = field_validator("domains")(_unique)

    @model_validator(mode="after")
    def validate_evidence_axes(self) -> Self:
        if self.domain not in self.domains:
            raise ValueError("primary domain must be present in domains")
        validate_trust_authority(self.trust_state, self.authority)
        if self.provenance.authority_basis not in _AUTHORITY_BASIS_COMPATIBILITY[self.authority]:
            raise ValueError("provenance basis cannot support the claimed authority")
        if self.trust_state is TrustState.QUARANTINED:
            if self.noise_state is not NoiseState.QUARANTINED:
                raise ValueError("QUARANTINED evidence requires quarantined noise state")
            if self.redaction_status == "not_applicable":
                raise ValueError("quarantined evidence requires redaction or safe rendering")
        if self.trust_state is TrustState.NOISE and self.noise_state not in {
            NoiseState.EXCLUDED,
            NoiseState.DOWNRANKED,
        }:
            raise ValueError("NOISE evidence must be excluded or downranked")
        if (
            self.trust_state in {TrustState.RAW, TrustState.QUARANTINED}
            and self.redaction_status == "not_applicable"
        ):
            raise ValueError("raw or quarantined evidence requires redaction metadata")
        if self.content_kind == "excerpt" and self.excerpt and self.token_cost == 0:
            raise ValueError("non-empty excerpts require a positive token cost")
        return self


class ExcludedItem(RuntimeModel):
    source_id: Identifier
    reason: ShortText


class ContextBudget(RuntimeModel):
    max_tokens: Annotated[StrictInt, Field(ge=1, le=30_000)]
    consumed_tokens: Annotated[StrictInt, Field(ge=0, le=30_000)]
    dense_used: StrictBool
    reranker_used: StrictBool
    index_work_triggered: Literal[False]
    budget_satisfied: Literal[True]

    @model_validator(mode="after")
    def validate_consumption(self) -> Self:
        if self.consumed_tokens > self.max_tokens:
            raise ValueError("consumed_tokens cannot exceed max_tokens")
        return self


class Explainability(RuntimeModel):
    summary: ShortText
    decisions: list[ShortText] = Field(max_length=64)
    source_revisions: list[Identifier] = Field(max_length=128)

    _unique_revisions = field_validator("source_revisions")(_unique)


class _AccessPolicyPayload(RuntimeModel):
    origin: Literal["authorization_boundary"]
    actor: Identifier
    raw_access: Literal["none", "privileged"]
    quarantine_access: Literal["none", "privileged"]
    redaction: Literal["mandatory"]
    capability_id: Identifier
    expires_at: AwareDateTime
    approval_ref: SourceReference | None = None

    @model_validator(mode="after")
    def validate_privileged_access(self) -> Self:
        if (
            self.raw_access == "privileged" or self.quarantine_access == "privileged"
        ) and self.approval_ref is None:
            raise ValueError("privileged access requires an explicit approval reference")
        return self


class AccessPolicy(_AccessPolicyPayload):
    """Server-issued access output, never a caller-supplied authority token."""

    _issuer_token: object | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def require_authorization_boundary(self) -> Self:
        if self._issuer_token is not _AUTHORIZATION_BOUNDARY_TOKEN:
            raise ValueError("AccessPolicy must be issued by the authorization boundary")
        return self

    @classmethod
    def _from_authorization_boundary(cls, **data: Any) -> Self:
        validated = _AccessPolicyPayload.model_validate(data)
        instance = cls.model_construct(**validated.model_dump(exclude_none=True))
        instance._issuer_token = _AUTHORIZATION_BOUNDARY_TOKEN
        return instance


class ContextPack(RuntimeModel):
    request_id: Identifier
    query: ShortText
    intent: QueryIntentKind
    budget_class: BudgetClass
    domains: list[DomainMatch] = Field(max_length=64)
    retrieval_plan: RetrievalPlan
    items: list[ContextItem] = Field(max_length=1_000)
    excluded: list[ExcludedItem] = Field(max_length=1_000)
    budget: ContextBudget
    explainability: Explainability
    retrieval_status: Literal["complete", "partial", "degraded", "failed"]
    fallback_reason: str = Field(max_length=2_048)
    policy_revision: Identifier
    generation_revision: Identifier
    implementation_status: Literal["planned"]
    access_policy: AccessPolicy

    @model_validator(mode="after")
    def validate_pack_access(self) -> Self:
        if self.access_policy._issuer_token is not _AUTHORIZATION_BOUNDARY_TOKEN:
            raise ValueError("ContextPack requires a server-issued access policy")
        if self.retrieval_status in {"degraded", "failed"} and not self.fallback_reason:
            raise ValueError("degraded or failed packs require a bounded fallback reason")
        if self.budget_class is not self.retrieval_plan.budget.budget_class:
            raise ValueError("pack budget class must match its retrieval plan")
        if self.budget.max_tokens > self.retrieval_plan.budget.max_tokens:
            raise ValueError("pack token ceiling cannot exceed the retrieval budget")
        if len(self.items) > self.retrieval_plan.budget.max_candidates:
            raise ValueError("pack item count cannot exceed candidate budget")
        actual_tokens = sum(item.token_cost for item in self.items)
        if actual_tokens != self.budget.consumed_tokens:
            raise ValueError("consumed_tokens must equal the bounded item token cost")
        actual_bytes = sum(len(item.excerpt.encode("utf-8")) for item in self.items)
        if actual_bytes > MAX_CONTEXT_PACK_BYTES:
            raise ValueError("context pack exceeds the aggregate byte ceiling")
        if self.budget.dense_used and not self.retrieval_plan.budget.dense_allowed:
            raise ValueError("dense usage is not allowed by the retrieval budget")
        if self.budget.reranker_used and not self.retrieval_plan.budget.reranker_allowed:
            raise ValueError("reranker usage is not allowed by the retrieval budget")
        if (
            any(item.trust_state is TrustState.RAW for item in self.items)
            and self.access_policy.raw_access != "privileged"
        ):
            raise ValueError("raw context requires privileged access policy")
        if (
            any(item.trust_state is TrustState.QUARANTINED for item in self.items)
            and self.access_policy.quarantine_access != "privileged"
        ):
            raise ValueError("quarantine context requires privileged access policy")
        return self


class IndexWorkItem(RuntimeModel):
    source_id: Identifier
    source_revision: Identifier
    domain_ids: list[Identifier] = Field(max_length=64)
    chunk_ids: list[Identifier] = Field(max_length=10_000)
    chunk_revision: Identifier | None = None
    priority: IndexPriority
    reason: ShortText
    embedding_model_revision: Identifier
    estimated_work: Annotated[StrictFloat, Field(ge=0.0, le=10_000_000), AfterValidator(_finite)]
    created_at: AwareDateTime
    queue_state: QueueState
    retry_count: Annotated[StrictInt, Field(ge=0, le=100)]
    idempotency_key: Identifier
    last_error: ReasonText | None = None
    deferred_until: AwareDateTime | None = None
    lease_id: Identifier | None = None
    lease_expires_at: AwareDateTime | None = None

    _unique_work_ids = field_validator("domain_ids", "chunk_ids")(_unique)

    @model_validator(mode="after")
    def validate_queue_shape(self) -> Self:
        if self.queue_state is QueueState.DEFERRED and self.deferred_until is None:
            raise ValueError("deferred work requires deferred_until")
        if self.queue_state is QueueState.RUNNING and (
            self.lease_id is None or self.lease_expires_at is None
        ):
            raise ValueError("running work requires an active lease")
        if self.queue_state in {QueueState.FAILED, QueueState.DEAD_LETTER} and not self.last_error:
            raise ValueError("failed work requires a bounded error category")
        return self


class IndexCostEstimate(RuntimeModel):
    affected_sources: Annotated[StrictInt, Field(ge=0, le=1_000_000)]
    affected_chunks: Annotated[StrictInt, Field(ge=0, le=10_000_000)]
    model_required: StrictBool
    priority: IndexPriority
    estimated_memory_class: Literal["low", "medium", "high", "unknown"]
    estimated_cpu_class: Literal["low", "medium", "high", "unknown"]
    full_rebuild: StrictBool
    reason: ShortText


class _MemoryActionPayload(RuntimeModel):
    action: MemoryActionKind
    signal: ShortText
    domain: Identifier
    trust_state: TrustState
    authority: Authority | None = None
    confidence: Annotated[StrictFloat, Field(ge=0.0, le=1.0), AfterValidator(_finite)]
    reason: ShortText
    policy_revision: Identifier

    @model_validator(mode="after")
    def validate_payload_axes(self) -> Self:
        if self.trust_state in {
            TrustState.RAW,
            TrustState.QUARANTINED,
            TrustState.NOISE,
        } and self.authority in {Authority.CANONICAL, Authority.VERIFIED}:
            raise ValueError("untrusted memory action cannot claim canonical authority")
        return self


class MemoryActionDecision(RuntimeModel):
    """Server-derived policy output; it is not a caller input authority."""

    action: MemoryActionKind
    signal: ShortText
    domain: Identifier
    trust_state: TrustState
    authority: Authority | None = None
    confidence: Annotated[StrictFloat, Field(ge=0.0, le=1.0), AfterValidator(_finite)]
    reason: ShortText
    origin: Literal["policy_engine"]
    policy_revision: Identifier
    server_derived: Literal[True]
    _issuer_token: object | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def require_policy_issuer(self) -> Self:
        if self._issuer_token is not _POLICY_ENGINE_TOKEN:
            raise ValueError("MemoryAction is server-derived and cannot be caller-created")
        return self

    @classmethod
    def _from_policy_engine(cls, **data: Any) -> Self:
        payload = {
            key: value for key, value in data.items() if key not in {"origin", "server_derived"}
        }
        validated = _MemoryActionPayload.model_validate(payload)
        instance = cls.model_construct(
            **validated.model_dump(exclude_none=True), origin="policy_engine", server_derived=True
        )
        instance._issuer_token = _POLICY_ENGINE_TOKEN
        return instance


class RetentionClassContract(RuntimeModel):
    value: RetentionClass
    description: str | None = Field(default=None, max_length=512)


class SensitivityClassContract(RuntimeModel):
    value: SensitivityClass
    description: str | None = Field(default=None, max_length=512)


class PayloadRetentionPolicy(RuntimeModel):
    retention_class: RetentionClass
    sensitivity_class: SensitivityClass
    payload_action: Literal["RETAIN", "EXPIRE", "DELETE_AFTER_ELIGIBILITY", "LEGAL_HOLD"]
    expires_at: AwareDateTime | None = None
    audit_metadata_retained: Literal[True]
    policy_revision: OpaqueReference
    noise_disposition: NoiseDisposition
    source_delete_requires_explicit_policy: Literal[True]
    description: str | None = Field(default=None, max_length=1_024)

    @model_validator(mode="after")
    def validate_noise_retention(self) -> Self:
        if (
            self.noise_disposition is NoiseDisposition.QUARANTINE
            and self.payload_action == "DELETE_AFTER_ELIGIBILITY"
        ):
            raise ValueError("noise or quarantine alone cannot authorize source deletion")
        return self


class TombstoneReceipt(RuntimeModel):
    receipt_id: OpaqueReference
    receipt_kind: ReceiptKind
    source_ref: OpaqueReference
    source_revision: Digest
    payload_action: TombstonePayloadAction
    payload_digest: Digest
    metadata_digest: Digest
    observed_at: AwareDateTime
    recorded_at: AwareDateTime
    policy_revision: OpaqueReference
    authorization_ref: OpaqueReference
    sensitivity_class: SensitivityClass
    redaction_policy_revision: OpaqueReference
    payload_eligibility_proof: OpaqueReference
    audit_metadata_retained: Literal[True]
    noise_never_deletes_source: Literal[True]
    reason: ReasonText
    reason_is_secret_free: Literal[True]

    @model_validator(mode="after")
    def validate_receipt_action(self) -> Self:
        if (
            self.receipt_kind is ReceiptKind.DELETION
            and self.payload_action is not TombstonePayloadAction.DELETED
        ):
            raise ValueError("DELETION receipt requires DELETED payload action")
        if (
            self.receipt_kind is ReceiptKind.TOMBSTONE
            and self.payload_action is TombstonePayloadAction.DELETED
        ):
            raise ValueError("TOMBSTONE receipt cannot claim payload deletion")
        return self


class BitemporalEvidence(RuntimeModel):
    observed_at: AwareDateTime
    recorded_at: AwareDateTime
    valid_from: AwareDateTime | None = None
    valid_to: AwareDateTime | None = None
    correction_of: OpaqueReference | None = None
    delayed_capture: StrictBool | None = None
    correction_reason: str | None = Field(default=None, max_length=1_024)

    @model_validator(mode="after")
    def validate_validity_interval(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must be greater than or equal to valid_from")
        return self


class EvidenceOrderingPolicy(RuntimeModel):
    intent_class: IntentClass
    ordered_stages: tuple[str, ...]
    authority_sensitive: StrictBool
    authority_rank: tuple[str, ...]
    semantic_relevance_may_override_authority: Literal[False]
    supersession_precedes_relevance: Literal[True]
    score_model: Literal["separate-explainable-stages"]

    @model_validator(mode="after")
    def validate_ordering(self) -> Self:
        expected_stages = (
            "access_policy",
            "authority_policy",
            "temporal_validity",
            "supersession",
            "contradiction_state",
            "semantic_relevance",
            "reranking",
            "diversity_token_packing",
        )
        expected_authority = ("canonical", "verified", "curated", "proposed", "raw", "unknown")
        if self.ordered_stages != expected_stages:
            raise ValueError("evidence stages must preserve the approved explainable order")
        if self.authority_rank != expected_authority:
            raise ValueError("authority rank must preserve the approved order")
        if (
            self.intent_class
            in {
                IntentClass.PROJECT_STATE,
                IntentClass.DECISION,
                IntentClass.TASK,
                IntentClass.GOVERNANCE,
            }
            and not self.authority_sensitive
        ):
            raise ValueError("authority-sensitive intents require authority_sensitive=true")
        return self


class ResourceProfile(RuntimeModel):
    profile_class: ResourceProfileClass
    calibration_status: Literal["phase5_shadow_benchmark_required"]
    numeric_defaults_are_hypotheses: Literal[True]
    host_specific_facts_are_not_framework_invariants: Literal[True]
    default_max_workers: Annotated[StrictInt, Field(ge=1, le=64)] | None = None
    default_memory_class: DefaultMemoryClass | None = None
    default_model_policy: DefaultModelPolicy | None = None


class HostCapabilityProfile(RuntimeModel):
    profile_id: OpaqueReference
    resource_profile: ResourceProfileClass
    deployment_profile_ref: OpaqueReference
    cpu_class: StrictStr | None = Field(default=None, max_length=128)
    memory_class: StrictStr | None = Field(default=None, max_length=128)
    model_capabilities: list[StrictStr] | None = Field(default=None, max_length=32)
    benchmark_evidence_ref: OpaqueReference | None = None
    framework_invariants_excluded: Literal[True]

    _unique_capabilities = field_validator("model_capabilities")(_unique)


class ProfileBudgetLayer(RuntimeModel):
    source: BudgetLayerSource
    max_candidates: Annotated[StrictInt, Field(ge=1, le=10_000)] | None = None
    max_tokens: Annotated[StrictInt, Field(ge=1, le=1_000_000)] | None = None
    max_domains: Annotated[StrictInt, Field(ge=1, le=256)] | None = None
    max_graph_hops: Annotated[StrictInt, Field(ge=0, le=32)] | None = None
    lower_only: StrictBool

    @model_validator(mode="after")
    def validate_lower_only(self) -> Self:
        if self.source is BudgetLayerSource.CALLER_HINT and not self.lower_only:
            raise ValueError("caller hint must be lower-only")
        if self.source is not BudgetLayerSource.CALLER_HINT and self.lower_only:
            raise ValueError("only caller hints may be marked lower-only")
        return self


class BudgetProfile(RuntimeModel):
    max_candidates: Annotated[StrictInt, Field(ge=1, le=10_000)]
    max_tokens: Annotated[StrictInt, Field(ge=1, le=1_000_000)]
    max_domains: Annotated[StrictInt, Field(ge=1, le=256)]
    max_graph_hops: Annotated[StrictInt, Field(ge=0, le=32)]
    model_load: ModelLoadPolicy
    numeric_default_is_hypothesis: Literal[True]


class BudgetProfiles(RuntimeModel):
    FAST: BudgetProfile
    BALANCED: BudgetProfile
    DEEP: BudgetProfile


class RetrievalBudgetPolicy(RuntimeModel):
    structural_absolute_safety_ceiling: ProfileBudgetLayer
    resource_profile_default: ProfileBudgetLayer
    domain_policy_cap: ProfileBudgetLayer
    caller_hint: ProfileBudgetLayer
    effective_limit_rule: Literal[
        "min(structural_ceiling, resource_default, domain_cap, caller_hint_when_present)"
    ]
    defaults_calibration: Literal["phase5_shadow_benchmark_required"]
    numeric_defaults_are_not_product_constants: Literal[True]
    profiles: BudgetProfiles

    @model_validator(mode="after")
    def validate_layer_sources(self) -> Self:
        expected = {
            "structural_absolute_safety_ceiling": BudgetLayerSource.STRUCTURAL_ABSOLUTE_SAFETY_CEILING,
            "resource_profile_default": BudgetLayerSource.RESOURCE_PROFILE_DEFAULT,
            "domain_policy_cap": BudgetLayerSource.DOMAIN_POLICY_CAP,
            "caller_hint": BudgetLayerSource.CALLER_HINT,
        }
        for name, source in expected.items():
            if getattr(self, name).source is not source:
                raise ValueError(f"{name} has an incompatible budget layer source")
        return self


class BackoffPolicy(RuntimeModel):
    strategy: RetryStrategy
    initial_delay_ms: Annotated[StrictInt, Field(ge=0, le=300_000)]
    multiplier: Annotated[StrictFloat, Field(ge=1.0, le=8.0), AfterValidator(_finite)]
    max_delay_ms: Annotated[StrictInt, Field(ge=0, le=3_600_000)]
    jitter: StrictBool

    @model_validator(mode="after")
    def validate_delay_bounds(self) -> Self:
        if self.max_delay_ms < self.initial_delay_ms:
            raise ValueError("max_delay_ms must not be below initial_delay_ms")
        return self


class RetryPolicy(RuntimeModel):
    max_automatic_retries: Annotated[StrictInt, Field(ge=0, le=3)]
    max_total_requeues: Annotated[StrictInt, Field(ge=0, le=10)]
    max_manual_requeues: Annotated[StrictInt, Field(ge=0, le=3)]
    backoff: BackoffPolicy
    dead_letter_after_exhaustion: Literal[True]
    explicit_review_before_requeue: Literal[True]
    requeue_requires_revision_check: Literal[True]
    no_unbounded_retries: Literal[True]
    secret_free_error_receipt: Literal[True]

    @model_validator(mode="after")
    def validate_retry_relationships(self) -> Self:
        if self.max_total_requeues < self.max_automatic_retries + self.max_manual_requeues:
            raise ValueError("total requeues must cover automatic and manual requeues")
        if self.max_automatic_retries and (
            self.backoff.initial_delay_ms < 1 or self.backoff.max_delay_ms < 1
        ):
            raise ValueError("automatic retries require a positive bounded backoff")
        return self


class CallerBudgetEscalationError(ValueError):
    """Raised when caller input attempts to raise a server-selected cap."""


def resolve_budget_caps(policy: RetrievalBudgetPolicy, budget_class: BudgetClass) -> BudgetProfile:
    """Resolve pure layered caps; caller hints may only lower server limits."""
    baseline = getattr(policy.profiles, budget_class.value)
    server_layers = (
        policy.structural_absolute_safety_ceiling,
        policy.resource_profile_default,
        policy.domain_policy_cap,
    )
    fields = ("max_candidates", "max_tokens", "max_domains", "max_graph_hops")
    effective: dict[str, int] = {}
    for field_name in fields:
        server_values = [getattr(baseline, field_name)]
        server_values.extend(
            value for layer in server_layers if (value := getattr(layer, field_name)) is not None
        )
        server_cap = min(server_values)
        caller_value = getattr(policy.caller_hint, field_name)
        if caller_value is not None and caller_value > server_cap:
            raise CallerBudgetEscalationError(
                f"caller hint raises {field_name} above server-selected cap"
            )
        effective[field_name] = (
            min(server_cap, caller_value) if caller_value is not None else server_cap
        )
    return BudgetProfile(
        **effective,
        model_load=baseline.model_load,
        numeric_default_is_hypothesis=True,
    )


def _runtime_contract_models() -> dict[str, type[Any] | Any]:
    """Return the discriminator registry without creating import cycles."""
    registry: dict[str, type[Any] | Any] = {
        ContractName.QUERY_INTENT.value: QueryIntent,
        ContractName.RETRIEVAL_BUDGET.value: RetrievalBudget,
        ContractName.SEARCH_SCOPE.value: SearchScope,
        ContractName.DOMAIN_MATCH.value: DomainMatch,
        ContractName.RETRIEVAL_STAGE.value: RetrievalStage,
        ContractName.RETRIEVAL_PLAN.value: RetrievalPlan,
        ContractName.NOISE_ASSESSMENT.value: NoiseAssessment,
        ContractName.CONTEXT_ITEM.value: ContextItem,
        ContractName.CONTEXT_PACK.value: ContextPack,
        ContractName.INDEX_WORK_ITEM.value: IndexWorkItem,
        ContractName.INDEX_COST_ESTIMATE.value: IndexCostEstimate,
        ContractName.MEMORY_DISPOSITION.value: MemoryDisposition,
        ContractName.MEMORY_ACTION.value: MemoryActionDecision,
        ContractName.RETENTION_CLASS.value: RetentionClassContract,
        ContractName.SENSITIVITY_CLASS.value: SensitivityClassContract,
        ContractName.PAYLOAD_RETENTION_POLICY.value: PayloadRetentionPolicy,
        ContractName.TOMBSTONE_RECEIPT.value: TombstoneReceipt,
        ContractName.BITEMPORAL_EVIDENCE.value: BitemporalEvidence,
        ContractName.EVIDENCE_ORDERING_POLICY.value: EvidenceOrderingPolicy,
        ContractName.RESOURCE_PROFILE.value: ResourceProfile,
        ContractName.HOST_CAPABILITY_PROFILE.value: HostCapabilityProfile,
        ContractName.RETRIEVAL_BUDGET_POLICY.value: RetrievalBudgetPolicy,
        ContractName.RETRY_POLICY.value: RetryPolicy,
    }
    registry.update(_RUNTIME_CONTRACT_EXTENSIONS)
    return registry


_RUNTIME_CONTRACT_EXTENSIONS: dict[str, type[Any] | Any] = {}


def register_runtime_contract(name: str, model: type[Any]) -> None:
    """Register an optional contract module after its own import completes."""
    if name in _RUNTIME_CONTRACT_EXTENSIONS:
        raise RuntimeError(f"runtime contract already registered: {name}")
    _RUNTIME_CONTRACT_EXTENSIONS[name] = model


class RuntimeContractEnvelope(RuntimeModel):
    """Versioned exact-discriminator envelope for runtime contract payloads."""

    schema_version: Literal["power.context-runtime.v2"]
    contract: ContractName
    payload: Any

    @model_validator(mode="before")
    @classmethod
    def bind_discriminator(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("runtime contract envelope must be an object")
        raw_contract = data.get("contract")
        if not isinstance(raw_contract, str):
            raise ValueError("runtime contract discriminator must be a string")
        try:
            contract = ContractName(raw_contract)
        except (TypeError, ValueError) as exc:
            raise ValueError("unknown runtime contract discriminator") from exc
        registry = _runtime_contract_models()
        expected = registry[contract.value]
        if "payload" not in data:
            raise ValueError("runtime contract envelope requires payload")
        payload = data["payload"]
        parsed: Any
        if isinstance(expected, type) and issubclass(expected, RuntimeModel):
            if expected is MemoryActionDecision and (
                not isinstance(payload, expected)
                or payload._issuer_token is not _POLICY_ENGINE_TOKEN
            ):
                raise ValueError("MemoryAction payload must be issued by the policy engine")
            parsed = payload if isinstance(payload, expected) else expected.model_validate(payload)
        elif isinstance(expected, type) and issubclass(expected, StrEnum):
            if isinstance(payload, expected):
                parsed = payload
            else:
                try:
                    parsed = expected(payload)
                except (TypeError, ValueError) as exc:
                    raise ValueError("payload does not match discriminator") from exc
        else:
            raise TypeError("runtime contract registry contains an invalid payload type")
        copied = dict(data)
        copied["contract"] = contract
        copied["payload"] = parsed
        return copied

    @model_validator(mode="after")
    def verify_discriminator_payload(self) -> Self:
        expected = _runtime_contract_models()[self.contract.value]
        if isinstance(expected, type) and issubclass(expected, RuntimeModel):
            if type(self.payload) is not expected:
                raise ValueError("payload type does not match contract discriminator")
        elif not isinstance(self.payload, expected):
            raise ValueError("payload value does not match contract discriminator")
        return self


# v1 vocabulary compatibility aliases.  The explicit ``Decision`` suffix is
# used by new callers so a policy output cannot be mistaken for an input DTO.
MemoryAction = MemoryActionDecision


__all__ = [
    "AccessPolicy",
    "Authority",
    "AuthorityBasis",
    "BackoffPolicy",
    "BitemporalEvidence",
    "BudgetClass",
    "BudgetLayerSource",
    "BudgetProfile",
    "BudgetProfiles",
    "CallerBudgetEscalationError",
    "ContextBudget",
    "ContextItem",
    "ContextPack",
    "ContractName",
    "ContradictionState",
    "DomainMatch",
    "EvidenceOrderingPolicy",
    "ExcludedItem",
    "Explainability",
    "Freshness",
    "HostCapabilityProfile",
    "IndexCostEstimate",
    "IndexPriority",
    "IndexWorkItem",
    "MemoryAction",
    "MemoryActionDecision",
    "MemoryActionKind",
    "MemoryDisposition",
    "ModelLoadPolicy",
    "NoiseAssessment",
    "NoiseDisposition",
    "PayloadRetentionPolicy",
    "ProfileBudgetLayer",
    "Provenance",
    "QueryIntent",
    "QueryIntentKind",
    "QueueState",
    "ResourceProfile",
    "ResourceProfileClass",
    "RetentionClass",
    "RetentionClassContract",
    "RetrievalBudget",
    "RetrievalBudgetPolicy",
    "RetrievalPlan",
    "RetrievalStage",
    "RetryPolicy",
    "RuntimeContractEnvelope",
    "RuntimeModel",
    "SearchScope",
    "SensitivityClass",
    "SensitivityClassContract",
    "TemporalBoundary",
    "TombstoneReceipt",
    "TrustState",
    "canonical_bytes",
    "canonical_sha256",
    "register_runtime_contract",
    "resolve_budget_caps",
    "validate_trust_authority",
]
