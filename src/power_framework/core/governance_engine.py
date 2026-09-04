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

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    ) -> GovernanceEvaluation:
        """Evaluate legality and prerequisites for an attempted lifecycle transition.

        Enforces:
        - Strict 17-transition FSM table
        - P0-1: Zero model-derived or unverified state advances
        - Rollback justifications
        - Evidence and approval gates
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

        # Approval requirement
        if spec.approval_required:
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
                    dod_eval = self.evaluate_dod(state, to_phase, event)
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

    def evaluate_gate_override(
        self,
        event: ProjectEvent,
    ) -> GovernanceEvaluation:
        """Validate whether an attempted gate.overridden event is authoritative.

        Enforces P0-3: Untrusted / model-derived candidates CANNOT override gates.
        Requires recognized authorized role and non-empty justification.
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
        reason = payload.get("reason", "")

        if not gate_name:
            return GovernanceEvaluation(
                decision=GovernanceDecision.DENY,
                reason_codes=["MISSING_OVERRIDE_GATE_NAME"],
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
    ) -> DoDEvaluation:
        """Evaluate Definition-of-Done criteria before closing.

        Enforces P0-2: Untrusted / model claims cannot satisfy DoD without canonical evidence.
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

        # 3. All valid decisions must be resolved
        pending_decisions = [
            did
            for did in sorted(state.valid_decisions)
            if state.decisions.get(did) and state.decisions[did].status == "pending"
        ]
        if pending_decisions:
            missing_approvals.extend([f"PENDING_DECISION:{did}" for did in pending_decisions])
            reason_codes.append("DOD_PENDING_DECISIONS_REMAIN")

        # 4. Mandatory evidence
        evidence_present = False
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
    "GovernanceEngine",
    "TransitionSpec",
    "detect_dependency_cycles",
    "is_untrusted_event",
]
