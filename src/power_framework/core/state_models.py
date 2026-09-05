"""Pydantic v2 Models for POWER Project State Engine (PSE) Phase 4.

Defines schemas, invariants, and deterministic structures for:
- ProjectPhase and legal FSM taxonomy
- ProjectState v1 (strict canonical state projection)
- TaskAuthorityView and DecisionAuthorityView (Option A / Hybrid authority adapters)
- PhaseTransitionRecord (audit trail for phase advancements and rollbacks)
- TaskReadinessEvaluation and reason codes
- DoREvaluation and DoDEvaluation (quality gate contracts)
- GovernanceEvaluation (ALLOW, DENY, REQUIRE_APPROVAL, REQUIRE_EVIDENCE)
- StateExplanation (deterministic evidence trace)
- ProjectStateSnapshot (verified accelerator)
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from power_framework.core.canonical_json import (
    canonical_json_bytes,
    canonical_json_dumps,
)
from power_framework.core.decision_models import (
    CANONICAL_DECISION_STATUSES,
    RESOLVED_DECISION_STATUSES,
    DecisionStatus,
)
from power_framework.core.project_models import (
    EVENT_ID_REGEX,
    HASH_REGEX,
    PREV_HASH_REGEX,
    PROJECT_ID_REGEX,
    validate_event_id,
    validate_project_id,
)
from power_framework.core.semantic_models import (  # noqa: TC001
    Assumption,
    Dependency,
    Issue,
    Risk,
)

if TYPE_CHECKING:
    from power_framework.core.decision_models import Decision
    from power_framework.core.task_models import PowerTask

STATE_SCHEMA_VERSION: Literal["power.project-state.v1"] = "power.project-state.v1"
GOVERNANCE_RULES_VERSION: str = "1.0.0"


class IllegalStateTransitionError(ValueError):
    """Raised when an illegal or unverified lifecycle transition is attempted."""


class StateEngineIntegrityError(ValueError):
    """Raised when state engine inputs, event ordering, or hash chains fail verification."""


class SnapshotIntegrityError(ValueError):
    """Raised when a state snapshot is tampered, forged, or fails lineage verification."""


class UnexplainableFieldError(KeyError):
    """Raised when explanation is requested for an unknown or unsupported state field."""


class ProjectPhase(StrEnum):
    """Canonical 6-state project lifecycle defined in Phase 1 & ADR-PSE-003."""

    DISCOVERY = "DISCOVERY"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    MONITORING = "MONITORING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class TaskReadinessStatus(StrEnum):
    """Deterministic task readiness status codes."""

    READY = "READY"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    BLOCKED_DOR = "BLOCKED_DOR"
    REQUIRES_EVIDENCE = "REQUIRES_EVIDENCE"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    TERMINAL = "TERMINAL"
    IN_PROGRESS = "IN_PROGRESS"


class GovernanceDecision(StrEnum):
    """Four-class governance policy outcomes required by Phase 4 specification."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"


class HealthFlag(StrEnum):
    """Deterministic health indicator flags."""

    BLOCKING_ISSUES_PRESENT = "BLOCKING_ISSUES_PRESENT"
    HIGH_RISKS_OPEN = "HIGH_RISKS_OPEN"
    CIRCULAR_DEPENDENCY_DETECTED = "CIRCULAR_DEPENDENCY_DETECTED"
    BLOCKED_TASKS_PRESENT = "BLOCKED_TASKS_PRESENT"
    UNRESOLVED_GOVERNANCE_REQUIREMENTS = "UNRESOLVED_GOVERNANCE_REQUIREMENTS"
    INVALID_TRANSITION_ATTEMPTED = "INVALID_TRANSITION_ATTEMPTED"
    STALE_AUTHORITATIVE_PROJECTION = "STALE_AUTHORITATIVE_PROJECTION"
    STALE_TASK_OBSERVATION = "STALE_TASK_OBSERVATION"
    TASK_AUTHORITY_DRIFT = "TASK_AUTHORITY_DRIFT"
    STALE_DECISION_OBSERVATION = "STALE_DECISION_OBSERVATION"
    DECISION_AUTHORITY_DRIFT = "DECISION_AUTHORITY_DRIFT"


class PhaseTransitionRecord(BaseModel):
    """Immutable audit record for one project lifecycle phase transition."""

    model_config = ConfigDict(extra="forbid")

    from_phase: ProjectPhase
    to_phase: ProjectPhase
    name: str = Field(..., min_length=1, max_length=128)
    timestamp: str = Field(...)
    actor: str = Field(..., min_length=1, max_length=128)
    event_id: str = Field(..., pattern=EVENT_ID_REGEX)
    is_rollback: bool = Field(default=False)
    reason: str | None = Field(default=None, max_length=4096)
    gate: str | None = Field(default=None, max_length=128)
    evidence_refs: list[str] = Field(default_factory=list)
    approval_refs: list[str] = Field(default_factory=list)

    @field_validator("event_id")
    @classmethod
    def check_event_id(cls, v: str) -> str:
        return validate_event_id(v)


class TaskAuthorityView(BaseModel):
    """Immutable, versioned projection of canonical Task v2 state.

    Binds TaskStore authority into the deterministic State Engine without
    duplicating or replacing Task v2 lifecycle truth (ADR-PSE-004 & Gate G4.3).

    Canonical authority is established by independent resolution against the
    owning authoritative subsystem (TaskStore/TaskService). Digests/receipts
    record or protect the result; they are not bearer credentials. A
    caller-constructed view — even with a matching self-digest and
    source_identity="TaskStore:v2" — proves only internal view integrity,
    never TaskStore authority.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., min_length=1, max_length=128)
    state: str = Field(..., min_length=1, max_length=64)
    revision: int = Field(default=1, ge=1)
    digest: str = Field(..., pattern=HASH_REGEX)
    source_identity: str = Field(default="TaskStore:v2", min_length=1, max_length=128)
    dependencies: list[str] = Field(default_factory=list)
    open_gates: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)

    @classmethod
    def compute_digest(
        cls,
        task_id: str,
        state: str,
        revision: int,
        dependencies: list[str] | None = None,
        open_gates: list[str] | None = None,
        receipt_ids: list[str] | None = None,
    ) -> str:
        payload = {
            "dependencies": sorted(dependencies or []),
            "open_gates": sorted(open_gates or []),
            "receipt_ids": sorted(receipt_ids or []),
            "revision": revision,
            "state": state,
            "task_id": task_id,
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @classmethod
    def from_power_task(
        cls,
        task: PowerTask,
        source_identity: str = "TaskStore:v2",
    ) -> TaskAuthorityView:
        digest = cls.compute_digest(
            task_id=task.task_id,
            state=task.state,
            revision=task.revision,
            dependencies=list(task.dependencies),
            open_gates=list(task.open_gates),
            receipt_ids=list(task.receipt_ids),
        )
        return cls(
            task_id=task.task_id,
            state=task.state,
            revision=task.revision,
            digest=digest,
            source_identity=source_identity,
            dependencies=sorted(task.dependencies),
            open_gates=sorted(task.open_gates),
            receipt_ids=sorted(task.receipt_ids),
        )


class DecisionAuthorityView(BaseModel):
    """Immutable, versioned projection of canonical typed Decision state.

    Binds DecisionService authority into the deterministic State Engine
    without duplicating or bypassing approval workflows (ADR-PSE-004 & Gate G4.4).

    Canonical authority is established by independent resolution against the
    owning authoritative subsystem (DecisionService). Digests/receipts record
    or protect the result; they are not bearer credentials. A caller-constructed
    view — even with a matching self-digest and
    source_identity="DecisionService:v1" — proves only internal view integrity,
    never DecisionService approval authority.
    """

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(..., min_length=1, max_length=128)
    status: DecisionStatus
    task_id: str | None = Field(default=None, max_length=128)
    task_revision: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    digest: str = Field(..., pattern=HASH_REGEX)
    source_identity: str = Field(default="DecisionService:v1", min_length=1, max_length=128)
    receipt_id: str | None = Field(default=None, max_length=128)

    @classmethod
    def compute_digest(
        cls,
        decision_id: str,
        status: DecisionStatus,
        task_id: str | None = None,
        task_revision: int = 1,
        revision: int = 1,
        receipt_id: str | None = None,
    ) -> str:
        payload = {
            "decision_id": decision_id,
            "receipt_id": receipt_id or "",
            "revision": revision,
            "status": status,
            "task_id": task_id or "",
            "task_revision": task_revision,
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @classmethod
    def from_decision(
        cls,
        decision: Decision,
        source_identity: str = "DecisionService:v1",
    ) -> DecisionAuthorityView:
        digest = cls.compute_digest(
            decision_id=decision.decision_id,
            status=decision.status,
            task_id=decision.task_id,
            task_revision=decision.task_revision,
            revision=1,
            receipt_id=decision.receipt_id,
        )
        return cls(
            decision_id=decision.decision_id,
            status=decision.status,
            task_id=decision.task_id,
            task_revision=decision.task_revision,
            revision=1,
            digest=digest,
            source_identity=source_identity,
            receipt_id=decision.receipt_id,
        )


class HistoricalGovernanceEvaluation(BaseModel):
    """Immutable authority proof bound to one canonical PSE event sequence.

    The event carrying this record is the historical source for DoR/DoD and
    approval/completion decisions.  Current TaskStore/DecisionService state is
    deliberately not represented here: it is applied only as a post-replay
    federation overlay by ``ProjectStateService``.
    """

    model_config = ConfigDict(extra="forbid")

    evaluation_type: Literal["dor", "dod"]
    result: Literal["passed", "failed"]
    evaluated_from_phase: ProjectPhase
    evaluated_phase: ProjectPhase
    evaluation_event_id: str = Field(..., pattern=EVENT_ID_REGEX)
    task_views: list[TaskAuthorityView] = Field(default_factory=list)
    decision_views: list[DecisionAuthorityView] = Field(default_factory=list)
    approved_decision_ids: list[str] = Field(default_factory=list)
    verified_task_receipts: list[str] = Field(default_factory=list)
    required_evidence_refs: list[str] = Field(default_factory=list)
    accountable_actor: str | None = Field(default=None, max_length=128)
    rules_version: str = Field(default=GOVERNANCE_RULES_VERSION, min_length=1, max_length=64)
    rules_digest: str = Field(..., pattern=HASH_REGEX)

    @model_validator(mode="after")
    def validate_bindings(self) -> HistoricalGovernanceEvaluation:
        task_ids = {view.task_id for view in self.task_views}
        decision_ids = {view.decision_id for view in self.decision_views}
        if any(view.status not in CANONICAL_DECISION_STATUSES for view in self.decision_views):
            raise ValueError("historical decision evaluation contains an unknown decision status")
        if not set(self.approved_decision_ids).issubset(decision_ids):
            raise ValueError("approved_decision_ids must reference included decision views")
        if any(
            view.status not in RESOLVED_DECISION_STATUSES or view.status != "approved"
            for view in self.decision_views
            if view.decision_id in self.approved_decision_ids
        ):
            raise ValueError("approved_decision_ids must reference approved decision views")
        receipt_ids = {receipt_id for view in self.task_views for receipt_id in view.receipt_ids}
        if not set(self.verified_task_receipts).issubset(receipt_ids):
            raise ValueError("verified_task_receipts must reference included task views")
        if len(task_ids) != len(self.task_views):
            raise ValueError("historical task evaluation contains duplicate task IDs")
        if len(decision_ids) != len(self.decision_views):
            raise ValueError("historical decision evaluation contains duplicate decision IDs")
        return self


class TaskReadinessEvaluation(BaseModel):
    """Deterministic evaluation of one task's readiness to be executed."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., min_length=1, max_length=128)
    status: TaskReadinessStatus
    reason_codes: list[str] = Field(default_factory=list)
    blocking_dependencies: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    missing_approvals: list[str] = Field(default_factory=list)
    cycle_path: list[str] = Field(default_factory=list)


class DoREvaluation(BaseModel):
    """Deterministic Definition-of-Ready evaluation for phase transitions or tasks."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    reason_codes: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    missing_approvals: list[str] = Field(default_factory=list)
    blocking_dependencies: list[str] = Field(default_factory=list)
    failed_preconditions: list[str] = Field(default_factory=list)


class DoDEvaluation(BaseModel):
    """Deterministic Definition-of-Done evaluation before project closing."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    reason_codes: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    missing_approvals: list[str] = Field(default_factory=list)
    failed_conditions: list[str] = Field(default_factory=list)


class GovernanceEvaluation(BaseModel):
    """Deterministic evaluation outcome from the Governance Policy Engine."""

    model_config = ConfigDict(extra="forbid")

    decision: GovernanceDecision
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str = Field(default=GOVERNANCE_RULES_VERSION)
    relevant_event_ids: list[str] = Field(default_factory=list)
    relevant_entity_ids: list[str] = Field(default_factory=list)
    required_approval_ids: list[str] = Field(default_factory=list)
    required_evidence_refs: list[str] = Field(default_factory=list)


class StateExplanation(BaseModel):
    """Deterministic provenance and evidence trace explaining one state field."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    field: str = Field(..., min_length=1, max_length=128)
    state_revision: str = Field(..., pattern=HASH_REGEX)
    value: Any = Field(...)
    contributing_event_ids: list[str] = Field(default_factory=list)
    applicable_rules: list[str] = Field(default_factory=list)
    decision_references: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    authority_references: list[str] = Field(default_factory=list)


def compute_state_revision(state_dict: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 state revision over normalized state content.

    Excludes the 'state_revision' field itself to guarantee mathematical determinism.
    """
    cleaned = {k: v for k, v in state_dict.items() if k != "state_revision"}
    return hashlib.sha256(canonical_json_bytes(cleaned)).hexdigest()


class ProjectState(BaseModel):
    """Authoritative, deterministic state projection of a POWER project.

    Strictly validated: extra='forbid'.
    All list projections are deterministically sorted to ensure byte-equivalent
    canonical JSON across independent Python processes and replays.
    """

    model_config = ConfigDict(extra="forbid")

    # Authoritative outputs required by Phase 4 Specification
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX, max_length=68)
    current_phase: ProjectPhase = ProjectPhase.DISCOVERY
    owner: str | None = Field(default=None, max_length=128)
    phase_history: list[PhaseTransitionRecord] = Field(default_factory=list)
    active_tasks: list[str] = Field(default_factory=list)
    ready_tasks: list[str] = Field(default_factory=list)
    blocked_tasks: list[str] = Field(default_factory=list)
    open_risks: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    active_assumptions: list[str] = Field(default_factory=list)
    active_dependencies: list[str] = Field(default_factory=list)
    valid_decisions: list[str] = Field(default_factory=list)
    superseded_decisions: list[str] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)
    health_flags: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    state_revision: str = Field(..., pattern=HASH_REGEX)

    # Lineage and metadata bound into the state revision
    schema_version: Literal["power.project-state.v1"] = STATE_SCHEMA_VERSION
    rules_version: str = Field(default=GOVERNANCE_RULES_VERSION)
    rules_digest: str = Field(default="", pattern=r"^([0-9a-f]{64})?$")
    last_event_sequence: int = Field(default=0, ge=0)
    last_event_hash: str = Field(default="", pattern=PREV_HASH_REGEX)

    # Canonical governance projections (PSE-owned deterministic index)
    # raci maps canonical role -> sorted actor list, built only from
    # canonical raci.assigned / raci.revoked ledger events. Caller payload
    # role strings never populate this projection.
    raci: dict[str, list[str]] = Field(default_factory=dict)
    # Canonical evidence semantics are explicit; an identifier containing the
    # word "charter" is never sufficient by itself.
    evidence_kinds: dict[str, str] = Field(default_factory=dict)
    # attached_evidence is the deterministic sorted index of canonical
    # evidence refs attached via evidence.attached / artifact.created events
    # (plus verified raw-evidence sha256: refs). Transition evidence_refs
    # must resolve against this index; non-empty strings alone never satisfy
    # a quality gate.
    attached_evidence: list[str] = Field(default_factory=list)

    # Internal typed entity maps
    tasks: dict[str, TaskAuthorityView] = Field(default_factory=dict)
    decisions: dict[str, DecisionAuthorityView] = Field(default_factory=dict)
    # Historical authority is sequence-bound and cannot be replaced by the
    # current federated overlay.
    historical_approved_decisions: dict[str, int] = Field(default_factory=dict)
    historical_task_receipts: dict[str, int] = Field(default_factory=dict)
    historical_evaluations: list[str] = Field(default_factory=list)
    historical_gate_evaluations: dict[str, int] = Field(default_factory=dict)
    historical_gate_origins: dict[str, str] = Field(default_factory=dict)
    risks: dict[str, Risk] = Field(default_factory=dict)
    issues: dict[str, Issue] = Field(default_factory=dict)
    assumptions: dict[str, Assumption] = Field(default_factory=dict)
    dependencies: dict[str, Dependency] = Field(default_factory=dict)
    overridden_gates: list[str] = Field(default_factory=list)
    contributing_events: list[str] = Field(default_factory=list)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)

    def to_canonical_dict(self) -> dict[str, Any]:
        """Convert state to a canonical JSON serializable dictionary."""
        return self.model_dump(mode="json")

    def to_canonical_json(self) -> str:
        """Serialize state to POWER Canonical JSON v1 deterministic string."""
        return canonical_json_dumps(self.to_canonical_dict())

    def to_canonical_bytes(self) -> bytes:
        """Serialize state to POWER Canonical JSON v1 deterministic UTF-8 bytes."""
        return canonical_json_bytes(self.to_canonical_dict())


def compute_snapshot_digest(snapshot_dict: dict[str, Any]) -> str:
    """Compute SHA-256 digest of snapshot payload excluding snapshot_digest field."""
    cleaned = {k: v for k, v in snapshot_dict.items() if k != "snapshot_digest"}
    return hashlib.sha256(canonical_json_bytes(cleaned)).hexdigest()


class ProjectStateSnapshot(BaseModel):
    """Cryptographically sealed snapshot of verified ProjectState.

    Snapshots serve purely as accelerators; they never replace canonical ledger authority.
    Any tampering or hash mismatch causes immediate rejection (Gate G4.1 & Section 22).

    Integrity != authority: verify_integrity() proves only internal
    self-consistency (matching digests/revisions). Authoritative restore must
    additionally verify snapshot.project_id, snapshot.last_event_sequence and
    snapshot.last_event_hash against a trusted re-read of the real canonical
    Phase-2 ledger, and must re-resolve federated TaskStore/DecisionService
    authority (see ProjectStateService.restore_snapshot_authoritative).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["power.project-state.v1"] = STATE_SCHEMA_VERSION
    rules_version: str = Field(default=GOVERNANCE_RULES_VERSION)
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    last_event_sequence: int = Field(..., ge=0)
    last_event_hash: str = Field(..., pattern=PREV_HASH_REGEX)
    state_revision: str = Field(..., pattern=HASH_REGEX)
    state: ProjectState
    snapshot_digest: str = Field(..., pattern=HASH_REGEX)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return validate_project_id(v)

    @classmethod
    def create(cls, state: ProjectState) -> ProjectStateSnapshot:
        """Create a cryptographically verified snapshot from current state."""
        state_dict = state.to_canonical_dict()
        if compute_state_revision(state_dict) != state.state_revision:
            raise SnapshotIntegrityError(
                "state_revision does not match state content; refusing to seal snapshot"
            )
        raw_dict = {
            "schema_version": STATE_SCHEMA_VERSION,
            "rules_version": state.rules_version,
            "project_id": state.project_id,
            "last_event_sequence": state.last_event_sequence,
            "last_event_hash": state.last_event_hash,
            "state_revision": state.state_revision,
            "state": state_dict,
        }
        digest = compute_snapshot_digest(raw_dict)
        return cls(
            schema_version=STATE_SCHEMA_VERSION,
            rules_version=state.rules_version,
            project_id=state.project_id,
            last_event_sequence=state.last_event_sequence,
            last_event_hash=state.last_event_hash,
            state_revision=state.state_revision,
            state=state,
            snapshot_digest=digest,
        )

    def verify_integrity(self) -> bool:
        """Verify internal consistency and cryptographic seal of this snapshot."""
        if self.project_id != self.state.project_id:
            return False
        if self.last_event_sequence != self.state.last_event_sequence:
            return False
        if self.last_event_hash != self.state.last_event_hash:
            return False
        if self.state_revision != self.state.state_revision:
            return False

        computed_state_rev = compute_state_revision(self.state.to_canonical_dict())
        if computed_state_rev != self.state_revision:
            return False

        computed_snap_digest = compute_snapshot_digest(self.model_dump(mode="json"))
        return computed_snap_digest == self.snapshot_digest


__all__ = [
    "GOVERNANCE_RULES_VERSION",
    "STATE_SCHEMA_VERSION",
    "DecisionAuthorityView",
    "DoDEvaluation",
    "DoREvaluation",
    "GovernanceDecision",
    "GovernanceEvaluation",
    "HealthFlag",
    "HistoricalGovernanceEvaluation",
    "IllegalStateTransitionError",
    "PhaseTransitionRecord",
    "ProjectPhase",
    "ProjectState",
    "ProjectStateSnapshot",
    "SnapshotIntegrityError",
    "StateEngineIntegrityError",
    "StateExplanation",
    "TaskAuthorityView",
    "TaskReadinessEvaluation",
    "TaskReadinessStatus",
    "UnexplainableFieldError",
    "compute_snapshot_digest",
    "compute_state_revision",
]
