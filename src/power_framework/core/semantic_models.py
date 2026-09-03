"""Pydantic v2 Models for POWER Project State Engine (PSE) Phase 3 Semantic Entities.

Defines schemas and invariants for:
- Provenance (mandatory epistemic and audit trail)
- 9 Semantic Entity Types: Fact, DecisionReference, Assumption, Hypothesis, Risk, Issue, Dependency, Observation, Lesson
- VerificationStatus (proposed, verified, rejected, superseded, invalidated)
- SemanticEntityCandidate & ContradictionProposal
Conforms strictly to artifacts/project-state/phase-1/semantic-entity-schema-v1.json
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from power_framework.core.project_models import PROJECT_ID_REGEX, validate_project_id

EVENT_ID_REGEX = r"^evt_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
_EVENT_ID_COMPILED = re.compile(EVENT_ID_REGEX)

# Entity ID regex patterns matching semantic-entity-schema-v1.json
FACT_ID_REGEX = r"^fct_[A-Za-z0-9._-]{2,64}$"
DECISION_REF_ID_REGEX = r"^dref_[A-Za-z0-9._-]{2,64}$"
ASSUMPTION_ID_REGEX = r"^asm_[A-Za-z0-9._-]{2,64}$"
HYPOTHESIS_ID_REGEX = r"^hyp_[A-Za-z0-9._-]{2,64}$"
RISK_ID_REGEX = r"^rsk_[A-Za-z0-9._-]{2,64}$"
ISSUE_ID_REGEX = r"^iss_[A-Za-z0-9._-]{2,64}$"
DEPENDENCY_ID_REGEX = r"^dep_[A-Za-z0-9._-]{2,64}$"
OBSERVATION_ID_REGEX = r"^obs_[A-Za-z0-9._-]{2,64}$"
LESSON_ID_REGEX = r"^lsn_[A-Za-z0-9._-]{2,64}$"

_FACT_ID_COMPILED = re.compile(FACT_ID_REGEX)
_DECISION_REF_ID_COMPILED = re.compile(DECISION_REF_ID_REGEX)
_ASSUMPTION_ID_COMPILED = re.compile(ASSUMPTION_ID_REGEX)
_HYPOTHESIS_ID_COMPILED = re.compile(HYPOTHESIS_ID_REGEX)
_RISK_ID_COMPILED = re.compile(RISK_ID_REGEX)
_ISSUE_ID_COMPILED = re.compile(ISSUE_ID_REGEX)
_DEPENDENCY_ID_COMPILED = re.compile(DEPENDENCY_ID_REGEX)
_OBSERVATION_ID_COMPILED = re.compile(OBSERVATION_ID_REGEX)
_LESSON_ID_COMPILED = re.compile(LESSON_ID_REGEX)


class VerificationStatus(StrEnum):
    """Lifecycle and verification statuses for semantic entity candidates and proposals."""

    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"


class SemanticEntityType(StrEnum):
    """The 9 required semantic entity types defined in Phase 1 & Phase 3 specifications."""

    FACT = "FACT"
    DECISION = "DECISION"
    ASSUMPTION = "ASSUMPTION"
    HYPOTHESIS = "HYPOTHESIS"
    RISK = "RISK"
    ISSUE = "ISSUE"
    DEPENDENCY = "DEPENDENCY"
    OBSERVATION = "OBSERVATION"
    LESSON = "LESSON"


class ContradictionKind(StrEnum):
    """Five-class contradiction/supersession taxonomy required by Phase 3 specification."""

    CONFLICTING_OBSERVATION = "conflicting_observation"
    EXPLICIT_CORRECTION = "explicit_correction"
    SUPERSEDING_DECISION = "superseding_decision"
    STALE_FACT = "stale_fact"
    UNRESOLVED_CONTRADICTION = "unresolved_contradiction"


class Provenance(BaseModel):
    """Mandatory audit and origin metadata for semantic entities."""

    model_config = ConfigDict(extra="forbid")

    source_event_ids: list[str] = Field(..., min_length=1)
    primary_source_event_id: str | None = Field(default=None, pattern=EVENT_ID_REGEX)
    actor: str = Field(..., min_length=1, max_length=128)
    timestamp: str = Field(...)
    source_type: Literal[
        "event_replay",
        "direct_mutation",
        "reconciliation",
        "agent_inference",
        "human_entry",
        "automated_test",
    ]
    correlation_id: str | None = Field(default=None, max_length=128)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    verification_status: Literal["unverified", "verified", "refuted", "quarantined"] | None = Field(
        default=None
    )
    valid_from: str | None = Field(default=None)
    valid_to: str | None = Field(default=None)
    supersedes: str | None = Field(default=None, max_length=128)
    invalidates: str | None = Field(default=None, max_length=128)

    @field_validator("source_event_ids")
    @classmethod
    def validate_source_events(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("source_event_ids must contain at least 1 event ID")
        seen: set[str] = set()
        deduped: list[str] = []
        for eid in v:
            if not _EVENT_ID_COMPILED.match(eid):
                raise ValueError(f"Invalid event ID in source_event_ids: {eid}")
            if eid not in seen:
                seen.add(eid)
                deduped.append(eid)
            else:
                raise ValueError(f"Duplicate event ID in source_event_ids: {eid}")
        return deduped

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, v: list[str]) -> list[str]:
        for ref in v:
            if len(ref) > 512:
                raise ValueError(f"evidence_ref exceeds max length 512: {ref[:32]}...")
        return v


class Fact(BaseModel):
    """Verified domain fact or empirical finding associated with a project."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., pattern=FACT_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    statement: str = Field(..., min_length=1, max_length=2048)
    category: Literal["domain", "technical", "organizational", "environmental", "historical"] = (
        Field(default="technical")
    )
    verified_at: str | None = Field(default=None)
    verification_method: str | None = Field(default=None, max_length=256)
    provenance: Provenance
    created_at: str = Field(...)
    updated_at: str | None = Field(default=None)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class DecisionReference(BaseModel):
    """Referential projection linking a canonical Decision into project state."""

    model_config = ConfigDict(extra="forbid")

    decision_ref_id: str = Field(..., pattern=DECISION_REF_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    decision_id: str = Field(..., min_length=2, max_length=128)
    relation: str = Field(default="governs", min_length=1, max_length=128)
    status: Literal["proposed", "pending", "accepted", "rejected", "superseded"] = Field(...)
    task_id: str | None = Field(default=None, max_length=128)
    receipt_ref: str | None = Field(default=None, max_length=256)
    provenance: Provenance
    created_at: str = Field(...)
    updated_at: str | None = Field(default=None)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Assumption(BaseModel):
    """Assumption entity in RAID log."""

    model_config = ConfigDict(extra="forbid")

    assumption_id: str = Field(..., pattern=ASSUMPTION_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    statement: str = Field(..., min_length=1, max_length=1024)
    rationale: str = Field(default="", max_length=4096)
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: Literal["valid", "invalidated", "confirmed"] = Field(...)
    validated_at: str | None = Field(default=None)
    invalidated_by: str | None = Field(default=None, max_length=128)
    provenance: Provenance
    created_at: str = Field(...)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Hypothesis(BaseModel):
    """Testable hypothesis or proposition requiring empirical validation."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(..., pattern=HYPOTHESIS_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    statement: str = Field(..., min_length=1, max_length=2048)
    rationale: str = Field(default="", max_length=4096)
    validation_criteria: str = Field(default="", max_length=2048)
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: Literal["proposed", "testing", "validated", "refuted", "abandoned"] = Field(...)
    provenance: Provenance
    created_at: str = Field(...)
    updated_at: str | None = Field(default=None)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Risk(BaseModel):
    """Risk entity in RAID log."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str = Field(..., pattern=RISK_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    probability: Literal["low", "medium", "high"] = Field(...)
    impact: Literal["low", "medium", "high", "critical"] = Field(...)
    mitigation_plan: str = Field(default="", max_length=4096)
    owner: str = Field(..., min_length=1, max_length=128)
    status: Literal["identified", "mitigated", "materialized", "retired"] = Field(...)
    related_task_ids: list[str] = Field(default_factory=list)
    provenance: Provenance
    created_at: str = Field(...)
    updated_at: str = Field(...)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Issue(BaseModel):
    """Issue entity in RAID log."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(..., pattern=ISSUE_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    severity: Literal["minor", "major", "critical", "blocker"] = Field(...)
    status: Literal["open", "investigating", "resolved", "closed"] = Field(...)
    blocking_task_ids: list[str] = Field(default_factory=list)
    resolution: str | None = Field(default=None, max_length=4096)
    provenance: Provenance
    created_at: str = Field(...)
    resolved_at: str | None = Field(default=None)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Dependency(BaseModel):
    """Typed cross-entity dependency in RAID log."""

    model_config = ConfigDict(extra="forbid")

    dependency_id: str = Field(..., pattern=DEPENDENCY_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    source_id: str = Field(..., min_length=1, max_length=128)
    target_id: str = Field(..., min_length=1, max_length=128)
    target_type: Literal["task", "decision", "artifact", "project", "external"] = Field(...)
    dependency_kind: Literal["blocks", "blocked_by", "relates_to", "requires"] = Field(...)
    status: Literal["pending", "satisfied", "broken"] = Field(...)
    external_ref: str | None = Field(default=None, max_length=512)
    provenance: Provenance
    created_at: str = Field(...)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Observation(BaseModel):
    """Direct observation recorded by an agent, sensor, or human."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(..., pattern=OBSERVATION_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    content: str = Field(..., min_length=1, max_length=4096)
    context: str = Field(default="", max_length=2048)
    observer: str = Field(default="", max_length=128)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_at: str = Field(...)
    provenance: Provenance
    created_at: str = Field(...)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


class Lesson(BaseModel):
    """Structured lesson learned, retrospective takeaway, or process optimization insight."""

    model_config = ConfigDict(extra="forbid")

    lesson_id: str = Field(..., pattern=LESSON_ID_REGEX)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    title: str = Field(..., min_length=1, max_length=256)
    summary: str = Field(..., min_length=1, max_length=4096)
    category: Literal[
        "process", "technical", "architecture", "coordination", "quality", "security"
    ] = Field(...)
    applies_to: list[str] = Field(default_factory=list)
    recommendation: str = Field(..., min_length=1, max_length=4096)
    provenance: Provenance
    created_at: str = Field(...)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)


# Type alias for any validated semantic entity model
SemanticEntity = (
    Fact
    | DecisionReference
    | Assumption
    | Hypothesis
    | Risk
    | Issue
    | Dependency
    | Observation
    | Lesson
)


ENTITY_TYPE_TO_MODEL: dict[SemanticEntityType, type[SemanticEntity]] = {
    SemanticEntityType.FACT: Fact,
    SemanticEntityType.DECISION: DecisionReference,
    SemanticEntityType.ASSUMPTION: Assumption,
    SemanticEntityType.HYPOTHESIS: Hypothesis,
    SemanticEntityType.RISK: Risk,
    SemanticEntityType.ISSUE: Issue,
    SemanticEntityType.DEPENDENCY: Dependency,
    SemanticEntityType.OBSERVATION: Observation,
    SemanticEntityType.LESSON: Lesson,
}

ENTITY_TYPE_PREFIX: dict[SemanticEntityType, str] = {
    SemanticEntityType.FACT: "fct",
    SemanticEntityType.DECISION: "dref",
    SemanticEntityType.ASSUMPTION: "asm",
    SemanticEntityType.HYPOTHESIS: "hyp",
    SemanticEntityType.RISK: "rsk",
    SemanticEntityType.ISSUE: "iss",
    SemanticEntityType.DEPENDENCY: "dep",
    SemanticEntityType.OBSERVATION: "obs",
    SemanticEntityType.LESSON: "lsn",
}


def generate_deterministic_entity_id(
    project_id: str,
    entity_type: SemanticEntityType,
    core_content: str,
) -> str:
    """Generate a deterministic stable entity ID from project_id, entity_type, and core content.

    Ensures idempotent recompilation and deduplication (G3.4).
    """
    prefix = ENTITY_TYPE_PREFIX[entity_type]
    normalized_content = core_content.strip().lower()
    digest = hashlib.sha256(
        f"{project_id}:{entity_type.value}:{normalized_content}".encode()
    ).hexdigest()[:16]
    return f"{prefix}_{digest}"


class ContradictionProposal(BaseModel):
    """Proposal linking two contradicting, superseding, or invalidating entities.

    In accordance with G3.5, the old record is NEVER deleted; history is preserved.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(...)
    kind: ContradictionKind
    subject_entity_id: str = Field(...)
    conflicting_entity_id: str = Field(...)
    proposed_action: Literal["supersede", "invalidate", "flag_contradiction", "review_required"]
    rationale: str = Field(..., min_length=1, max_length=4096)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: str = Field(...)


class SemanticEntityCandidate(BaseModel):
    """Typed candidate entity generated by the Semantic Compiler pipeline.

    Carries the fully validated domain entity dictionary, verification status,
    provenance, extraction source, and optional text offset.
    """

    model_config = ConfigDict(extra="forbid")

    entity_type: SemanticEntityType
    entity_id: str = Field(...)
    entity: dict[str, Any] = Field(...)
    verification_status: VerificationStatus = Field(default=VerificationStatus.PROPOSED)
    source: Literal["structured_event", "model_extraction"]
    location_offset: tuple[int, int] | None = Field(default=None)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_model_extraction_invariants(self) -> SemanticEntityCandidate:
        """Enforce Gate G3.2: Model-extracted candidates CANNOT bypass verification policy.

        They are unconditionally assigned status 'proposed' and their underlying
        provenance is forced to 'unverified'.
        """
        if self.source == "model_extraction":
            if self.verification_status == VerificationStatus.VERIFIED:
                self.verification_status = VerificationStatus.PROPOSED
            if isinstance(self.entity, dict) and "provenance" in self.entity:
                prov = self.entity["provenance"]
                if isinstance(prov, dict):
                    if prov.get("verification_status") == "verified":
                        prov["verification_status"] = "unverified"
                    if prov.get("source_type") != "agent_inference":
                        prov["source_type"] = "agent_inference"
        return self
