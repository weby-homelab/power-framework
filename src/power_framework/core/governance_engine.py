"""POWER Project State Engine (PSE) Phase 4 — Governance & Policy Engine.

Implements deterministic evaluation of:
- Project lifecycle FSM transition matrix (17 legal transitions from lifecycle-v1.json)
- Gate enforcement (DoR / DoD) and authorized overrides
- Task readiness and dependency cycle detection
- Preconditions, evidence requirements, and approval requirements
- Health flags and advisory memory governance
- Strict fail-closed trust boundaries against unverified / model-extracted proposals
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from power_framework.core.canonical_json import canonical_json_bytes
from power_framework.core.state_models import (
    GOVERNANCE_RULES_VERSION,
    DoDEvaluation,
    DoREvaluation,
    GovernanceDecision,
    GovernanceEvaluation,
    HealthFlag,
    ProjectPhase,
    TaskReadinessEvaluation,
    TaskReadinessStatus,
)
from power_framework.core.task_models import TERMINAL_STATES

if TYPE_CHECKING:
    from power_framework.core.project_models import ProjectEvent
    from power_framework.core.state_models import ProjectState, TaskAuthorityView


@dataclass(frozen=True)
class TransitionSpec:
    """Specification of one legal directed lifecycle transition."""

    from_phase: ProjectPhase
    to_phase: ProjectPhase
    name: str
    preconditions: tuple[str, ...]
    required_gate: str | None
    approval_required: bool
    evidence_required: bool
    is_rollback: bool


# Exactly 17 legal transitions defined in lifecycle-v1.json & ADR-PSE-003
LEGAL_TRANSITIONS: dict[tuple[ProjectPhase, ProjectPhase], TransitionSpec] = {
    (ProjectPhase.DISCOVERY, ProjectPhase.PLANNING): TransitionSpec(
        from_phase=ProjectPhase.DISCOVERY,
        to_phase=ProjectPhase.PLANNING,
        name="advance_to_planning",
        preconditions=("charter_present", "owner_assigned"),
        required_gate="dor_discovery_to_planning",
        approval_required=False,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.DISCOVERY, ProjectPhase.CLOSED): TransitionSpec(
        from_phase=ProjectPhase.DISCOVERY,
        to_phase=ProjectPhase.CLOSED,
        name="cancel_during_discovery",
        preconditions=("cancellation_reason_provided",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.PLANNING, ProjectPhase.EXECUTION): TransitionSpec(
        from_phase=ProjectPhase.PLANNING,
        to_phase=ProjectPhase.EXECUTION,
        name="start_execution",
        preconditions=(
            "dor_passed_or_overridden",
            "raci_accountable_assigned",
            "initial_tasks_registered",
        ),
        required_gate="dor_planning_to_execution",
        approval_required=True,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.PLANNING, ProjectPhase.DISCOVERY): TransitionSpec(
        from_phase=ProjectPhase.PLANNING,
        to_phase=ProjectPhase.DISCOVERY,
        name="revert_to_discovery",
        preconditions=("reversion_justification_recorded",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=True,
    ),
    (ProjectPhase.PLANNING, ProjectPhase.CLOSED): TransitionSpec(
        from_phase=ProjectPhase.PLANNING,
        to_phase=ProjectPhase.CLOSED,
        name="cancel_during_planning",
        preconditions=("cancellation_reason_provided",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.EXECUTION, ProjectPhase.MONITORING): TransitionSpec(
        from_phase=ProjectPhase.EXECUTION,
        to_phase=ProjectPhase.MONITORING,
        name="enter_monitoring",
        preconditions=(),
        required_gate=None,
        approval_required=False,
        evidence_required=False,
        is_rollback=False,
    ),
    (ProjectPhase.EXECUTION, ProjectPhase.PLANNING): TransitionSpec(
        from_phase=ProjectPhase.EXECUTION,
        to_phase=ProjectPhase.PLANNING,
        name="replanning_from_execution",
        preconditions=("replanning_justification_recorded",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=True,
    ),
    (ProjectPhase.EXECUTION, ProjectPhase.CLOSING): TransitionSpec(
        from_phase=ProjectPhase.EXECUTION,
        to_phase=ProjectPhase.CLOSING,
        name="begin_closing",
        preconditions=("all_tasks_terminal", "no_blocking_issues"),
        required_gate="dod_execution_to_closing",
        approval_required=False,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.EXECUTION, ProjectPhase.CLOSED): TransitionSpec(
        from_phase=ProjectPhase.EXECUTION,
        to_phase=ProjectPhase.CLOSED,
        name="abort_execution",
        preconditions=("termination_reason_recorded",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.MONITORING, ProjectPhase.EXECUTION): TransitionSpec(
        from_phase=ProjectPhase.MONITORING,
        to_phase=ProjectPhase.EXECUTION,
        name="resume_active_execution",
        preconditions=(),
        required_gate=None,
        approval_required=False,
        evidence_required=False,
        is_rollback=False,
    ),
    (ProjectPhase.MONITORING, ProjectPhase.PLANNING): TransitionSpec(
        from_phase=ProjectPhase.MONITORING,
        to_phase=ProjectPhase.PLANNING,
        name="replanning_from_monitoring",
        preconditions=("replanning_justification_recorded",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=True,
    ),
    (ProjectPhase.MONITORING, ProjectPhase.CLOSING): TransitionSpec(
        from_phase=ProjectPhase.MONITORING,
        to_phase=ProjectPhase.CLOSING,
        name="conclude_from_monitoring",
        preconditions=("all_tasks_terminal", "no_blocking_issues"),
        required_gate="dod_execution_to_closing",
        approval_required=False,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.MONITORING, ProjectPhase.CLOSED): TransitionSpec(
        from_phase=ProjectPhase.MONITORING,
        to_phase=ProjectPhase.CLOSED,
        name="terminate_from_monitoring",
        preconditions=("termination_reason_recorded",),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.CLOSING, ProjectPhase.EXECUTION): TransitionSpec(
        from_phase=ProjectPhase.CLOSING,
        to_phase=ProjectPhase.EXECUTION,
        name="reject_closing_to_execution",
        preconditions=("closing_failure_reason_recorded",),
        required_gate=None,
        approval_required=False,
        evidence_required=True,
        is_rollback=True,
    ),
    (ProjectPhase.CLOSING, ProjectPhase.CLOSED): TransitionSpec(
        from_phase=ProjectPhase.CLOSING,
        to_phase=ProjectPhase.CLOSED,
        name="finalize_close",
        preconditions=(
            "dod_passed_or_overridden",
            "all_tasks_terminal",
            "all_decisions_resolved",
            "all_issues_resolved_or_waived",
        ),
        required_gate="dod_final_closing",
        approval_required=True,
        evidence_required=True,
        is_rollback=False,
    ),
    (ProjectPhase.CLOSED, ProjectPhase.PLANNING): TransitionSpec(
        from_phase=ProjectPhase.CLOSED,
        to_phase=ProjectPhase.PLANNING,
        name="reopen_to_planning",
        preconditions=("reopen_justification_recorded", "accountable_approval"),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=True,
    ),
    (ProjectPhase.CLOSED, ProjectPhase.EXECUTION): TransitionSpec(
        from_phase=ProjectPhase.CLOSED,
        to_phase=ProjectPhase.EXECUTION,
        name="reopen_to_execution",
        preconditions=("reopen_justification_recorded", "accountable_approval"),
        required_gate=None,
        approval_required=True,
        evidence_required=True,
        is_rollback=True,
    ),
}

AUTHORIZED_OVERRIDE_ROLES: set[str] = {"admin", "architect", "lead", "accountable"}


def build_rules_manifest() -> dict[str, Any]:
    """Build the executable canonical governance manifest.

    The checked-in JSON manifest is a reviewable derivative of this builder.
    Runtime policy therefore has one authoritative definition, while tooling
    can hash an actual manifest to detect effective-rule drift.
    """
    return {
        "schema_version": "power.governance-rules.v1",
        "rules_version": GOVERNANCE_RULES_VERSION,
        "name": "POWER Project State Engine Governance Rules v1",
        "description": "Deterministic declarative governance and quality gate rules for POWER 3.8 PSE Phase 4.",
        "fsm": {
            "states": [phase.value for phase in ProjectPhase],
            "transitions_count": len(LEGAL_TRANSITIONS),
            "transitions": sorted(
                [
                    {
                        "name": spec.name,
                        "from_phase": spec.from_phase.value,
                        "to_phase": spec.to_phase.value,
                        "preconditions": sorted(spec.preconditions),
                        "required_gate": spec.required_gate,
                        "approval_required": spec.approval_required,
                        "evidence_required": spec.evidence_required,
                        "is_rollback": spec.is_rollback,
                    }
                    for spec in LEGAL_TRANSITIONS.values()
                ],
                key=lambda transition: (
                    transition["from_phase"],
                    transition["to_phase"],
                ),
            ),
        },
        "dor_rules": {
            "require_initial_tasks": True,
            "require_no_circular_dependencies": True,
            "blocking_issue_severities": ["blocker", "critical"],
        },
        "dod_rules": {
            "require_all_tasks_terminal": True,
            "require_all_decisions_resolved": True,
            "require_no_blocking_issues": True,
            "require_canonical_completion_evidence": True,
            "untrusted_model_statements_strictly_disallowed": True,
        },
        "override_policy": {
            "authorized_roles": sorted(AUTHORIZED_OVERRIDE_ROLES),
            "require_reason": True,
            "require_evidence": True,
            "allow_model_override": False,
        },
        "health_rules": {
            "BLOCKING_ISSUES_PRESENT": {
                "condition": "open_issues contains severity in [blocker, critical]",
                "severity": "CRITICAL",
            },
            "HIGH_RISKS_OPEN": {
                "condition": "open_risks contains impact in [critical, high] with status == identified",
                "severity": "HIGH",
            },
            "CIRCULAR_DEPENDENCY_DETECTED": {
                "condition": "directed cycle detected in task or project dependency graph",
                "severity": "CRITICAL",
            },
            "BLOCKED_TASKS_PRESENT": {
                "condition": "count(blocked_tasks) > 0",
                "severity": "MEDIUM",
            },
            "UNRESOLVED_GOVERNANCE_REQUIREMENTS": {
                "condition": "count(required_approvals) > 0",
                "severity": "HIGH",
            },
        },
        "temporal_authority": {
            "historical_source": "canonical PSE evaluation evidence at or before event sequence",
            "current_overlay_source": "current TaskStore and DecisionService snapshots",
            "future_authority_is_invalid": True,
        },
    }


def normalize_rules_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Normalize the generated JSON derivative into the executable shape."""
    normalized = deepcopy(manifest)
    fsm = normalized.get("fsm")
    if not isinstance(fsm, dict):
        raise ValueError("governance manifest must contain an fsm object")
    transitions = fsm.get("transitions")
    if not isinstance(transitions, list):
        raise ValueError("governance manifest must contain fsm.transitions")
    for transition in transitions:
        if not isinstance(transition, dict):
            raise ValueError("governance transition must be an object")
        preconditions = transition.get("preconditions", [])
        if not isinstance(preconditions, list):
            raise ValueError("governance transition preconditions must be a list")
        transition["preconditions"] = sorted(preconditions)
    fsm["states"] = list(fsm.get("states", []))
    fsm["transitions_count"] = len(transitions)
    fsm["transitions"] = sorted(
        transitions,
        key=lambda transition: (transition["from_phase"], transition["to_phase"]),
    )
    override_policy = normalized.get("override_policy")
    if not isinstance(override_policy, dict):
        roles = normalized.pop("override_roles", None)
        if not isinstance(roles, list):
            raise ValueError("governance manifest must contain override_policy")
        override_policy = {
            "authorized_roles": roles,
            "require_reason": True,
            "require_evidence": True,
            "allow_model_override": False,
        }
        normalized["override_policy"] = override_policy
    roles = override_policy.get("authorized_roles")
    if not isinstance(roles, list):
        raise ValueError("override_policy.authorized_roles must be a list")
    override_policy["authorized_roles"] = sorted(roles)
    return normalized


def compute_rules_digest(manifest: dict[str, Any] | None = None) -> str:
    """Compute SHA-256 over the normalized effective governance manifest."""
    effective_manifest = normalize_rules_manifest(
        manifest if manifest is not None else build_rules_manifest()
    )
    return hashlib.sha256(canonical_json_bytes(effective_manifest)).hexdigest()


RULES_DIGEST: str = compute_rules_digest()


@dataclass
class AuthorityContext:
    """Trusted canonical authority resolved by ProjectStateService.

    Canonical authority is established by independent resolution against the
    owning authoritative subsystem. Digests/receipts record or protect the
    result; they are not bearer credentials.

    - attached_evidence: refs attached via canonical evidence.attached /
      artifact.created events at sequences strictly before the evaluated event.
    - approved_decision_ids: decision IDs with a canonical approved
      DecisionService object carrying a valid DecisionReceipt.
    - raci: canonical role -> sorted actor list from raci.assigned/revoked.
    - accountable_actor: the single canonical Accountable actor (if any).
    - verified_task_receipts: tcr_* IDs verified via TaskStore receipts.
    - permit_accountable_approval: True only for transitions whose contract
      explicitly lists the accountable_approval precondition.
    """

    attached_evidence: set[str] = field(default_factory=set)
    approved_decision_ids: set[str] = field(default_factory=set)
    raci: dict[str, list[str]] = field(default_factory=dict)
    accountable_actor: str | None = None
    verified_task_receipts: set[str] = field(default_factory=set)
    permit_accountable_approval: bool = False
    historical: bool = False
    charter_evidence_refs: set[str] = field(default_factory=set)
    raci_accountable_cardinality_valid: bool = True


def is_untrusted_event(event: ProjectEvent | None) -> bool:
    """Detect if an event comes from an unverified or model extraction source."""
    if event is None:
        return False
    if event.source in ("model_extraction", "agent_inference", "untrusted"):
        return True
    if event.actor in ("model", "llm", "ai_agent_unverified"):
        return True
    payload = event.payload or {}
    if payload.get("verification_status") in ("proposed", "unverified", "quarantined"):
        return True
    return bool(payload.get("source_type") == "agent_inference")


def detect_dependency_cycles(
    tasks: dict[str, TaskAuthorityView],
    explicit_dependencies: list[dict[str, str]] | None = None,
) -> list[list[str]]:
    """Deterministically detect directed cycles in task dependency graphs.

    Uses DFS with recursion stack tracking. Cycle paths are normalized to start
    with their lexicographically lowest task_id and sorted deterministically.
    """
    adjacency: dict[str, set[str]] = {tid: set() for tid in tasks}

    for tid, t_view in tasks.items():
        for dep in t_view.dependencies:
            if dep in adjacency:
                adjacency[tid].add(dep)

    if explicit_dependencies:
        for exp_dep in explicit_dependencies:
            src = exp_dep.get("source_id")
            tgt = exp_dep.get("target_id")
            kind = exp_dep.get("dependency_kind", "blocks")
            if src and tgt and src in adjacency and tgt in adjacency:
                if kind in ("blocks", "requires"):
                    adjacency[tgt].add(src)
                elif kind == "blocked_by":
                    adjacency[src].add(tgt)

    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: list[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        rec_stack.append(node)

        for neighbor in sorted(adjacency.get(node, ())):
            if neighbor in rec_stack:
                idx = rec_stack.index(neighbor)
                cycle = [*rec_stack[idx:], neighbor]
                # Canonicalize cycle start
                if len(cycle) > 1:
                    inner = cycle[:-1]
                    min_idx = inner.index(min(inner))
                    normalized = [*inner[min_idx:], *inner[:min_idx], inner[min_idx]]
                    if normalized not in cycles:
                        cycles.append(normalized)
            elif neighbor not in visited:
                dfs(neighbor)

        rec_stack.pop()

    for task_id in sorted(adjacency):
        if task_id not in visited:
            dfs(task_id)

    return sorted(cycles, key=lambda c: (len(c), c))


class GovernanceEngine:
    """Authoritative Governance Policy Engine for POWER Project State."""

    def __init__(self, policy_version: str = GOVERNANCE_RULES_VERSION) -> None:
        self.policy_version = policy_version

    def evaluate_transition(
        self,
        state: ProjectState,
        to_phase: ProjectPhase,
        event: ProjectEvent,
        authority: AuthorityContext | None = None,
    ) -> GovernanceEvaluation:
        """Evaluate legality and prerequisites for an attempted lifecycle transition.

        Enforces:
        - Strict 17-transition FSM table
        - P0-1: Zero model-derived or unverified state advances
        - Rollback justifications
        - Evidence and approval gates
        - Declared TransitionSpec.preconditions via deterministic evaluators;
          unknown precondition tokens fail closed.

        When ``authority`` is provided (authoritative path), approval strings,
        evidence strings and role strings are resolved against canonical
        subsystems: approvals require a canonical approved decision with valid
        receipt (or canonical RACI Accountable where the contract explicitly
        permits it); evidence refs must each resolve to canonically attached
        evidence; every declared precondition must pass its evaluator.
        Without ``authority`` the legacy non-authoritative checks apply
        (pure-reducer determinism only; never canonical evidence).
        """
        from_phase = state.current_phase
        event_ids = [event.event_id]

        # P0-1 / Gate G4.2: Model-derived input CANNOT advance lifecycle
        if is_untrusted_event(event):
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["UNTRUSTED_MODEL_TRANSITION_PROHIBITED"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        # Closed state lock
        if from_phase == ProjectPhase.CLOSED and event.event_type != "project.reopened":
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["CLOSED_PROJECT_REQUIRES_EXPLICIT_REOPEN"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        spec = LEGAL_TRANSITIONS.get((from_phase, to_phase))
        if spec is None:
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["ILLEGAL_LIFECYCLE_TRANSITION"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        if authority is not None and not authority.raci_accountable_cardinality_valid:
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["RACI_ACCOUNTABLE_CARDINALITY_VIOLATION"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        reason_codes: list[str] = []
        payload = event.payload or {}

        # Rollback & reopen justification
        if spec.is_rollback:
            reason = (
                payload.get("reason")
                or payload.get("justification")
                or payload.get("reopen_justification")
                or payload.get("replanning_justification")
                or payload.get("closing_failure_reason")
            )
            if not reason or not str(reason).strip():
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["MISSING_TRANSITION_REASON"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )

        # Evidence requirement
        if spec.evidence_required:
            evidence = (
                event.evidence_refs
                or payload.get("evidence_refs")
                or ([payload["evidence_ref"]] if "evidence_ref" in payload else [])
            )
            if not evidence:
                return GovernanceEvaluation(
                    decision=GovernanceDecision.REQUIRE_EVIDENCE,
                    reason_codes=["MISSING_REQUIRED_EVIDENCE"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            if authority is not None:
                unresolved = [r for r in evidence if r not in authority.attached_evidence]
                if unresolved:
                    return GovernanceEvaluation(
                        decision=GovernanceDecision.REQUIRE_EVIDENCE,
                        reason_codes=["EVIDENCE_REF_NOT_CANONICALLY_ATTACHED"],
                        policy_version=self.policy_version,
                        relevant_event_ids=event_ids,
                        required_evidence_refs=sorted(set(unresolved)),
                    )

        # Approval requirement
        if spec.approval_required:
            if authority is not None:
                has_approval = self._resolve_canonical_approval(payload, state, authority, spec)
            else:
                has_approval = (
                    payload.get("approval_ref")
                    or payload.get("approval_refs")
                    or payload.get("approved_by")
                    or payload.get("accountable_approval")
                    or any(dec.status == "approved" for dec in state.decisions.values())
                )
            if not has_approval:
                return GovernanceEvaluation(
                    decision=GovernanceDecision.REQUIRE_APPROVAL,
                    reason_codes=["MISSING_REQUIRED_APPROVAL"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )

        # Declared preconditions: every token must map to an evaluator; unknown fails closed.
        if authority is not None:
            for precondition in spec.preconditions:
                if not self._evaluate_precondition(precondition, state, event, authority):
                    return GovernanceEvaluation(
                        decision=GovernanceDecision.DENY,
                        reason_codes=[f"PRECONDITION_FAILED:{precondition}"],
                        policy_version=self.policy_version,
                        relevant_event_ids=event_ids,
                    )
        # Quality Gates (DoR / DoD)
        if spec.required_gate:
            if spec.required_gate in state.overridden_gates:
                reason_codes.append(f"GATE_OVERRIDDEN:{spec.required_gate}")
            else:
                if "dor" in spec.required_gate:
                    dor_eval = self.evaluate_dor(state, to_phase)
                    if not dor_eval.passed:
                        return GovernanceEvaluation(
                            decision=GovernanceDecision.DENY,
                            reason_codes=sorted(
                                dor_eval.reason_codes or ["DOR_QUALITY_GATE_FAILED"]
                            ),
                            policy_version=self.policy_version,
                            relevant_event_ids=event_ids,
                        )
                elif "dod" in spec.required_gate:
                    dod_eval = self.evaluate_dod(state, to_phase, event, authority)
                    if not dod_eval.passed:
                        return GovernanceEvaluation(
                            decision=GovernanceDecision.DENY,
                            reason_codes=sorted(
                                dod_eval.reason_codes or ["DOD_QUALITY_GATE_FAILED"]
                            ),
                            policy_version=self.policy_version,
                            relevant_event_ids=event_ids,
                        )

        reason_codes.append("TRANSITION_ALLOWED")
        return GovernanceEvaluation(
            decision=GovernanceDecision.ALLOW,
            reason_codes=sorted(reason_codes),
            policy_version=self.policy_version,
            relevant_event_ids=event_ids,
        )

    @staticmethod
    def _resolve_canonical_approval(
        payload: dict[str, object],
        state: ProjectState,
        authority: AuthorityContext,
        spec: TransitionSpec,
    ) -> bool:
        """Resolve approval strictly against canonical subsystems (fail-closed).

        Satisfied only by: (1) a canonically approved DecisionService object
        with valid receipt whose ID is referenced; or (2) canonical RACI
        Accountable authority where the transition contract explicitly permits
        accountable approval. Bare ID/string presence never satisfies.
        """
        refs: list[str] = []
        single = payload.get("approval_ref")
        if isinstance(single, str) and single.strip():
            refs.append(single.strip())
        multi = payload.get("approval_refs")
        if isinstance(multi, list):
            refs.extend([r for r in multi if isinstance(r, str) and r.strip()])
        if any(r in authority.approved_decision_ids for r in refs):
            return True
        # Live-state fallback: approved views already resolved from DecisionService.
        live_approved = {did for did, dv in state.decisions.items() if dv.status == "approved"}
        if any(r in live_approved and r in authority.approved_decision_ids for r in refs):
            return True
        if "accountable_approval" in spec.preconditions or spec.approval_required:
            claimed = payload.get("accountable_approval") or payload.get("approved_by")
            if (
                isinstance(claimed, str)
                and authority.accountable_actor is not None
                and claimed.strip() == authority.accountable_actor
                and "accountable_approval" in spec.preconditions
            ):
                return True
        return False

    def _evaluate_precondition(
        self,
        precondition: str,
        state: ProjectState,
        event: ProjectEvent,
        authority: AuthorityContext,
    ) -> bool:
        """Deterministically evaluate one declared precondition.

        Unknown tokens fail closed (return False).
        """
        payload = event.payload or {}
        text_fields = (
            payload.get("reason"),
            payload.get("justification"),
            payload.get("reopen_justification"),
            payload.get("replanning_justification"),
            payload.get("closing_failure_reason"),
            payload.get("cancellation_reason"),
            payload.get("termination_reason"),
            payload.get("reversion_justification"),
        )
        has_reason_text = any(isinstance(v, str) and v.strip() for v in text_fields)

        if precondition == "charter_present":
            if authority.historical:
                return bool(
                    authority.charter_evidence_refs
                    and authority.charter_evidence_refs.issubset(authority.attached_evidence)
                )
            if any("charter" in ref.lower() for ref in authority.attached_evidence):
                return True
            charter_keys = ("charter", "charter_present", "charter_ref")
            return any(
                isinstance(payload.get(k), str) and str(payload.get(k)).strip()
                for k in charter_keys
            ) and any("charter" in str(v).lower() for v in payload.values() if isinstance(v, str))
        if precondition == "owner_assigned":
            if authority.historical:
                return isinstance(state.owner, str) and bool(state.owner.strip())
            owner = payload.get("owner") or payload.get("owner_assigned")
            if isinstance(owner, str) and owner.strip():
                return True
            return any(len(actors) > 0 for actors in authority.raci.values())
        if precondition in (
            "cancellation_reason_provided",
            "termination_reason_recorded",
            "reversion_justification_recorded",
            "replanning_justification_recorded",
            "reopen_justification_recorded",
            "closing_failure_reason_recorded",
        ):
            return has_reason_text
        if precondition == "dor_passed_or_overridden":
            if "dor_planning_to_execution" in state.overridden_gates:
                return True
            dor = self.evaluate_dor(state, ProjectPhase.EXECUTION)
            return dor.passed
        if precondition == "raci_accountable_assigned":
            return (
                authority.raci_accountable_cardinality_valid
                and authority.accountable_actor is not None
            )
        if precondition == "initial_tasks_registered":
            return len(state.tasks) > 0
        if precondition == "all_tasks_terminal":
            return (
                all(t.state in TERMINAL_STATES for t in state.tasks.values())
                and len(state.tasks) > 0
            )
        if precondition == "no_blocking_issues":
            for iid in state.open_issues:
                issue = state.issues.get(iid)
                if issue is not None and issue.severity in ("blocker", "critical"):
                    return False
            return True
        if precondition == "dod_passed_or_overridden":
            if (
                "dod_execution_to_closing" in state.overridden_gates
                or "dod_final_closing" in state.overridden_gates
            ):
                return True
            dod = self.evaluate_dod(state, ProjectPhase.CLOSED, event, authority)
            return dod.passed
        if precondition == "all_decisions_resolved":
            return all(d.status != "pending" for d in state.decisions.values())
        if precondition == "all_issues_resolved_or_waived":
            return len(state.open_issues) == 0
        if precondition == "accountable_approval":
            claimed = payload.get("accountable_approval") or payload.get("approved_by")
            return (
                isinstance(claimed, str)
                and authority.accountable_actor is not None
                and claimed.strip() == authority.accountable_actor
            )
        return False

    def evaluate_gate_override(
        self,
        event: ProjectEvent,
        authority: AuthorityContext | None = None,
    ) -> GovernanceEvaluation:
        """Validate whether an attempted gate.overridden event is authoritative.

        Enforces P0-3: Untrusted / model-derived candidates CANNOT override gates.
        Requires recognized authorized role and non-empty justification.

        In authoritative mode (authority provided) payload role strings never
        grant override authority: the actor must resolve to canonical
        RACI/governance state, and the frozen required metadata
        (overridden_by, justification/reason, approved_by) must be present and
        must verify against canonical authority identities.
        """
        event_ids = [event.event_id]

        if is_untrusted_event(event):
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["UNTRUSTED_MODEL_OVERRIDE_PROHIBITED"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        payload = event.payload or {}
        gate_name = payload.get("gate") or payload.get("gate_name")
        role = payload.get("role", "")
        reason = payload.get("reason", "") or payload.get("justification", "")

        if not gate_name:
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["MISSING_OVERRIDE_GATE_NAME"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        if authority is not None:
            if authority.historical and not authority.raci_accountable_cardinality_valid:
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["RACI_ACCOUNTABLE_CARDINALITY_VIOLATION"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            if authority.historical and authority.accountable_actor is None:
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["RACI_ACCOUNTABLE_REQUIRED_FOR_OVERRIDE"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            if authority.historical:
                evidence = event.evidence_refs or payload.get("evidence_refs") or []
                if not isinstance(evidence, list) or not evidence:
                    return GovernanceEvaluation(
                        decision=GovernanceDecision.REQUIRE_EVIDENCE,
                        reason_codes=["MISSING_OVERRIDE_EVIDENCE"],
                        policy_version=self.policy_version,
                        relevant_event_ids=event_ids,
                    )
                unresolved = [ref for ref in evidence if ref not in authority.attached_evidence]
                if unresolved:
                    return GovernanceEvaluation(
                        decision=GovernanceDecision.REQUIRE_EVIDENCE,
                        reason_codes=["OVERRIDE_EVIDENCE_NOT_CANONICAL"],
                        policy_version=self.policy_version,
                        relevant_event_ids=event_ids,
                        required_evidence_refs=sorted(set(unresolved)),
                    )
            overridden_by = payload.get("overridden_by") or event.actor
            approved_by = payload.get("approved_by")
            if not isinstance(overridden_by, str) or not overridden_by.strip():
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["MISSING_OVERRIDE_ACTOR"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            if not reason or not str(reason).strip():
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["MISSING_OVERRIDE_REASON"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            if not isinstance(approved_by, str) or not approved_by.strip():
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["MISSING_OVERRIDE_APPROVAL"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            authorized_actors = {
                actor
                for raci_role, actors in authority.raci.items()
                if raci_role.strip().casefold() in AUTHORIZED_OVERRIDE_ROLES
                for actor in actors
            }
            if overridden_by.strip() not in authorized_actors:
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["UNAUTHORIZED_OVERRIDE_ACTOR"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            approver_ok = (
                approved_by.strip() == (authority.accountable_actor or "")
                or approved_by.strip() in authority.approved_decision_ids
            )
            if not approver_ok:
                # approved_by may also reference a canonically approved decision
                # that authorized this override.
                return GovernanceEvaluation(
                    decision=GovernanceDecision.DENY,
                    reason_codes=["OVERRIDE_APPROVAL_NOT_CANONICAL"],
                    policy_version=self.policy_version,
                    relevant_event_ids=event_ids,
                )
            return GovernanceEvaluation(
                decision=GovernanceDecision.ALLOW,
                reason_codes=["GATE_OVERRIDE_AUTHORIZED"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        if role not in AUTHORIZED_OVERRIDE_ROLES and event.actor not in AUTHORIZED_OVERRIDE_ROLES:
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["UNAUTHORIZED_OVERRIDE_ACTOR"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        if not reason or not str(reason).strip():
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["MISSING_OVERRIDE_REASON"],
                policy_version=self.policy_version,
                relevant_event_ids=event_ids,
            )

        return GovernanceEvaluation(
            decision=GovernanceDecision.ALLOW,
            reason_codes=["GATE_OVERRIDE_AUTHORIZED"],
            policy_version=self.policy_version,
            relevant_event_ids=event_ids,
        )

    def evaluate_dor(
        self,
        state: ProjectState,
        target_phase: ProjectPhase = ProjectPhase.EXECUTION,
    ) -> DoREvaluation:
        """Evaluate Definition-of-Ready criteria for advancing into Execution."""
        reason_codes: list[str] = []
        missing_evidence: list[str] = []
        missing_approvals: list[str] = []
        blocking_deps: list[str] = []
        failed_preconditions: list[str] = []

        if "dor_planning_to_execution" in state.overridden_gates:
            return DoREvaluation(
                passed=True,
                reason_codes=["DOR_OVERRIDDEN"],
                missing_evidence=[],
                missing_approvals=[],
                blocking_dependencies=[],
                failed_preconditions=[],
            )

        # 1. Tasks must be registered for execution
        if target_phase == ProjectPhase.EXECUTION and not state.tasks:
            failed_preconditions.append("INITIAL_TASKS_NOT_REGISTERED")
            reason_codes.append("BLOCKED_DOR_NO_TASKS")

        # 2. Dependency cycles forbid readiness
        cycles = detect_dependency_cycles(state.tasks)
        if cycles:
            failed_preconditions.append("CIRCULAR_DEPENDENCY_DETECTED")
            reason_codes.append("BLOCKED_DOR_CYCLE")

        # 3. Check for blocking unresolved issues
        for issue_id in sorted(state.open_issues):
            issue = state.issues.get(issue_id)
            if issue and issue.severity in ("blocker", "critical"):
                blocking_deps.append(f"issue:{issue_id}")
                reason_codes.append("BLOCKED_DOR_HIGH_SEVERITY_ISSUE")

        passed = len(failed_preconditions) == 0 and len(reason_codes) == 0
        return DoREvaluation(
            passed=passed,
            reason_codes=sorted(set(reason_codes)),
            missing_evidence=sorted(set(missing_evidence)),
            missing_approvals=sorted(set(missing_approvals)),
            blocking_dependencies=sorted(set(blocking_deps)),
            failed_preconditions=sorted(set(failed_preconditions)),
        )

    def evaluate_dod(
        self,
        state: ProjectState,
        target_phase: ProjectPhase = ProjectPhase.CLOSED,
        event: ProjectEvent | None = None,
        authority: AuthorityContext | None = None,
    ) -> DoDEvaluation:
        """Evaluate Definition-of-Done criteria before closing.

        Enforces P0-2: Untrusted / model claims cannot satisfy DoD without canonical evidence.

        In authoritative mode (authority provided) task receipts are validated
        through canonical TaskStore receipt semantics: a random receipt ID
        never satisfies DoD, only receipts verified via the owning subsystem.
        """
        reason_codes: list[str] = []
        missing_evidence: list[str] = []
        missing_approvals: list[str] = []
        failed_conditions: list[str] = []

        if (
            "dod_execution_to_closing" in state.overridden_gates
            or "dod_final_closing" in state.overridden_gates
        ):
            return DoDEvaluation(
                passed=True,
                reason_codes=["DOD_OVERRIDDEN"],
                missing_evidence=[],
                missing_approvals=[],
                failed_conditions=[],
            )

        # P0-2: Untrusted or model event claiming completion fails without canonical evidence
        if event is not None and is_untrusted_event(event):
            missing_evidence.append("CANONICAL_COMPLETION_EVIDENCE_REQUIRED")
            reason_codes.append("UNTRUSTED_MODEL_DOD_CLAIM_REJECTED")

        # 1. All tasks must be terminal
        non_terminal = [
            tid
            for tid, t_view in sorted(state.tasks.items())
            if t_view.state not in TERMINAL_STATES
        ]
        if non_terminal:
            failed_conditions.extend([f"TASK_NOT_TERMINAL:{tid}" for tid in non_terminal])
            reason_codes.append("DOD_ACTIVE_TASKS_REMAIN")

        # 2. No blocking or critical issues
        blocking_issues = [
            iid
            for iid in sorted(state.open_issues)
            if state.issues.get(iid) and state.issues[iid].severity in ("blocker", "critical")
        ]
        if blocking_issues:
            failed_conditions.extend([f"UNRESOLVED_ISSUE:{iid}" for iid in blocking_issues])
            reason_codes.append("DOD_UNRESOLVED_BLOCKING_ISSUES")

        # 3. All valid decisions must be resolved (pending in canonical decisions map)
        pending_decisions = [
            did for did, d_view in sorted(state.decisions.items()) if d_view.status == "pending"
        ]
        if pending_decisions:
            missing_approvals.extend([f"PENDING_DECISION:{did}" for did in pending_decisions])
            reason_codes.append("DOD_PENDING_DECISIONS_REMAIN")

        # 4. Mandatory evidence: any non-empty string is NOT evidence.
        # Quality-gate evidence refs must resolve to canonical evidence known
        # to PSE (attached evidence index or verified task receipts).
        evidence_present = False
        if authority is not None:
            refs: list[str] = []
            if event is not None:
                refs.extend(event.evidence_refs or [])
                payload_refs = (event.payload or {}).get("evidence_refs") or []
                if isinstance(payload_refs, list):
                    refs.extend([r for r in payload_refs if isinstance(r, str)])
            if refs and all(r in authority.attached_evidence for r in refs):
                evidence_present = True
            if any(
                rid in authority.verified_task_receipts
                for t in state.tasks.values()
                for rid in t.receipt_ids
            ):
                evidence_present = True
        else:
            if event is not None and (
                event.evidence_refs or (event.payload and event.payload.get("evidence_refs"))
            ):
                evidence_present = True
            if any(t.receipt_ids for t in state.tasks.values()):
                evidence_present = True

        if not evidence_present and not is_untrusted_event(event):
            missing_evidence.append("COMPLETION_EVIDENCE_REQUIRED")
            reason_codes.append("DOD_MISSING_EVIDENCE")

        passed = (
            len(failed_conditions) == 0
            and len(missing_evidence) == 0
            and len(missing_approvals) == 0
        )
        return DoDEvaluation(
            passed=passed,
            reason_codes=sorted(set(reason_codes)),
            missing_evidence=sorted(set(missing_evidence)),
            missing_approvals=sorted(set(missing_approvals)),
            failed_conditions=sorted(set(failed_conditions)),
        )

    def evaluate_task_readiness(
        self,
        task: TaskAuthorityView,
        state: ProjectState,
        cycle_tasks: set[str],
    ) -> TaskReadinessEvaluation:
        """Compute fine-grained readiness for one task projection."""
        task_id = task.task_id

        # Terminal tasks
        if task.state in TERMINAL_STATES:
            return TaskReadinessEvaluation(
                task_id=task_id,
                status=TaskReadinessStatus.TERMINAL,
                reason_codes=["TASK_TERMINAL"],
                blocking_dependencies=[],
                missing_evidence=[],
                missing_approvals=[],
                cycle_path=[],
            )

        # Cycle detection
        if task_id in cycle_tasks:
            return TaskReadinessEvaluation(
                task_id=task_id,
                status=TaskReadinessStatus.CIRCULAR_DEPENDENCY,
                reason_codes=["CIRCULAR_DEPENDENCY"],
                blocking_dependencies=[],
                missing_evidence=[],
                missing_approvals=[],
                cycle_path=sorted(cycle_tasks),
            )

        # Working / In-progress
        if task.state in ("working", "input-required", "auth-required"):
            return TaskReadinessEvaluation(
                task_id=task_id,
                status=TaskReadinessStatus.IN_PROGRESS,
                reason_codes=[f"TASK_STATE_{task.state.upper().replace('-', '_')}"],
                blocking_dependencies=[],
                missing_evidence=[],
                missing_approvals=[],
                cycle_path=[],
            )

        # Check blocking dependencies
        blocking_deps: list[str] = []
        for dep_id in sorted(task.dependencies):
            dep_task = state.tasks.get(dep_id)
            if dep_task and dep_task.state not in TERMINAL_STATES:
                blocking_deps.append(dep_id)

        # Check explicit dependencies
        for dep in state.dependencies.values():
            if (
                dep.source_id == task_id
                and dep.dependency_kind in ("blocked_by", "requires")
                and dep.status != "satisfied"
            ):
                target_task = state.tasks.get(dep.target_id)
                if target_task is None or target_task.state not in TERMINAL_STATES:
                    blocking_deps.append(dep.target_id)

        if blocking_deps:
            return TaskReadinessEvaluation(
                task_id=task_id,
                status=TaskReadinessStatus.BLOCKED_DEPENDENCY,
                reason_codes=["BLOCKED_BY_DEPENDENCY"],
                blocking_dependencies=sorted(set(blocking_deps)),
                missing_evidence=[],
                missing_approvals=[],
                cycle_path=[],
            )

        # Check open gates and approvals
        if task.open_gates:
            return TaskReadinessEvaluation(
                task_id=task_id,
                status=TaskReadinessStatus.REQUIRES_APPROVAL,
                reason_codes=["OPEN_GATES_REMAIN"],
                blocking_dependencies=[],
                missing_evidence=[],
                missing_approvals=sorted(task.open_gates),
                cycle_path=[],
            )

        return TaskReadinessEvaluation(
            task_id=task_id,
            status=TaskReadinessStatus.READY,
            reason_codes=["READY"],
            blocking_dependencies=[],
            missing_evidence=[],
            missing_approvals=[],
            cycle_path=[],
        )

    def evaluate_health_flags(
        self,
        state: ProjectState,
        cycles: list[list[str]],
    ) -> list[str]:
        """Compute deterministic project health indicators based on current state."""
        flags: set[str] = set()

        # 1. Blocking issues
        for issue_id in state.open_issues:
            issue = state.issues.get(issue_id)
            if issue and issue.severity in ("blocker", "critical"):
                flags.add(HealthFlag.BLOCKING_ISSUES_PRESENT.value)
                break

        # 2. High risks open
        for risk_id in state.open_risks:
            risk = state.risks.get(risk_id)
            if risk and risk.impact in ("critical", "high") and risk.status == "identified":
                flags.add(HealthFlag.HIGH_RISKS_OPEN.value)
                break

        # 3. Circular dependencies
        if cycles:
            flags.add(HealthFlag.CIRCULAR_DEPENDENCY_DETECTED.value)

        # 4. Blocked tasks present
        if state.blocked_tasks:
            flags.add(HealthFlag.BLOCKED_TASKS_PRESENT.value)

        # 5. Required approvals pending
        if state.required_approvals:
            flags.add(HealthFlag.UNRESOLVED_GOVERNANCE_REQUIREMENTS.value)

        return sorted(flags)


__all__ = [
    "AUTHORIZED_OVERRIDE_ROLES",
    "LEGAL_TRANSITIONS",
    "RULES_DIGEST",
    "AuthorityContext",
    "GovernanceEngine",
    "TransitionSpec",
    "build_rules_manifest",
    "compute_rules_digest",
    "detect_dependency_cycles",
    "is_untrusted_event",
    "normalize_rules_manifest",
]
