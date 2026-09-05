"""POWER Project State Engine (PSE) Phase 4 — Deterministic State Reducer.

Pure, deterministic state reducer:
Canonical Phase-2 Project Event Ledger
             │
             ▼
Phase-3 Semantic Compiler (governed entities)
             │
             ▼
      ProjectStateReducer
             │
             ├── Task v2 authority (TaskAuthorityView)
             ├── typed Decision authority (DecisionAuthorityView)
             ├── RAID state aggregation
             ├── DoR / DoD gate enforcement
             ├── Governance rules & FSM (17 legal transitions)
             └── Explainability trace
             │
             ▼
       ProjectState (canonical deterministic projection)

Guarantees:
- G4.1: Full replay is 100% deterministic (byte-equivalent across independent Python processes).
- G4.2: Model-derived input CANNOT force state transitions or satisfy quality gates.
- G4.3: Task v2 remains canonical authority; no shadow task stores.
- G4.4: Existing typed decision workflow remains canonical authority.
- G4.5: Illegal transitions fail closed (IllegalStateTransitionError).
- G4.6: State fields can be explained from evidence and rules.
- Pure reducer: No LLM calls, network I/O, or store side-effects.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Literal

from power_framework.core.canonical_json import compute_event_hash, compute_payload_digest
from power_framework.core.governance_engine import (
    LEGAL_TRANSITIONS,
    RULES_DIGEST,
    AuthorityContext,
    GovernanceEngine,
    detect_dependency_cycles,
    is_untrusted_event,
)
from power_framework.core.semantic_models import (
    Assumption,
    Dependency,
    Issue,
    Provenance,
    Risk,
)
from power_framework.core.state_models import (
    GOVERNANCE_RULES_VERSION,
    STATE_SCHEMA_VERSION,
    DecisionAuthorityView,
    GovernanceDecision,
    HistoricalGovernanceEvaluation,
    IllegalStateTransitionError,
    PhaseTransitionRecord,
    ProjectPhase,
    ProjectState,
    ProjectStateSnapshot,
    SnapshotIntegrityError,
    StateEngineIntegrityError,
    StateExplanation,
    TaskAuthorityView,
    TaskReadinessStatus,
    UnexplainableFieldError,
    compute_state_revision,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from power_framework.core.project_models import ProjectEvent


class ProjectStateReducer:
    """Deterministic, pure state reducer for POWER Project State Engine.

    NON-AUTHORITATIVE BOUNDARY: reduce()/reduce_internal() perform a pure,
    deterministic replay of caller-supplied events for unit testing only.
    Integrity != authority: a self-consistent event chain is NOT proof of
    canonical ledger membership. Authoritative ProjectState must be built
    only via ProjectStateService.rebuild_project_state(vault_root,
    project_id), which verifies the canonical Phase-2 ledger, re-reads the
    authoritative event sequence from that store, resolves federated Task and
    Decision authority from their canonical services, and only then executes
    this pure reduction. Never present reduce() output as canonical state.
    """

    def __init__(
        self,
        governance_engine: GovernanceEngine | None = None,
        schema_version: Literal["power.project-state.v1"] = STATE_SCHEMA_VERSION,
        rules_version: str = GOVERNANCE_RULES_VERSION,
    ) -> None:
        self.governance_engine = governance_engine or GovernanceEngine(policy_version=rules_version)
        self.schema_version: Literal["power.project-state.v1"] = schema_version
        self.rules_version = rules_version

    def reduce(
        self,
        events: Sequence[ProjectEvent],
        initial_state: ProjectState | None = None,
        tasks: Sequence[TaskAuthorityView] | None = None,
        decisions: Sequence[DecisionAuthorityView] | None = None,
        project_id: str | None = None,
        authority: AuthorityContext | None = None,
    ) -> ProjectState:
        """Deterministically reduce an ordered event stream into ProjectState.

        NON-AUTHORITATIVE unless ``authority`` carries a trusted canonical
        bundle assembled by ProjectStateService: without it this method only
        replays caller-supplied events for determinism testing and MUST NOT
        masquerade as canonical state. With ``authority``, federated Task /
        Decision views from the owning subsystems win over ledger
        observations, evidence/approvals resolve canonically, and declared
        preconditions are enforced.

        Zero side effects: does not mutate external stores, invoke LLMs, or make network calls.
        """
        return self.reduce_internal(
            events,
            initial_state=initial_state,
            tasks=tasks,
            decisions=decisions,
            project_id=project_id,
            authority=authority,
        )

    def reduce_internal(
        self,
        events: Sequence[ProjectEvent],
        initial_state: ProjectState | None = None,
        tasks: Sequence[TaskAuthorityView] | None = None,
        decisions: Sequence[DecisionAuthorityView] | None = None,
        project_id: str | None = None,
        authority: AuthorityContext | None = None,
    ) -> ProjectState:
        """Internal pure reduction engine (see reduce() authority warning)."""
        if not events and initial_state is None and project_id is None:
            raise StateEngineIntegrityError("Cannot reduce empty event stream without project_id")

        target_project_id = project_id or (
            initial_state.project_id if initial_state else events[0].project_id
        )

        if initial_state is not None:
            state = deepcopy(initial_state)
            if state.project_id != target_project_id:
                raise StateEngineIntegrityError(
                    f"Initial state project_id '{state.project_id}' does not match target '{target_project_id}'"
                )
        else:
            state = ProjectState(
                project_id=target_project_id,
                current_phase=ProjectPhase.DISCOVERY,
                schema_version=self.schema_version,
                rules_version=self.rules_version,
                rules_digest=RULES_DIGEST,
                state_revision="0" * 64,
            )
        if (
            authority is not None
            and authority.historical
            and state.rules_digest not in {"", RULES_DIGEST}
        ):
            raise StateEngineIntegrityError("Historical replay rules digest mismatch")
        if not state.rules_digest and authority is not None and authority.historical:
            raise StateEngineIntegrityError("Historical replay requires a non-empty rules digest")
        if not state.rules_digest:
            state.rules_digest = RULES_DIGEST

        # Non-authoritative pure replay may preload supplied views for
        # determinism tests.  Historical authoritative replay deliberately
        # starts with no live federation: future TaskStore state must not be
        # visible before a canonical relationship/evaluation event.
        if tasks and not (authority is not None and authority.historical):
            for t_view in tasks:
                if authority is not None:
                    expected = TaskAuthorityView.compute_digest(
                        task_id=t_view.task_id,
                        state=t_view.state,
                        revision=t_view.revision,
                        dependencies=list(t_view.dependencies),
                        open_gates=list(t_view.open_gates),
                        receipt_ids=list(t_view.receipt_ids),
                    )
                    if expected != t_view.digest:
                        raise StateEngineIntegrityError(
                            f"Task view digest mismatch for '{t_view.task_id}': "
                            "view integrity check failed"
                        )
                state.tasks[t_view.task_id] = deepcopy(t_view)

        # Merge decision views only for pure replay/current non-historical
        # callers.  Historical approval comes from sequence-bound evaluation
        # evidence applied during replay.
        if decisions and not (authority is not None and authority.historical):
            for d_view in decisions:
                if authority is not None:
                    expected_d = DecisionAuthorityView.compute_digest(
                        decision_id=d_view.decision_id,
                        status=d_view.status,
                        task_id=d_view.task_id,
                        task_revision=d_view.task_revision,
                        revision=d_view.revision,
                        receipt_id=d_view.receipt_id,
                    )
                    if expected_d != d_view.digest:
                        raise StateEngineIntegrityError(
                            f"Decision view digest mismatch for '{d_view.decision_id}'"
                        )
                state.decisions[d_view.decision_id] = deepcopy(d_view)

        # Replay event stream sequentially with full integrity verification
        for event in events:
            self._apply_event(state, event, authority)

        # Compute post-replay projections (task readiness, decisions, health flags, state_revision)
        self._compute_projections(state, authority)

        return state

    def _apply_event(
        self,
        state: ProjectState,
        event: ProjectEvent,
        authority: AuthorityContext | None = None,
    ) -> None:
        """Apply a single canonical event to the working state with strict integrity checks."""
        # 1. Project ID integrity (cross-project contamination check)
        if event.project_id != state.project_id:
            raise StateEngineIntegrityError(
                f"Cross-project event detected: event {event.event_id} for '{event.project_id}' "
                f"cannot be applied to state for '{state.project_id}'"
            )

        # 2. Sequential ordering and hash chain verification
        if state.last_event_sequence > 0:
            expected_seq = state.last_event_sequence + 1
            if event.sequence != expected_seq:
                raise StateEngineIntegrityError(
                    f"Event sequence gap or reorder: expected {expected_seq}, got {event.sequence} (event {event.event_id})"
                )
            if event.prev_event_hash != state.last_event_hash:
                raise StateEngineIntegrityError(
                    f"Broken hash chain at sequence {event.sequence} (event {event.event_id}): "
                    f"prev_hash '{event.prev_event_hash}' != last_event_hash '{state.last_event_hash}'"
                )
        elif event.sequence != 1:
            raise StateEngineIntegrityError(
                f"Initial event sequence must be 1, got {event.sequence} (event {event.event_id})"
            )

        # 3. Cryptographic hash integrity (defense-in-depth: payload digest
        # is verified explicitly before trusting ProjectEvent content; the
        # outer event hash alone is not sufficient).
        expected_payload_digest = compute_payload_digest(event.payload or {})
        if expected_payload_digest != event.payload_digest:
            raise StateEngineIntegrityError(
                f"Tampered event payload: payload digest mismatch on event {event.event_id}"
            )
        computed_hash = compute_event_hash(event.model_dump())
        if computed_hash != event.event_hash:
            raise StateEngineIntegrityError(
                f"Tampered event payload: hash mismatch on event {event.event_id}"
            )

        # 4. Dispatch event by type
        payload = event.payload or {}
        event_type = event.event_type

        governance_bearing_types = {
            "project.created",
            "project.updated",
            "project.phase.changed",
            "project.reopened",
            "raci.assigned",
            "raci.revoked",
            "evidence.attached",
            "artifact.created",
            "artifact.updated",
            "task.associated",
            "task.disassociated",
            "decision.associated",
            "decision.disassociated",
            "dor.evaluated",
            "dod.evaluated",
            "gate.overridden",
        }
        if (
            authority is not None
            and authority.historical
            and event_type in governance_bearing_types
            and event.source != "pse_governance"
        ):
            raise StateEngineIntegrityError(
                f"Governance-bearing event requires trusted PSE provenance: {event.event_id}"
            )
        if (
            authority is not None
            and authority.historical
            and event_type in governance_bearing_types
            and is_untrusted_event(event)
        ):
            raise StateEngineIntegrityError(
                f"Untrusted governance-bearing event rejected: {event.event_id}"
            )

        if event_type == "project.created":
            state.current_phase = ProjectPhase.DISCOVERY
            self._handle_project_owner(state, event)

        elif event_type == "project.updated":
            self._handle_project_owner(state, event)

        elif event_type in ("project.phase.changed", "project.reopened"):
            self._handle_phase_transition(state, event, authority)

        elif event_type == "gate.overridden":
            self._handle_gate_override(state, event, authority)

        elif event_type == "raci.assigned":
            self._handle_raci_assigned(state, event)

        elif event_type == "raci.revoked":
            self._handle_raci_revoked(state, event)

        elif event_type == "evidence.attached":
            self._handle_evidence_attached(state, event)

        elif event_type in ("artifact.created", "artifact.updated"):
            self._handle_artifact_event(state, event)

        elif event_type in ("dor.evaluated", "dod.evaluated"):
            self._handle_historical_evaluation(state, event, authority)

        elif event_type == "task.associated":
            task_id = payload.get("task_id")
            if task_id and task_id not in state.tasks:
                digest = TaskAuthorityView.compute_digest(task_id, "backlog", 1)
                state.tasks[task_id] = TaskAuthorityView(
                    task_id=task_id,
                    state="backlog",
                    revision=1,
                    digest=digest,
                    source_identity=event.event_id,
                )

        elif event_type == "task.disassociated":
            task_id = payload.get("task_id")
            if task_id:
                state.tasks.pop(task_id, None)

        elif event_type == "task.lifecycle.observed":
            # Lifecycle observation is an audit/reconciliation signal, never
            # TaskStore authority. In authoritative mode the live TaskStore
            # view wins; the observation is recorded only as drift signal.
            task_id = payload.get("task_id")
            new_state = payload.get("state")
            if task_id and new_state:
                if authority is not None:
                    # Authoritative mode: live TaskStore view already merged;
                    # observations never create or overwrite authority.
                    if (
                        task_id in state.tasks
                        and state.tasks[task_id].state != new_state
                        and "STALE_TASK_OBSERVATION" not in list(state.health_flags)
                    ):
                        state.health_flags.append("STALE_TASK_OBSERVATION")
                        state.health_flags.append("TASK_AUTHORITY_DRIFT")
                else:
                    rev = int(payload.get("revision", 1))
                    receipt_ids = payload.get("receipt_ids", [])
                    deps = payload.get("dependencies", [])
                    open_gates = payload.get("open_gates", [])
                    digest = TaskAuthorityView.compute_digest(
                        task_id=task_id,
                        state=new_state,
                        revision=rev,
                        dependencies=deps,
                        open_gates=open_gates,
                        receipt_ids=receipt_ids,
                    )
                    state.tasks[task_id] = TaskAuthorityView(
                        task_id=task_id,
                        state=new_state,
                        revision=rev,
                        digest=digest,
                        source_identity=event.event_id,
                        dependencies=sorted(deps),
                        open_gates=sorted(open_gates),
                        receipt_ids=sorted(receipt_ids),
                    )

        elif event_type == "decision.associated":
            decision_id = payload.get("decision_id")
            if decision_id and decision_id not in state.decisions:
                digest = DecisionAuthorityView.compute_digest(decision_id, "pending")
                state.decisions[decision_id] = DecisionAuthorityView(
                    decision_id=decision_id,
                    status="pending",
                    revision=1,
                    digest=digest,
                    source_identity=event.event_id,
                )

        elif event_type == "decision.disassociated":
            decision_id = payload.get("decision_id")
            if decision_id:
                state.decisions.pop(decision_id, None)
                state.historical_approved_decisions.pop(decision_id, None)

        elif event_type == "decision.lifecycle.observed":
            # Decision observation is audit signal only; DecisionService wins.
            decision_id = payload.get("decision_id")
            new_status = payload.get("status")
            if decision_id and new_status:
                if authority is not None:
                    # Authoritative mode: live DecisionService view already
                    # merged; observations never create or overwrite authority.
                    if (
                        decision_id in state.decisions
                        and state.decisions[decision_id].status != new_status
                        and "STALE_DECISION_OBSERVATION" not in state.health_flags
                    ):
                        state.health_flags.append("STALE_DECISION_OBSERVATION")
                        state.health_flags.append("DECISION_AUTHORITY_DRIFT")
                else:
                    rev = int(payload.get("revision", 1))
                    task_id = payload.get("task_id")
                    receipt_id = payload.get("receipt_id")
                    digest = DecisionAuthorityView.compute_digest(
                        decision_id=decision_id,
                        status=new_status,
                        task_id=task_id,
                        revision=rev,
                        receipt_id=receipt_id,
                    )
                    state.decisions[decision_id] = DecisionAuthorityView(
                        decision_id=decision_id,
                        status=new_status,
                        task_id=task_id,
                        revision=rev,
                        digest=digest,
                        source_identity=event.event_id,
                        receipt_id=receipt_id,
                    )

        # RAID Events (Risks, Assumptions, Issues, Dependencies)
        elif event_type == "risk.opened":
            self._handle_risk_opened(state, event)

        elif event_type == "risk.updated":
            self._handle_risk_updated(state, event)

        elif event_type == "risk.closed":
            self._handle_risk_closed(state, event)

        elif event_type == "assumption.created":
            self._handle_assumption_created(state, event)

        elif event_type in ("assumption.updated", "assumption.confirmed"):
            self._handle_assumption_updated(state, event)

        elif event_type == "assumption.invalidated":
            self._handle_assumption_invalidated(state, event)

        elif event_type == "issue.opened":
            self._handle_issue_opened(state, event)

        elif event_type == "issue.updated":
            self._handle_issue_updated(state, event)

        elif event_type in ("issue.resolved", "issue.closed"):
            self._handle_issue_closed(state, event)

        elif event_type == "dependency.created":
            self._handle_dependency_created(state, event)

        elif event_type == "dependency.updated":
            self._handle_dependency_updated(state, event)

        elif event_type == "dependency.resolved":
            self._handle_dependency_resolved(state, event)

        # Advance state lineage
        state.last_event_sequence = event.sequence
        state.last_event_hash = event.event_hash
        state.contributing_events.append(event.event_id)

    @staticmethod
    def _handle_project_owner(state: ProjectState, event: ProjectEvent) -> None:
        """Project ownership is established only by prior project metadata."""
        payload = event.payload or {}
        owner = payload.get("owner") or payload.get("owner_id")
        if isinstance(owner, str) and owner.strip():
            state.owner = owner.strip()

    def _handle_historical_evaluation(
        self,
        state: ProjectState,
        event: ProjectEvent,
        authority: AuthorityContext | None,
    ) -> None:
        """Apply a trusted, sequence-bound DoR/DoD evaluation record."""
        if authority is None or not authority.historical:
            raise StateEngineIntegrityError(
                f"Historical governance evaluation {event.event_id} requires the trusted service boundary"
            )
        if event.source != "pse_governance":
            raise StateEngineIntegrityError(
                f"Historical governance evaluation {event.event_id} has an untrusted source"
            )
        try:
            evaluation = HistoricalGovernanceEvaluation.model_validate(event.payload or {})
        except ValueError as exc:
            raise StateEngineIntegrityError(
                f"Invalid historical governance evaluation on {event.event_id}: {exc}"
            ) from exc

        expected_type = "dor" if event.event_type == "dor.evaluated" else "dod"
        if evaluation.evaluation_type != expected_type:
            raise StateEngineIntegrityError(
                f"Evaluation type mismatch on {event.event_id}: expected {expected_type}"
            )
        allowed_phases = (
            {ProjectPhase.PLANNING, ProjectPhase.EXECUTION}
            if expected_type == "dor"
            else {ProjectPhase.CLOSING, ProjectPhase.CLOSED}
        )
        if evaluation.evaluated_phase not in allowed_phases:
            raise StateEngineIntegrityError(
                f"Evaluation phase is incompatible with {expected_type} on {event.event_id}"
            )
        if evaluation.evaluation_event_id != event.event_id:
            raise StateEngineIntegrityError(
                f"Evaluation event binding mismatch on {event.event_id}"
            )
        if (
            evaluation.rules_version != self.rules_version
            or evaluation.rules_digest != RULES_DIGEST
        ):
            raise StateEngineIntegrityError(
                f"Historical governance rules binding mismatch on {event.event_id}"
            )
        if evaluation.evaluated_from_phase != state.current_phase:
            raise StateEngineIntegrityError(
                f"Historical evaluation {event.event_id} is bound to the wrong source phase"
            )

        if any(ref not in state.attached_evidence for ref in evaluation.required_evidence_refs):
            raise StateEngineIntegrityError(
                f"Historical evaluation {event.event_id} references future or unknown evidence"
            )
        if evaluation.accountable_actor is not None:
            actors = self._accountable_actors(state.raci)
            if actors != [evaluation.accountable_actor]:
                raise StateEngineIntegrityError(
                    f"Historical evaluation {event.event_id} has invalid Accountable binding"
                )

        for task_view in evaluation.task_views:
            if task_view.task_id not in state.tasks:
                raise StateEngineIntegrityError(
                    f"Historical evaluation {event.event_id} references unassociated task "
                    f"'{task_view.task_id}'"
                )
            expected_digest = TaskAuthorityView.compute_digest(
                task_id=task_view.task_id,
                state=task_view.state,
                revision=task_view.revision,
                dependencies=list(task_view.dependencies),
                open_gates=list(task_view.open_gates),
                receipt_ids=list(task_view.receipt_ids),
            )
            if expected_digest != task_view.digest:
                raise StateEngineIntegrityError(
                    f"Historical task evaluation digest mismatch for '{task_view.task_id}'"
                )
            state.tasks[task_view.task_id] = deepcopy(task_view)

        for decision_view in evaluation.decision_views:
            if decision_view.decision_id not in state.decisions:
                raise StateEngineIntegrityError(
                    f"Historical evaluation {event.event_id} references unassociated decision "
                    f"'{decision_view.decision_id}'"
                )
            expected_digest = DecisionAuthorityView.compute_digest(
                decision_id=decision_view.decision_id,
                status=decision_view.status,
                task_id=decision_view.task_id,
                task_revision=decision_view.task_revision,
                revision=decision_view.revision,
                receipt_id=decision_view.receipt_id,
            )
            if expected_digest != decision_view.digest:
                raise StateEngineIntegrityError(
                    f"Historical decision evaluation digest mismatch for '{decision_view.decision_id}'"
                )
            state.decisions[decision_view.decision_id] = deepcopy(decision_view)

        if evaluation.result == "passed":
            if (
                evaluation.evaluated_phase
                in (
                    ProjectPhase.EXECUTION,
                    ProjectPhase.CLOSING,
                    ProjectPhase.CLOSED,
                )
                and not evaluation.task_views
            ):
                raise StateEngineIntegrityError(
                    f"Historical evaluation {event.event_id} lacks canonical task views"
                )
            state.historical_gate_evaluations[evaluation.evaluated_phase.value] = event.sequence
            state.historical_gate_origins[evaluation.evaluated_phase.value] = (
                evaluation.evaluated_from_phase.value
            )
            for decision_id in evaluation.approved_decision_ids:
                decision = state.decisions.get(decision_id)
                if decision is None or decision.status != "approved":
                    raise StateEngineIntegrityError(
                        f"Historical approval binding invalid for '{decision_id}'"
                    )
                state.historical_approved_decisions[decision_id] = event.sequence
            receipt_ids = set(evaluation.verified_task_receipts)
            known_receipts = {
                receipt_id for task in evaluation.task_views for receipt_id in task.receipt_ids
            }
            if not receipt_ids.issubset(known_receipts):
                raise StateEngineIntegrityError(
                    f"Historical completion receipt binding invalid on {event.event_id}"
                )
            for receipt_id in receipt_ids:
                state.historical_task_receipts[receipt_id] = event.sequence
        state.historical_evaluations.append(event.event_id)

    def _handle_phase_transition(
        self,
        state: ProjectState,
        event: ProjectEvent,
        authority: AuthorityContext | None = None,
    ) -> None:
        """Process project.phase.changed and project.reopened events."""
        payload = event.payload or {}
        raw_to_phase = (
            payload.get("target_phase") or payload.get("to_phase") or payload.get("phase")
        )
        if not raw_to_phase:
            raise IllegalStateTransitionError(
                f"Missing target phase in transition event {event.event_id}"
            )

        try:
            to_phase = ProjectPhase(str(raw_to_phase).upper())
        except ValueError as err:
            raise IllegalStateTransitionError(
                f"Unknown project phase '{raw_to_phase}' in event {event.event_id}"
            ) from err

        spec = LEGAL_TRANSITIONS.get((state.current_phase, to_phase))
        if (
            authority is not None
            and authority.historical
            and spec is not None
            and spec.required_gate
        ):
            required_evaluation = "dor" if "dor" in spec.required_gate else "dod"
            evaluation_sequence = state.historical_gate_evaluations.get(to_phase.value)
            evaluation_origin = state.historical_gate_origins.get(to_phase.value)
            if (
                evaluation_sequence is None
                or evaluation_sequence != state.last_event_sequence
                or evaluation_origin != state.current_phase.value
            ):
                raise IllegalStateTransitionError(
                    f"Illegal phase transition from {state.current_phase} to {to_phase} "
                    f"rejected by governance engine: MISSING_CANONICAL_{required_evaluation.upper()}_EVALUATION"
                )

        eval_result = self.governance_engine.evaluate_transition(
            state, to_phase, event, self._effective_authority(state, authority)
        )

        if eval_result.decision != GovernanceDecision.ALLOW:
            reasons = ", ".join(eval_result.reason_codes)
            raise IllegalStateTransitionError(
                f"Illegal phase transition from {state.current_phase} to {to_phase} "
                f"rejected by governance engine: {reasons}"
            )

        spec = LEGAL_TRANSITIONS[(state.current_phase, to_phase)]
        transition_record = PhaseTransitionRecord(
            from_phase=state.current_phase,
            to_phase=to_phase,
            name=spec.name,
            timestamp=event.timestamp,
            actor=event.actor,
            event_id=event.event_id,
            is_rollback=spec.is_rollback,
            reason=(
                payload.get("reason")
                or payload.get("justification")
                or payload.get("reopen_justification")
                or payload.get("replanning_justification")
                or payload.get("closing_failure_reason")
            ),
            gate=spec.required_gate,
            evidence_refs=sorted(event.evidence_refs or payload.get("evidence_refs") or []),
            approval_refs=sorted(
                [payload["approval_ref"]]
                if "approval_ref" in payload
                else payload.get("approval_refs", [])
            ),
        )
        state.phase_history.append(transition_record)
        state.current_phase = to_phase
        if authority is not None and authority.historical and spec.required_gate:
            state.historical_gate_evaluations.pop(to_phase.value, None)
            state.historical_gate_origins.pop(to_phase.value, None)

    def _effective_authority(
        self, state: ProjectState, authority: AuthorityContext | None
    ) -> AuthorityContext | None:
        """Restrict canonical authority to ledger history strictly before now.

        Prevents self-justification (transition referencing evidence attached
        in its own event) and future-justification: evidence/RACI seen by the
        governance check are only those accumulated from prior sequences.
        """
        if authority is None:
            return None
        prior_raci: dict[str, list[str]] = {
            role: sorted(actors) for role, actors in state.raci.items() if actors
        }
        accountable_actors = self._accountable_actors(prior_raci)
        cardinality_valid = len(accountable_actors) <= 1
        accountable = accountable_actors[0] if len(accountable_actors) == 1 else None
        if authority.historical:
            approved_decisions = {
                decision_id
                for decision_id, sequence in state.historical_approved_decisions.items()
                if sequence <= state.last_event_sequence
            }
            verified_receipts = {
                receipt_id
                for receipt_id, sequence in state.historical_task_receipts.items()
                if sequence <= state.last_event_sequence
            }
        else:
            approved_decisions = set(authority.approved_decision_ids)
            verified_receipts = set(authority.verified_task_receipts)
        charter_refs = {
            ref
            for ref, kind in state.evidence_kinds.items()
            if kind in {"charter", "project_charter"}
        }
        return AuthorityContext(
            attached_evidence=set(state.attached_evidence),
            approved_decision_ids=approved_decisions,
            raci=prior_raci,
            accountable_actor=accountable,
            verified_task_receipts=verified_receipts,
            permit_accountable_approval=authority.permit_accountable_approval,
            historical=authority.historical,
            charter_evidence_refs=charter_refs,
            raci_accountable_cardinality_valid=cardinality_valid,
        )

    @staticmethod
    def _accountable_actors(raci: dict[str, list[str]]) -> list[str]:
        """Normalize Accountable aliases before enforcing exactly-one cardinality."""
        actors = {
            actor
            for role, role_actors in raci.items()
            if role.strip().casefold() in {"accountable", "a"}
            for actor in role_actors
            if isinstance(actor, str) and actor.strip()
        }
        return sorted(actors)

    def _handle_raci_assigned(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record canonical raci.assigned into the deterministic RACI projection."""
        payload = event.payload or {}
        role = payload.get("role")
        actor = payload.get("actor")
        if not isinstance(role, str) or not role.strip():
            return
        if not isinstance(actor, str) or not actor.strip():
            return
        canonical_role = self._canonical_raci_role(role)
        actors = set(state.raci.get(canonical_role, []))
        actors.add(actor.strip())
        state.raci[canonical_role] = sorted(actors)

    def _handle_raci_revoked(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record canonical raci.revoked; Accountable must remain exactly one actor."""
        payload = event.payload or {}
        role = payload.get("role")
        actor = payload.get("actor")
        if not isinstance(role, str) or not role.strip():
            return
        canonical_role = self._canonical_raci_role(role)
        current = set(state.raci.get(canonical_role, []))
        if isinstance(actor, str) and actor.strip():
            current.discard(actor.strip())
        else:
            current.clear()
        if current:
            state.raci[canonical_role] = sorted(current)
        else:
            state.raci.pop(canonical_role, None)

    @staticmethod
    def _canonical_raci_role(role: str) -> str:
        normalized = role.strip()
        if normalized.casefold() in {"accountable", "a"}:
            return "Accountable"
        return normalized

    @staticmethod
    def _collect_evidence_refs(event: ProjectEvent) -> list[str]:
        """Collect canonical evidence refs carried by one ledger event."""
        refs: list[str] = []
        refs.extend(event.evidence_refs or [])
        refs.extend(event.artifact_refs or [])
        payload = event.payload or {}
        for key in ("evidence_id", "evidence_ref", "ref", "artifact_id", "artifact_ref"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                refs.append(value.strip())
        for key in ("evidence_refs", "evidence_ids", "artifact_refs"):
            value = payload.get(key)
            if isinstance(value, list):
                refs.extend([v for v in value if isinstance(v, str) and v.strip()])
        return sorted(set(refs))

    def _handle_evidence_attached(self, state: ProjectState, event: ProjectEvent) -> None:
        """Index canonically attached evidence refs (deterministic sorted set)."""
        refs = self._collect_evidence_refs(event)
        payload = event.payload or {}
        kind = payload.get("evidence_type") or payload.get("artifact_type") or payload.get("kind")
        normalized_kind = kind.strip().lower() if isinstance(kind, str) and kind.strip() else None
        for ref in refs:
            if ref not in state.attached_evidence:
                state.attached_evidence.append(ref)
            if normalized_kind is not None:
                state.evidence_kinds[ref] = normalized_kind
        state.attached_evidence = sorted(set(state.attached_evidence))
        state.evidence_kinds = {
            ref: state.evidence_kinds[ref]
            for ref in sorted(state.evidence_kinds)
            if ref in state.attached_evidence
        }

    def _handle_artifact_event(self, state: ProjectState, event: ProjectEvent) -> None:
        """Index artifact refs as canonical evidence (same index as evidence)."""
        self._handle_evidence_attached(state, event)

    def _handle_gate_override(
        self, state: ProjectState, event: ProjectEvent, authority: AuthorityContext | None = None
    ) -> None:
        """Process gate.overridden events with strict trust checking."""
        if authority is not None and authority.historical and event.source != "pse_governance":
            raise StateEngineIntegrityError(
                f"Gate override {event.event_id} requires the trusted service boundary"
            )
        eval_result = self.governance_engine.evaluate_gate_override(
            event, self._effective_authority(state, authority)
        )
        if eval_result.decision == GovernanceDecision.ALLOW:
            payload = event.payload or {}
            gate_name = str(payload.get("gate") or payload.get("gate_name"))
            if gate_name not in state.overridden_gates:
                state.overridden_gates.append(gate_name)

    def _handle_risk_opened(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record risk.opened in state risks and open_risks."""
        payload = event.payload or {}
        risk_id = payload.get("risk_id")
        if not risk_id:
            return

        if not is_untrusted_event(event):
            prov = Provenance(
                source_event_ids=[event.event_id],
                actor=event.actor,
                timestamp=event.timestamp,
                source_type="event_replay",
                verification_status="verified",
            )
            risk = Risk(
                risk_id=risk_id,
                project_id=state.project_id,
                title=payload.get("title", f"Risk {risk_id}"),
                description=payload.get("description", ""),
                probability=payload.get("probability", "medium"),
                impact=payload.get("impact", "medium"),
                mitigation_plan=payload.get("mitigation_plan", ""),
                owner=payload.get("owner", event.actor),
                status=payload.get("status", "identified"),
                related_task_ids=sorted(payload.get("related_task_ids", [])),
                provenance=prov,
                created_at=event.timestamp,
                updated_at=event.timestamp,
            )
            state.risks[risk_id] = risk
            if risk.status == "identified" and risk_id not in state.open_risks:
                state.open_risks.append(risk_id)

    def _handle_risk_updated(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record risk.updated in state risks and manage open_risks."""
        payload = event.payload or {}
        risk_id = payload.get("risk_id")
        if not risk_id or is_untrusted_event(event):
            return

        risk = state.risks.get(risk_id)
        if risk:
            updated_dict = risk.model_dump()
            for key in (
                "title",
                "description",
                "probability",
                "impact",
                "mitigation_plan",
                "owner",
                "status",
            ):
                if key in payload:
                    updated_dict[key] = payload[key]
            updated_dict["updated_at"] = event.timestamp
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.risks[risk_id] = Risk.model_validate(updated_dict)

            if state.risks[risk_id].status in ("mitigated", "retired", "closed"):
                if risk_id in state.open_risks:
                    state.open_risks.remove(risk_id)
            elif state.risks[risk_id].status == "identified" and risk_id not in state.open_risks:
                state.open_risks.append(risk_id)

    def _handle_risk_closed(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record risk.closed."""
        payload = event.payload or {}
        risk_id = payload.get("risk_id")
        if not risk_id or is_untrusted_event(event):
            return

        risk = state.risks.get(risk_id)
        if risk:
            updated_dict = risk.model_dump()
            updated_dict["status"] = "retired"
            updated_dict["updated_at"] = event.timestamp
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.risks[risk_id] = Risk.model_validate(updated_dict)

        if risk_id in state.open_risks:
            state.open_risks.remove(risk_id)

    def _handle_assumption_created(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record assumption.created."""
        payload = event.payload or {}
        asm_id = payload.get("assumption_id")
        if not asm_id or is_untrusted_event(event):
            return

        prov = Provenance(
            source_event_ids=[event.event_id],
            actor=event.actor,
            timestamp=event.timestamp,
            source_type="event_replay",
            verification_status="verified",
        )
        asm = Assumption(
            assumption_id=asm_id,
            project_id=state.project_id,
            statement=payload.get("statement", ""),
            rationale=payload.get("rationale", ""),
            confidence=float(payload.get("confidence", 1.0)),
            status=payload.get("status", "valid"),
            provenance=prov,
            created_at=event.timestamp,
        )
        state.assumptions[asm_id] = asm
        if asm.status in ("valid", "confirmed") and asm_id not in state.active_assumptions:
            state.active_assumptions.append(asm_id)

    def _handle_assumption_updated(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record assumption.updated / assumption.confirmed."""
        payload = event.payload or {}
        asm_id = payload.get("assumption_id")
        if not asm_id or is_untrusted_event(event):
            return

        asm = state.assumptions.get(asm_id)
        if asm:
            updated_dict = asm.model_dump()
            if "status" in payload:
                updated_dict["status"] = payload["status"]
            if "confidence" in payload:
                updated_dict["confidence"] = float(payload["confidence"])
            if event.event_type == "assumption.confirmed":
                updated_dict["status"] = "confirmed"
                updated_dict["validated_at"] = event.timestamp
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.assumptions[asm_id] = Assumption.model_validate(updated_dict)

            if updated_dict["status"] == "invalidated":
                if asm_id in state.active_assumptions:
                    state.active_assumptions.remove(asm_id)
            elif asm_id not in state.active_assumptions:
                state.active_assumptions.append(asm_id)

    def _handle_assumption_invalidated(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record assumption.invalidated."""
        payload = event.payload or {}
        asm_id = payload.get("assumption_id")
        if not asm_id or is_untrusted_event(event):
            return

        asm = state.assumptions.get(asm_id)
        if asm:
            updated_dict = asm.model_dump()
            updated_dict["status"] = "invalidated"
            updated_dict["invalidated_by"] = event.actor
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.assumptions[asm_id] = Assumption.model_validate(updated_dict)

        if asm_id in state.active_assumptions:
            state.active_assumptions.remove(asm_id)

    def _handle_issue_opened(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record issue.opened (or reopen an existing issue)."""
        payload = event.payload or {}
        issue_id = payload.get("issue_id")
        if not issue_id or is_untrusted_event(event):
            return

        prov = Provenance(
            source_event_ids=[event.event_id],
            actor=event.actor,
            timestamp=event.timestamp,
            source_type="event_replay",
            verification_status="verified",
        )
        issue = Issue(
            issue_id=issue_id,
            project_id=state.project_id,
            title=payload.get("title", f"Issue {issue_id}"),
            description=payload.get("description", ""),
            severity=payload.get("severity", "major"),
            status=payload.get("status", "open"),
            blocking_task_ids=sorted(payload.get("blocking_task_ids", [])),
            resolution=payload.get("resolution"),
            provenance=prov,
            created_at=event.timestamp,
        )
        state.issues[issue_id] = issue
        if issue.status in ("open", "investigating") and issue_id not in state.open_issues:
            state.open_issues.append(issue_id)

    def _handle_issue_updated(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record issue.updated."""
        payload = event.payload or {}
        issue_id = payload.get("issue_id")
        if not issue_id or is_untrusted_event(event):
            return

        issue = state.issues.get(issue_id)
        if issue:
            updated_dict = issue.model_dump()
            for key in ("title", "description", "severity", "status", "resolution"):
                if key in payload:
                    updated_dict[key] = payload[key]
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.issues[issue_id] = Issue.model_validate(updated_dict)

            if updated_dict["status"] in ("resolved", "closed"):
                if issue_id in state.open_issues:
                    state.open_issues.remove(issue_id)
            elif (
                updated_dict["status"] in ("open", "investigating")
                and issue_id not in state.open_issues
            ):
                state.open_issues.append(issue_id)

    def _handle_issue_closed(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record issue.resolved or issue.closed."""
        payload = event.payload or {}
        issue_id = payload.get("issue_id")
        if not issue_id:
            return

        # Gate G4.2 / Section 19: Model-extracted candidate cannot close an issue authoritatively
        if is_untrusted_event(event):
            return

        issue = state.issues.get(issue_id)
        if issue:
            updated_dict = issue.model_dump()
            updated_dict["status"] = (
                "resolved" if event.event_type == "issue.resolved" else "closed"
            )
            updated_dict["resolved_at"] = event.timestamp
            if "resolution" in payload:
                updated_dict["resolution"] = payload["resolution"]
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.issues[issue_id] = Issue.model_validate(updated_dict)

        if issue_id in state.open_issues:
            state.open_issues.remove(issue_id)

    def _handle_dependency_created(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record dependency.created."""
        payload = event.payload or {}
        dep_id = payload.get("dependency_id")
        if not dep_id or is_untrusted_event(event):
            return

        prov = Provenance(
            source_event_ids=[event.event_id],
            actor=event.actor,
            timestamp=event.timestamp,
            source_type="event_replay",
            verification_status="verified",
        )
        dep = Dependency(
            dependency_id=dep_id,
            project_id=state.project_id,
            source_id=payload.get("source_id", ""),
            target_id=payload.get("target_id", ""),
            target_type=payload.get("target_type", "task"),
            dependency_kind=payload.get("dependency_kind", "blocks"),
            status=payload.get("status", "pending"),
            external_ref=payload.get("external_ref"),
            provenance=prov,
            created_at=event.timestamp,
        )
        state.dependencies[dep_id] = dep
        if dep.status != "satisfied" and dep_id not in state.active_dependencies:
            state.active_dependencies.append(dep_id)

    def _handle_dependency_updated(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record dependency.updated."""
        payload = event.payload or {}
        dep_id = payload.get("dependency_id")
        if not dep_id or is_untrusted_event(event):
            return

        dep = state.dependencies.get(dep_id)
        if dep:
            updated_dict = dep.model_dump()
            if "status" in payload:
                updated_dict["status"] = payload["status"]
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.dependencies[dep_id] = Dependency.model_validate(updated_dict)

            if updated_dict["status"] == "satisfied":
                if dep_id in state.active_dependencies:
                    state.active_dependencies.remove(dep_id)
            elif dep_id not in state.active_dependencies:
                state.active_dependencies.append(dep_id)

    def _handle_dependency_resolved(self, state: ProjectState, event: ProjectEvent) -> None:
        """Record dependency.resolved."""
        payload = event.payload or {}
        dep_id = payload.get("dependency_id")
        if not dep_id or is_untrusted_event(event):
            return

        dep = state.dependencies.get(dep_id)
        if dep:
            updated_dict = dep.model_dump()
            updated_dict["status"] = "satisfied"
            updated_dict["provenance"]["source_event_ids"] = sorted(
                {*updated_dict["provenance"]["source_event_ids"], event.event_id}
            )
            state.dependencies[dep_id] = Dependency.model_validate(updated_dict)

        if dep_id in state.active_dependencies:
            state.active_dependencies.remove(dep_id)

    def _compute_projections(
        self, state: ProjectState, authority: AuthorityContext | None = None
    ) -> None:
        """Compute all post-reduction projections deterministically."""
        # 1. Dependency cycle analysis
        explicit_deps = [dep.model_dump() for dep in state.dependencies.values()]
        cycles = detect_dependency_cycles(state.tasks, explicit_deps)
        cycle_tasks = {node for cycle in cycles for node in cycle}

        # 2. Task readiness projections
        active: list[str] = []
        ready: list[str] = []
        blocked: list[str] = []

        for task_id in sorted(state.tasks):
            t_view = state.tasks[task_id]
            readiness = self.governance_engine.evaluate_task_readiness(t_view, state, cycle_tasks)

            if readiness.status != TaskReadinessStatus.TERMINAL:
                active.append(task_id)

            if readiness.status == TaskReadinessStatus.READY:
                ready.append(task_id)
            elif readiness.status in (
                TaskReadinessStatus.BLOCKED_DEPENDENCY,
                TaskReadinessStatus.CIRCULAR_DEPENDENCY,
                TaskReadinessStatus.REQUIRES_APPROVAL,
                TaskReadinessStatus.REQUIRES_EVIDENCE,
                TaskReadinessStatus.BLOCKED_DOR,
            ):
                blocked.append(task_id)

        state.active_tasks = sorted(active)
        state.ready_tasks = sorted(ready)
        state.blocked_tasks = sorted(blocked)

        # 3. Decision projections: valid_decisions = approved canonical
        # decisions; required_approvals = pending decisions. Pending is never
        # reported as valid/approved.
        valid_decs: list[str] = []
        super_decs: list[str] = []
        req_approvals: list[str] = []

        for dec_id in sorted(state.decisions):
            d_view = state.decisions[dec_id]
            if d_view.status == "approved":
                valid_decs.append(dec_id)
            elif d_view.status == "superseded":
                super_decs.append(dec_id)

            if d_view.status == "pending":
                req_approvals.append(dec_id)

        state.valid_decisions = sorted(valid_decs)
        state.superseded_decisions = sorted(super_decs)
        state.required_approvals = sorted(req_approvals)

        # 4. RAID projections sorting (+ canonical governance projections)
        state.open_risks = sorted(set(state.open_risks))
        state.open_issues = sorted(set(state.open_issues))
        state.active_assumptions = sorted(set(state.active_assumptions))
        state.active_dependencies = sorted(set(state.active_dependencies))
        state.overridden_gates = sorted(set(state.overridden_gates))
        state.attached_evidence = sorted(set(state.attached_evidence))
        state.raci = {role: sorted(set(actors)) for role, actors in sorted(state.raci.items())}
        state.evidence_kinds = {
            ref: state.evidence_kinds[ref] for ref in sorted(state.evidence_kinds)
        }
        state.historical_approved_decisions = {
            decision_id: state.historical_approved_decisions[decision_id]
            for decision_id in sorted(state.historical_approved_decisions)
        }
        state.historical_task_receipts = {
            receipt_id: state.historical_task_receipts[receipt_id]
            for receipt_id in sorted(state.historical_task_receipts)
        }
        state.historical_evaluations = sorted(set(state.historical_evaluations))
        state.historical_gate_evaluations = {
            phase: state.historical_gate_evaluations[phase]
            for phase in sorted(state.historical_gate_evaluations)
        }
        state.historical_gate_origins = {
            phase: state.historical_gate_origins[phase]
            for phase in sorted(state.historical_gate_origins)
        }
        if (
            authority is not None
            and authority.historical
            and state.rules_digest not in {"", RULES_DIGEST}
        ):
            raise StateEngineIntegrityError("Historical projection rules digest mismatch")
        if not state.rules_digest and authority is not None and authority.historical:
            raise StateEngineIntegrityError(
                "Historical projection requires a non-empty rules digest"
            )
        if not state.rules_digest:
            state.rules_digest = RULES_DIGEST

        # 5. Recent changes: deterministic last 10 event IDs
        state.recent_changes = state.contributing_events[-10:] if state.contributing_events else []

        # 6. Health flags (preserve drift diagnostics recorded during replay)
        drift_flags = [
            f
            for f in state.health_flags
            if f
            in (
                "STALE_TASK_OBSERVATION",
                "TASK_AUTHORITY_DRIFT",
                "STALE_DECISION_OBSERVATION",
                "DECISION_AUTHORITY_DRIFT",
                "STALE_AUTHORITATIVE_PROJECTION",
            )
        ]
        computed_flags = self.governance_engine.evaluate_health_flags(state, cycles)
        state.health_flags = sorted(set(computed_flags) | set(drift_flags))

        # 7. Deterministic state_revision
        state.state_revision = compute_state_revision(state.model_dump())

    def explain(self, state: ProjectState, field: str) -> StateExplanation:
        """Provide deterministic evidence and rule trace explaining one state field."""
        if field == "current_phase":
            contributing = [r.event_id for r in state.phase_history]
            rules = [f"FSM_RULE:{r.from_phase}->{r.to_phase}:{r.name}" for r in state.phase_history]
            evidence = [ref for r in state.phase_history for ref in r.evidence_refs]
            approvals = [ref for r in state.phase_history for ref in r.approval_refs]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.current_phase.value,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=sorted(set(rules)),
                decision_references=sorted(set(approvals)),
                evidence_references=sorted(set(evidence)),
                authority_references=["ProjectLifecycleFSM:v1"],
            )

        if field == "active_tasks":
            contributing = [t.source_identity for t in state.tasks.values()]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.active_tasks,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=["TASK_LIFECYCLE_NON_TERMINAL"],
                decision_references=[],
                evidence_references=[],
                authority_references=["TaskStore:v2"],
            )

        if field == "ready_tasks":
            contributing = [
                state.tasks[t].source_identity for t in state.ready_tasks if t in state.tasks
            ]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.ready_tasks,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=["TASK_READINESS_NO_BLOCKING_DEPS_NO_CYCLES"],
                decision_references=[],
                evidence_references=[],
                authority_references=["TaskStore:v2"],
            )

        if field == "blocked_tasks":
            contributing = [
                state.tasks[t].source_identity for t in state.blocked_tasks if t in state.tasks
            ]
            rules = ["TASK_BLOCKED_BY_DEPENDENCY_OR_CYCLE"]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.blocked_tasks,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=sorted(rules),
                decision_references=[],
                evidence_references=[],
                authority_references=["TaskStore:v2"],
            )

        if field == "open_risks":
            contributing = [
                eid
                for rid in state.open_risks
                if rid in state.risks
                for eid in state.risks[rid].provenance.source_event_ids
            ]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.open_risks,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=["RISK_STATUS_IDENTIFIED"],
                decision_references=[],
                evidence_references=[],
                authority_references=["PSE:RAID:v1"],
            )

        if field == "open_issues":
            contributing = [
                eid
                for iid in state.open_issues
                if iid in state.issues
                for eid in state.issues[iid].provenance.source_event_ids
            ]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.open_issues,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=["ISSUE_STATUS_OPEN_OR_INVESTIGATING"],
                decision_references=[],
                evidence_references=[],
                authority_references=["PSE:RAID:v1"],
            )

        if field == "valid_decisions":
            contributing = [d.source_identity for d in state.decisions.values()]
            receipts = [d.receipt_id for d in state.decisions.values() if d.receipt_id]
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.valid_decisions,
                contributing_event_ids=sorted(set(contributing)),
                applicable_rules=["DECISION_STATUS_APPROVED"],
                decision_references=state.valid_decisions,
                evidence_references=sorted(set(receipts)),
                authority_references=["DecisionService:v1"],
            )

        if field == "health_flags":
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.health_flags,
                contributing_event_ids=sorted(set(state.recent_changes)),
                applicable_rules=["HEALTH_RULES_V1"],
                decision_references=[],
                evidence_references=[],
                authority_references=["GovernanceEngine:v1"],
            )

        if field == "required_approvals":
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.required_approvals,
                contributing_event_ids=[
                    state.decisions[d].source_identity
                    for d in state.required_approvals
                    if d in state.decisions
                ],
                applicable_rules=["PENDING_DECISION_REQUIRES_APPROVAL"],
                decision_references=state.required_approvals,
                evidence_references=[],
                authority_references=["DecisionService:v1"],
            )

        if field == "state_revision":
            return StateExplanation(
                project_id=state.project_id,
                field=field,
                state_revision=state.state_revision,
                value=state.state_revision,
                contributing_event_ids=sorted(set(state.contributing_events)),
                applicable_rules=[
                    f"SCHEMA:{state.schema_version}",
                    f"RULES:{state.rules_version}",
                ],
                decision_references=state.valid_decisions,
                evidence_references=[],
                authority_references=["CanonicalJson:v1"],
            )

        # Field not recognized: fail closed
        raise UnexplainableFieldError(
            f"State field '{field}' is not a recognized explainable state property"
        )

    def create_snapshot(self, state: ProjectState) -> ProjectStateSnapshot:
        """Create a cryptographically verified snapshot of the given state."""
        return ProjectStateSnapshot.create(state)

    def restore_from_snapshot(
        self,
        snapshot: ProjectStateSnapshot,
        tail_events: Sequence[ProjectEvent] = (),
        authority: AuthorityContext | None = None,
    ) -> ProjectState:
        """Restore project state from a validated snapshot and replay tail events.

        Guarantees that snapshot + tail replay is byte-equivalent to full replay (G4.1).
        Any snapshot tampering causes immediate SnapshotIntegrityError.

        Integrity != authority: this checks internal self-consistency only.
        Authoritative restore must additionally verify ledger lineage and
        re-resolve federated authority via
        ProjectStateService.restore_snapshot_authoritative.
        """
        if not snapshot.verify_integrity():
            raise SnapshotIntegrityError(
                f"Snapshot integrity verification failed for project {snapshot.project_id}"
            )

        if snapshot.schema_version != self.schema_version:
            raise SnapshotIntegrityError(
                f"Snapshot schema version '{snapshot.schema_version}' != current '{self.schema_version}'"
            )

        if snapshot.rules_version != self.rules_version:
            raise SnapshotIntegrityError(
                f"Snapshot rules version '{snapshot.rules_version}' != current '{self.rules_version}'"
            )

        if not snapshot.state.rules_digest or snapshot.state.rules_digest != RULES_DIGEST:
            raise SnapshotIntegrityError(
                "Snapshot ruleset digest mismatch: effective governance rules changed"
            )

        working_state = deepcopy(snapshot.state)

        # Replay tail events onto the restored state
        if tail_events:
            first_event = tail_events[0]
            expected_seq = working_state.last_event_sequence + 1
            if first_event.sequence != expected_seq:
                raise StateEngineIntegrityError(
                    f"Tail event sequence gap: snapshot at {working_state.last_event_sequence}, "
                    f"first tail event at {first_event.sequence}"
                )
            if first_event.prev_event_hash != working_state.last_event_hash:
                raise StateEngineIntegrityError(
                    f"Tail event hash mismatch: snapshot head hash '{working_state.last_event_hash}' "
                    f"!= first tail event prev_hash '{first_event.prev_event_hash}'"
                )

            for event in tail_events:
                self._apply_event(working_state, event, authority)

            self._compute_projections(working_state, authority)

        return working_state

    def verify_snapshot_lineage(
        self,
        snapshot: ProjectStateSnapshot,
        ledger_sequence: int,
        ledger_head_hash: str,
    ) -> bool:
        """Verify snapshot lineage against a trusted re-read of the canonical ledger.

        Returns True only when snapshot.project_id's last_event_sequence and
        last_event_hash exactly match the canonical ledger head. Integrity of
        the snapshot itself must be verified separately.
        """
        return (
            snapshot.last_event_sequence == ledger_sequence
            and snapshot.last_event_hash == ledger_head_hash
        )


__all__ = [
    "ProjectStateReducer",
]
