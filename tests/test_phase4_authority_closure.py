"""POWER 3.8 PSE Phase 4 — Authority & Governance Closure Tests (T1-T12).

AUTHORITATIVE STATE ENGINE INTEGRATION TESTS. These tests use a real
temporary vault, the real ProjectEventStore, the real TaskStore/TaskService
and the real DecisionService. They prove that forged, stale, or
self-declared authority is rejected fail-closed while the legitimate
canonical path remains reachable (positive control).

Integrity != authority: self-consistent objects, matching self-digests,
source identity strings, observed lifecycles and snapshot seals are never
bearer credentials. Canonical authority is established by independent
resolution against the owning authoritative subsystem.

Pure-reducer determinism tests live in tests/test_phase4_state_engine.py and
must not be read as canonical-authority evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from power_framework.core.canonical_json import (
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.decision_service import DecisionService
from power_framework.core.governance_engine import (
    LEGAL_TRANSITIONS,
    AuthorityContext,
    GovernanceDecision,
    GovernanceEngine,
    compute_rules_digest,
)
from power_framework.core.project_models import AppendCommand, ProjectEvent
from power_framework.core.project_store import ProjectEventStore
from power_framework.core.state_models import (
    DecisionAuthorityView,
    IllegalStateTransitionError,
    ProjectPhase,
    ProjectState,
    ProjectStateSnapshot,
    SnapshotIntegrityError,
    TaskAuthorityView,
)
from power_framework.core.state_reducer import ProjectStateReducer
from power_framework.core.state_service import (
    AuthoritativeStateError,
    ProjectStateService,
)
from power_framework.core.task_service import TaskService

LEAD = "user:lead"
ENGINEER = "user:engineer"


# ---------------------------------------------------------------------------
# Helpers: real canonical vault
# ---------------------------------------------------------------------------


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    return vault


def append(
    vault: Path,
    pid: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    actor: str = ENGINEER,
    source: str = "cli",
    evidence_refs: list[str] | None = None,
    artifact_refs: list[str] | None = None,
) -> ProjectEvent:
    store = ProjectEventStore(pid, vault)
    return store.append(
        AppendCommand(
            project_id=pid,
            event_type=event_type,
            payload=payload or {},
            actor=actor,
            source=source,
            evidence_refs=evidence_refs or [],
            artifact_refs=artifact_refs or [],
        )
    )


def attach_evidence(vault: Path, pid: str, ref: str) -> ProjectEvent:
    return append(
        vault,
        pid,
        "evidence.attached",
        {"evidence_id": ref},
        actor=LEAD,
    )


def assign_accountable(vault: Path, pid: str, actor: str = LEAD) -> ProjectEvent:
    return append(
        vault,
        pid,
        "raci.assigned",
        {"role": "Accountable", "actor": actor},
        actor=LEAD,
    )


def make_taskvault_task(service: TaskService, task_id: str, state: str = "backlog") -> Any:
    return service.create_task(
        task_id=task_id,
        title=f"Task {task_id}",
        objective="closure test",
        owner="local",
        state=state,  # type: ignore[arg-type]
    )


def complete_task(service: TaskService, vault: Path, task_id: str) -> Any:
    artifact = vault / f"{task_id}_done.txt"
    artifact.write_text("done", encoding="utf-8")
    task = service.get_task(task_id)
    assert task is not None
    if task.state == "backlog":
        task = service.transition_task(task_id, "working", actor="local")  # type: ignore[arg-type]
    return service.transition_task(
        task_id,
        "completed",  # type: ignore[arg-type]
        actor="local",
        expected_revision=task.revision,
        completion_postcondition=f"{task_id} verified complete",
        completion_artifact_refs=[artifact.name],
    )


def make_approved_decision(
    decisions: DecisionService,
    decision_id: str,
    task_id: str,
    actor: str = "operator-1",
) -> Any:
    decisions.create_decision(
        decision_id=decision_id,
        task_id=task_id,
        title=f"Decision {decision_id}",
        requested_by="requester-1",
        allowed_actors=[actor],
    )
    resolved, _receipt = decisions.resolve_decision(
        decision_id,
        action="approve",
        actor=actor,
        authority="apply",
    )
    return resolved


def make_forged_chain(pid: str, n: int = 2) -> list[ProjectEvent]:
    """Build an internally valid chain exactly as synthetic tests do (never appended)."""
    events: list[ProjectEvent] = []
    prev_hash = ""
    types = ["project.created", "project.phase.changed"]
    for i in range(1, n + 1):
        etype = types[(i - 1) % len(types)]
        payload: dict[str, Any] = {} if etype == "project.created" else {"target_phase": "PLANNING"}
        raw: dict[str, Any] = {
            "event_id": f"evt_forged_{i:04d}",
            "schema_version": "power.project-event.v1",
            "project_id": pid,
            "sequence": i,
            "timestamp": f"2026-09-05T02:00:{i:02d}Z",
            "actor": "test_lead",
            "source": "cli",
            "session_id": None,
            "event_type": etype,
            "payload": payload,
            "payload_digest": "0" * 64,
            "prev_event_hash": prev_hash,
            "artifact_refs": [],
            "evidence_refs": ["evi_charter"] if i == 2 else [],
            "correlation_id": None,
            "causation_id": None,
            "idempotency_key": None,
            "event_hash": "0" * 64,
        }
        event = ProjectEvent(**raw)
        event.payload_digest = compute_payload_digest(event.payload)
        event.event_hash = compute_event_hash(event.model_dump())
        events.append(event)
        prev_hash = event.event_hash
    return events


# ---------------------------------------------------------------------------
# T1 — forged event chain
# ---------------------------------------------------------------------------


class TestT1ForgedEventChain:
    def test_forged_chain_rejected_authoritative(self, tmp_path: Path) -> None:
        """T1: self-consistent forged chain, never appended, must be REJECTED."""
        vault = make_vault(tmp_path)
        pid = "prj_t1_forged"
        append(vault, pid, "project.created", {"name": "T1"})
        service = ProjectStateService(vault)
        forged = make_forged_chain(pid)
        # Pure reducer replays caller bytes (non-authoritative determinism only).
        pure = ProjectStateReducer().reduce(forged)
        assert pure.current_phase == ProjectPhase.PLANNING
        # Authoritative path rejects: not canonical ledger members.
        with pytest.raises(AuthoritativeStateError, match="REJECTED"):
            service.rebuild_from_candidates(pid, forged)


# ---------------------------------------------------------------------------
# T2 — real ledger contains different events
# ---------------------------------------------------------------------------


class TestT2RealLedgerDifferentFakeStream:
    def test_fake_stream_rejected(self, tmp_path: Path) -> None:
        """T2: canonical A/B/C vs internally valid fake X/Y/Z -> REJECT."""
        vault = make_vault(tmp_path)
        pid = "prj_t2_streams"
        append(vault, pid, "project.created", {"name": "T2"})
        attach_evidence(vault, pid, "evi_charter_01")
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "PLANNING", "owner": LEAD},
            actor=LEAD,
            evidence_refs=["evi_charter_01"],
        )
        service = ProjectStateService(vault)
        canonical = service.rebuild_project_state(pid)
        assert canonical.current_phase == ProjectPhase.PLANNING

        fake = make_forged_chain(pid, n=3)
        with pytest.raises(AuthoritativeStateError, match="REJECTED"):
            service.rebuild_from_candidates(pid, fake)


# ---------------------------------------------------------------------------
# T3 — forged task view
# ---------------------------------------------------------------------------


class TestT3ForgedTaskView:
    def test_live_taskstore_wins_over_forged_view(self, tmp_path: Path) -> None:
        """T3: forged completed view with valid digest vs live working -> working wins."""
        vault = make_vault(tmp_path)
        pid = "prj_t3_taskview"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_1", state="working")
        append(vault, pid, "project.created", {"name": "T3"})
        append(vault, pid, "task.associated", {"task_id": "task_1"})

        forged_view = TaskAuthorityView(
            task_id="task_1",
            state="completed",
            revision=9,
            digest=TaskAuthorityView.compute_digest("task_1", "completed", 9),
            source_identity="TaskStore:v2",
        )
        assert forged_view.digest == TaskAuthorityView.compute_digest("task_1", "completed", 9)

        service = ProjectStateService(vault, task_service=tasks)
        state = service.rebuild_project_state(pid)
        assert state.tasks["task_1"].state == "working"
        governance = GovernanceEngine()
        dod = governance.evaluate_dod(state, ProjectPhase.CLOSED, event=None)
        assert dod.passed is False


# ---------------------------------------------------------------------------
# T4 — stale task observation
# ---------------------------------------------------------------------------


class TestT4StaleTaskObservation:
    def test_observed_completed_does_not_override_working(self, tmp_path: Path) -> None:
        """T4: ledger says completed, TaskStore says working -> working wins, DoD FAIL."""
        vault = make_vault(tmp_path)
        pid = "prj_t4_stale"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_1", state="working")
        append(vault, pid, "project.created", {"name": "T4"})
        append(vault, pid, "task.associated", {"task_id": "task_1"})
        append(
            vault,
            pid,
            "task.lifecycle.observed",
            {"task_id": "task_1", "state": "completed", "revision": 2},
        )
        service = ProjectStateService(vault, task_service=tasks)
        state = service.rebuild_project_state(pid)
        assert state.tasks["task_1"].state == "working"
        governance = GovernanceEngine()
        assert governance.evaluate_dod(state, ProjectPhase.CLOSED).passed is False
        assert "STALE_TASK_OBSERVATION" in state.health_flags


# ---------------------------------------------------------------------------
# T5 — forged decision view
# ---------------------------------------------------------------------------


class TestT5ForgedDecisionView:
    def test_live_decisionservice_wins_over_forged_view(self, tmp_path: Path) -> None:
        """T5: forged approved view vs live pending -> pending wins, approval unsatisfied."""
        vault = make_vault(tmp_path)
        pid = "prj_t5_decview"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_anchor", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        decisions.create_decision(
            decision_id="dec_1",
            task_id="task_anchor",
            title="Gate",
            requested_by="requester-1",
        )
        append(vault, pid, "project.created", {"name": "T5"})
        append(vault, pid, "decision.associated", {"decision_id": "dec_1"})

        forged = DecisionAuthorityView(
            decision_id="dec_1",
            status="approved",
            revision=1,
            digest=DecisionAuthorityView.compute_digest("dec_1", "approved"),
            source_identity="DecisionService:v1",
        )
        assert forged.digest == DecisionAuthorityView.compute_digest("dec_1", "approved")

        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        state = service.rebuild_project_state(pid)
        assert state.decisions["dec_1"].status == "pending"
        assert "dec_1" in state.required_approvals
        assert "dec_1" not in state.valid_decisions


# ---------------------------------------------------------------------------
# T6 — stale decision observation
# ---------------------------------------------------------------------------


class TestT6StaleDecisionObservation:
    def test_observed_approved_does_not_override_pending(self, tmp_path: Path) -> None:
        """T6: ledger says approved, DecisionService says pending -> pending wins."""
        vault = make_vault(tmp_path)
        pid = "prj_t6_staledec"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_anchor", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        decisions.create_decision(
            decision_id="dec_1",
            task_id="task_anchor",
            title="Gate",
            requested_by="requester-1",
        )
        append(vault, pid, "project.created", {"name": "T6"})
        append(vault, pid, "decision.associated", {"decision_id": "dec_1"})
        append(
            vault,
            pid,
            "decision.lifecycle.observed",
            {"decision_id": "dec_1", "status": "approved"},
        )
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        state = service.rebuild_project_state(pid)
        assert state.decisions["dec_1"].status == "pending"
        assert "STALE_DECISION_OBSERVATION" in state.health_flags
        # Transition requiring approval remains blocked.
        assert "dec_1" in state.required_approvals
        assert "dec_1" not in state.valid_decisions


# ---------------------------------------------------------------------------
# T7 — fake approval ref
# ---------------------------------------------------------------------------


class TestT7FakeApprovalRef:
    def test_unknown_approval_ref_requires_approval(self, tmp_path: Path) -> None:
        """T7: approval_ref='does_not_exist' with no canonical approval -> REQUIRE_APPROVAL."""
        vault = make_vault(tmp_path)
        pid = "prj_t7_approval"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_exec", state="ready")
        decisions = DecisionService(vault, task_service=tasks)
        append(vault, pid, "project.created", {"name": "T7"})
        attach_evidence(vault, pid, "evi_charter_01")
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "PLANNING", "owner": LEAD},
            actor=LEAD,
            evidence_refs=["evi_charter_01"],
        )
        assign_accountable(vault, pid)
        append(vault, pid, "task.associated", {"task_id": "task_exec"})
        attach_evidence(vault, pid, "evi_dor_checklist")
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "does_not_exist"},
            actor=LEAD,
            evidence_refs=["evi_dor_checklist"],
        )
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        with pytest.raises(IllegalStateTransitionError, match="MISSING_REQUIRED_APPROVAL"):
            service.rebuild_project_state(pid)


# ---------------------------------------------------------------------------
# T8 — self-declared admin override
# ---------------------------------------------------------------------------


class TestT8SelfDeclaredAdmin:
    def test_self_declared_role_denied(self, tmp_path: Path) -> None:
        """T8: role='admin' strings without canonical RACI/approval -> OVERRIDE DENIED."""
        vault = make_vault(tmp_path)
        pid = "prj_t8_override"
        append(vault, pid, "project.created", {"name": "T8"})
        append(
            vault,
            pid,
            "gate.overridden",
            {"gate": "dod_final_closing", "role": "admin", "reason": "override"},
            actor="user:attacker",
        )
        service = ProjectStateService(vault)
        state = service.rebuild_project_state(pid)
        assert "dod_final_closing" not in state.overridden_gates

    def test_canonical_override_accepted(self, tmp_path: Path) -> None:
        """Positive: canonical RACI actor with frozen metadata -> override accepted."""
        vault = make_vault(tmp_path)
        pid = "prj_t8_positive"
        append(vault, pid, "project.created", {"name": "T8pos"})
        assign_accountable(vault, pid, LEAD)
        append(
            vault,
            pid,
            "gate.overridden",
            {
                "gate": "review_gate_alpha",
                "overridden_by": LEAD,
                "reason": "documented schedule risk accepted",
                "approved_by": LEAD,
            },
            actor=LEAD,
        )
        service = ProjectStateService(vault)
        state = service.rebuild_project_state(pid)
        assert "review_gate_alpha" in state.overridden_gates


# ---------------------------------------------------------------------------
# T9 — fake evidence ref
# ---------------------------------------------------------------------------


class TestT9FakeEvidenceRef:
    def test_unknown_evidence_ref_requires_evidence(self, tmp_path: Path) -> None:
        """T9: evidence_refs=['evi_does_not_exist'] with no attachment -> REQUIRE_EVIDENCE."""
        vault = make_vault(tmp_path)
        pid = "prj_t9_evidence"
        append(vault, pid, "project.created", {"name": "T9"})
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "PLANNING", "owner": LEAD},
            actor=LEAD,
            evidence_refs=["evi_does_not_exist"],
        )
        service = ProjectStateService(vault)
        with pytest.raises(
            IllegalStateTransitionError, match="EVIDENCE_REF_NOT_CANONICALLY_ATTACHED"
        ):
            service.rebuild_project_state(pid)


# ---------------------------------------------------------------------------
# Fake task receipt (T20)
# ---------------------------------------------------------------------------


class TestFakeTaskReceipt:
    def test_fake_receipt_fails_dod_engine_level(self) -> None:
        """Random tcr_ receipt must not satisfy DoD; only verified receipts count."""
        from power_framework.core.governance_engine import AuthorityContext

        fake_receipt = "tcr_" + "0" * 64
        task_view = TaskAuthorityView(
            task_id="task_f",
            state="completed",
            revision=2,
            digest=TaskAuthorityView.compute_digest(
                "task_f", "completed", 2, receipt_ids=[fake_receipt]
            ),
            receipt_ids=[fake_receipt],
        )
        state = ProjectState(
            project_id="prj_t20_receipt",
            current_phase=ProjectPhase.EXECUTION,
            state_revision="0" * 64,
            tasks={"task_f": task_view},
        )
        governance = GovernanceEngine()
        authority_fake = AuthorityContext(
            attached_evidence=set(),
            approved_decision_ids=set(),
            verified_task_receipts=set(),
        )
        dod_fake = governance.evaluate_dod(
            state, ProjectPhase.CLOSING, event=None, authority=authority_fake
        )
        assert dod_fake.passed is False
        assert "DOD_MISSING_EVIDENCE" in dod_fake.reason_codes
        authority_real = AuthorityContext(
            attached_evidence=set(),
            approved_decision_ids=set(),
            verified_task_receipts={fake_receipt},
        )
        dod_real = governance.evaluate_dod(
            state, ProjectPhase.CLOSING, event=None, authority=authority_real
        )
        assert dod_real.passed is True

    def test_receipts_verified_through_taskstore(self, tmp_path: Path) -> None:
        """Verified set comes from TaskStore receipts; hacked fake IDs never enter it."""
        vault = make_vault(tmp_path)
        pid = "prj_t20_store"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_real", state="working")
        complete_task(tasks, vault, "task_real")
        fake_task = make_taskvault_task(tasks, "task_fake", state="working")
        fake_receipt = "tcr_" + "1" * 64
        hacked = fake_task.model_copy(
            update={
                "state": "completed",
                "revision": fake_task.revision + 1,
                "receipt_ids": [fake_receipt],
            }
        )
        tasks.store.save_task(hacked)
        append(vault, pid, "project.created", {"name": "T20"})
        append(vault, pid, "task.associated", {"task_id": "task_real"})
        append(vault, pid, "task.associated", {"task_id": "task_fake"})
        service = ProjectStateService(vault, task_service=tasks)
        canonical = service._read_canonical_events(pid)
        authority, _live_tasks, _live_decisions = service._assemble_authority(canonical)
        stored_real = tasks.get_task("task_real")
        assert stored_real is not None
        assert stored_real.receipt_ids
        for rid in stored_real.receipt_ids:
            assert rid in authority.verified_task_receipts
        assert fake_receipt not in authority.verified_task_receipts


# ---------------------------------------------------------------------------
# T10 — transition precondition coverage
# ---------------------------------------------------------------------------


def _authority(
    attached: set[str] | None = None,
    approved: set[str] | None = None,
    accountable: str | None = LEAD,
) -> AuthorityContext:
    raci: dict[str, list[str]] = {"Accountable": [accountable]} if accountable else {}
    return AuthorityContext(
        attached_evidence=set(attached or set()),
        approved_decision_ids=set(approved or set()),
        raci=raci,
        accountable_actor=accountable,
        verified_task_receipts=set(),
    )


def _terminal_task_view(task_id: str) -> TaskAuthorityView:
    return TaskAuthorityView(
        task_id=task_id,
        state="completed",
        revision=2,
        digest=TaskAuthorityView.compute_digest(
            task_id, "completed", 2, receipt_ids=["tcr_" + "a" * 64]
        ),
        receipt_ids=["tcr_" + "a" * 64],
    )


def _approved_decision_view(decision_id: str) -> DecisionAuthorityView:
    return DecisionAuthorityView(
        decision_id=decision_id,
        status="approved",
        revision=1,
        digest=DecisionAuthorityView.compute_digest(decision_id, "approved"),
        receipt_id="dcr_" + "b" * 64,
    )


def _pending_decision_view(decision_id: str) -> DecisionAuthorityView:
    return DecisionAuthorityView(
        decision_id=decision_id,
        status="pending",
        revision=1,
        digest=DecisionAuthorityView.compute_digest(decision_id, "pending"),
    )


def _passing_state_for(
    from_phase: ProjectPhase,
    with_tasks: bool = True,
    with_decisions: str = "approved",
) -> ProjectState:
    tasks = {"task_a": _terminal_task_view("task_a")} if with_tasks else {}
    decisions: dict[str, DecisionAuthorityView] = {}
    if with_decisions == "approved":
        decisions = {"dec_ok_1": _approved_decision_view("dec_ok_1")}
    elif with_decisions == "pending":
        decisions = {"dec_ok_1": _pending_decision_view("dec_ok_1")}
    return ProjectState(
        project_id="prj_matrix_01",
        current_phase=from_phase,
        state_revision="0" * 64,
        tasks=tasks,
        decisions=decisions,
    )


def _transition_event(
    from_phase: ProjectPhase,
    to_phase: ProjectPhase,
    evidence: list[str] | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> ProjectEvent:
    payload: dict[str, Any] = {"target_phase": to_phase.value}
    payload.update(extra_payload or {})
    raw: dict[str, Any] = {
        "event_id": "evt_matrix_0001",
        "schema_version": "power.project-event.v1",
        "project_id": "prj_matrix_01",
        "sequence": 1,
        "timestamp": "2026-09-05T02:00:01Z",
        "actor": LEAD,
        "source": "cli",
        "session_id": None,
        "event_type": "project.reopened"
        if from_phase == ProjectPhase.CLOSED
        else "project.phase.changed",
        "payload": payload,
        "payload_digest": "0" * 64,
        "prev_event_hash": "",
        "artifact_refs": [],
        "evidence_refs": evidence or [],
        "correlation_id": None,
        "causation_id": None,
        "idempotency_key": None,
        "event_hash": "0" * 64,
    }
    event = ProjectEvent(**raw)
    event.payload_digest = compute_payload_digest(event.payload)
    event.event_hash = compute_event_hash(event.model_dump())
    return event


def _allow_payload(from_phase: ProjectPhase, to_phase: ProjectPhase) -> dict[str, Any]:
    """Payload satisfying all reason/owner/approval needs for the positive case."""
    spec = LEGAL_TRANSITIONS[(from_phase, to_phase)]
    payload: dict[str, Any] = {
        "reason": "documented governance rationale",
        "owner": LEAD,
        "approval_ref": "dec_ok_1",
        "accountable_approval": LEAD,
        "approved_by": LEAD,
    }
    if "accountable_approval" not in spec.preconditions:
        payload.pop("accountable_approval")
    return payload


class TestT10PreconditionCoverage:
    def test_every_precondition_token_maps_to_evaluator(self) -> None:
        """Contract: every declared token in all 17 transitions has an evaluator; unknown fails closed."""
        engine = GovernanceEngine()
        state = _passing_state_for(ProjectPhase.DISCOVERY)
        event = _transition_event(
            ProjectPhase.DISCOVERY, ProjectPhase.PLANNING, evidence=["evi_charter_01"]
        )
        tokens: set[str] = set()
        for spec in LEGAL_TRANSITIONS.values():
            tokens.update(spec.preconditions)
        assert len(tokens) >= 10
        for token in sorted(tokens):
            result = engine._evaluate_precondition(
                token, state, event, _authority({"evi_charter_01"}, {"dec_ok_1"})
            )
            assert isinstance(result, bool)
        assert (
            engine._evaluate_precondition(
                "nonexistent_precondition_xyz",
                state,
                event,
                _authority({"evi_charter_01"}, {"dec_ok_1"}),
            )
            is False
        )

    @pytest.mark.parametrize(
        ("from_p", "to_p"),
        sorted(
            [(f.value, t.value) for (f, t) in LEGAL_TRANSITIONS],
        ),
    )
    def test_all_17_transitions_allow_on_positive_case(self, from_p: str, to_p: str) -> None:
        """T10 positive: every legal transition ALLOWs when prerequisites hold."""
        engine = GovernanceEngine()
        from_phase = ProjectPhase(from_p)
        to_phase = ProjectPhase(to_p)
        with_tasks = to_p not in ("PLANNING", "DISCOVERY") or from_p in (
            "PLANNING",
            "EXECUTION",
            "MONITORING",
            "CLOSING",
            "CLOSED",
        )
        state = _passing_state_for(from_phase, with_tasks=True, with_decisions="approved")
        if not with_tasks:
            state = _passing_state_for(from_phase, with_tasks=False, with_decisions="none")
            state.decisions = {}
        evidence = ["evi_charter_01", "evi_gate_01"]
        authority = _authority(set(evidence), {"dec_ok_1"})
        event = _transition_event(
            from_phase,
            to_phase,
            evidence=evidence,
            extra_payload=_allow_payload(from_phase, to_phase),
        )
        result = engine.evaluate_transition(state, to_phase, event, authority)
        assert result.decision == GovernanceDecision.ALLOW, (
            f"{from_p}->{to_p}: {result.reason_codes}"
        )

    def test_discovery_to_planning_requires_owner_and_charter(self, tmp_path: Path) -> None:
        """T10 vault-level: DISCOVERY->PLANNING without owner/charter fails; with them passes."""
        vault = make_vault(tmp_path)
        pid = "prj_t10_disc"
        append(vault, pid, "project.created", {"name": "T10"})
        attach_evidence(vault, pid, "evi_misc_01")
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "PLANNING"},
            actor=LEAD,
            evidence_refs=["evi_misc_01"],
        )
        service = ProjectStateService(vault)
        with pytest.raises(IllegalStateTransitionError, match="PRECONDITION_FAILED"):
            service.rebuild_project_state(pid)

    def test_planning_to_execution_requires_accountable(self, tmp_path: Path) -> None:
        """T10 vault-level: PLANNING->EXECUTION without RACI Accountable fails."""
        vault = make_vault(tmp_path)
        pid = "prj_t10_exec"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_e1", state="ready")
        decisions = DecisionService(vault, task_service=tasks)
        append(vault, pid, "project.created", {"name": "T10"})
        attach_evidence(vault, pid, "evi_charter_01")
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "PLANNING", "owner": LEAD},
            actor=LEAD,
            evidence_refs=["evi_charter_01"],
        )
        append(vault, pid, "task.associated", {"task_id": "task_e1"})
        make_taskvault_task(tasks, "task_anchor", state="working")
        make_approved_decision(decisions, "dec_exec_ok", "task_anchor")
        append(vault, pid, "decision.associated", {"decision_id": "dec_exec_ok"})
        attach_evidence(vault, pid, "evi_dor_checklist")
        append(
            vault,
            pid,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_exec_ok"},
            actor=LEAD,
            evidence_refs=["evi_dor_checklist"],
        )
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        with pytest.raises(
            IllegalStateTransitionError, match="PRECONDITION_FAILED:raci_accountable_assigned"
        ):
            service.rebuild_project_state(pid)

    def test_closed_to_planning_requires_accountable_approval(self, tmp_path: Path) -> None:
        """T10 vault-level: CLOSED->PLANNING without real accountable approval fails."""
        vault = make_vault(tmp_path)
        pid = "prj_t10_reopen"
        _build_closed_project(vault, pid)
        attach_evidence(vault, pid, "evi_reopen_request")
        append(
            vault,
            pid,
            "project.reopened",
            {
                "target_phase": "PLANNING",
                "reason": "phase 2 expansion",
                "accountable_approval": "user:impostor",
            },
            actor="user:impostor",
            evidence_refs=["evi_reopen_request"],
        )
        service = ProjectStateService(vault)
        with pytest.raises(
            IllegalStateTransitionError,
            match=r"MISSING_REQUIRED_APPROVAL|PRECONDITION_FAILED",
        ):
            service.rebuild_project_state(pid)


def _build_closed_project(vault: Path, pid: str) -> ProjectStateService:
    """Positive-control builder: canonical ledger + live stores through CLOSED."""
    tasks = TaskService(vault)
    decisions = DecisionService(vault, task_service=tasks)
    make_taskvault_task(tasks, "task_alpha", state="backlog")
    make_taskvault_task(tasks, "task_anchor", state="working")
    append(vault, pid, "project.created", {"name": "closed-positive"})
    attach_evidence(vault, pid, "evi_charter_01")
    append(
        vault,
        pid,
        "project.phase.changed",
        {"target_phase": "PLANNING", "owner": LEAD},
        actor=LEAD,
        evidence_refs=["evi_charter_01"],
    )
    assign_accountable(vault, pid, LEAD)
    append(vault, pid, "task.associated", {"task_id": "task_alpha"})
    append(vault, pid, "task.associated", {"task_id": "task_anchor"})
    make_approved_decision(decisions, "dec_exec_gate", "task_anchor")
    append(vault, pid, "decision.associated", {"decision_id": "dec_exec_gate"})
    attach_evidence(vault, pid, "evi_dor_checklist")
    append(
        vault,
        pid,
        "project.phase.changed",
        {"target_phase": "EXECUTION", "approval_ref": "dec_exec_gate"},
        actor=LEAD,
        evidence_refs=["evi_dor_checklist"],
    )
    complete_task(tasks, vault, "task_alpha")
    complete_task(tasks, vault, "task_anchor")
    attach_evidence(vault, pid, "evi_dod_receipt")
    append(
        vault,
        pid,
        "project.phase.changed",
        {"target_phase": "CLOSING"},
        actor=LEAD,
        evidence_refs=["evi_dod_receipt"],
    )
    # Anchor/base tasks are completed; anchor revision moved, so bind close
    # decision to a fresh completed task revision anchor.
    make_approved_decision(decisions, "dec_close", "task_anchor")
    append(vault, pid, "decision.associated", {"decision_id": "dec_close"})
    attach_evidence(vault, pid, "evi_close_receipt")
    append(
        vault,
        pid,
        "project.phase.changed",
        {"target_phase": "CLOSED", "approval_ref": "dec_close"},
        actor=LEAD,
        evidence_refs=["evi_close_receipt"],
    )
    return ProjectStateService(vault, task_service=tasks, decision_service=decisions)


# ---------------------------------------------------------------------------
# T11 — self-consistent forged snapshot
# ---------------------------------------------------------------------------


class TestT11ForgedSnapshot:
    def test_forged_snapshot_rejected_authoritative(self, tmp_path: Path) -> None:
        """T11: internally consistent snapshot disagreeing with ledger -> REJECT."""
        vault = make_vault(tmp_path)
        pid = "prj_t11_snap"
        service = ProjectStateService(vault)
        append(vault, pid, "project.created", {"name": "T11"})
        genuine = service.rebuild_project_state(pid)
        assert genuine.current_phase == ProjectPhase.DISCOVERY

        forged_state = ProjectState(
            project_id=pid,
            current_phase=ProjectPhase.CLOSED,
            state_revision="0" * 64,
            last_event_sequence=7,
            last_event_hash="a" * 64,
        )
        forged_state.state_revision = "0" * 64
        from power_framework.core.state_models import compute_state_revision

        forged_state.state_revision = compute_state_revision(forged_state.model_dump())
        forged_snapshot = ProjectStateSnapshot.create(forged_state)
        assert forged_snapshot.verify_integrity() is True
        with pytest.raises(SnapshotIntegrityError, match="REJECTED"):
            service.restore_snapshot_authoritative(forged_snapshot)


# ---------------------------------------------------------------------------
# T12 — stale federated snapshot
# ---------------------------------------------------------------------------


class TestT12StaleFederatedSnapshot:
    def test_live_authorities_re_resolved_on_restore(self, tmp_path: Path) -> None:
        """T12: TaskStore advances after snapshot; authoritative restore sees completed."""
        vault = make_vault(tmp_path)
        pid = "prj_t12_stale"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_x", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        append(vault, pid, "project.created", {"name": "T12"})
        append(vault, pid, "task.associated", {"task_id": "task_x"})
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        state_before = service.rebuild_project_state(pid)
        assert state_before.tasks["task_x"].state == "working"
        snapshot = ProjectStateReducer().create_snapshot(state_before)

        complete_task(tasks, vault, "task_x")
        restored = service.restore_snapshot_authoritative(snapshot)
        assert restored.tasks["task_x"].state == "completed"

    def test_snapshot_behind_head_replays_tail_with_live_authority(self, tmp_path: Path) -> None:
        """Snapshot at K + canonical tail K+1..N restores with live TaskStore truth."""
        vault = make_vault(tmp_path)
        pid = "prj_t12_tail"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_x", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        append(vault, pid, "project.created", {"name": "T12t"})
        append(vault, pid, "task.associated", {"task_id": "task_x"})
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        state_at_k = service.rebuild_project_state(pid)
        snapshot = ProjectStateReducer().create_snapshot(state_at_k)
        # Canonical tail after the snapshot + live federation advance.
        attach_evidence(vault, pid, "evi_tail_01")
        complete_task(tasks, vault, "task_x")
        restored = service.restore_snapshot_authoritative(snapshot)
        assert restored.tasks["task_x"].state == "completed"
        assert "evi_tail_01" in restored.attached_evidence
        assert restored.last_event_sequence == state_at_k.last_event_sequence + 1

    def test_live_decision_re_resolved_on_restore(self, tmp_path: Path) -> None:
        """T12 analogue: DecisionService advances after snapshot; restore sees approved."""
        vault = make_vault(tmp_path)
        pid = "prj_t12_dec"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_anchor", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        decisions.create_decision(
            decision_id="dec_y",
            task_id="task_anchor",
            title="Gate Y",
            requested_by="requester-1",
        )
        append(vault, pid, "project.created", {"name": "T12d"})
        append(vault, pid, "decision.associated", {"decision_id": "dec_y"})
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        state_before = service.rebuild_project_state(pid)
        assert state_before.decisions["dec_y"].status == "pending"
        snapshot = ProjectStateReducer().create_snapshot(state_before)

        decisions.resolve_decision("dec_y", action="approve", actor="operator-1", authority="apply")
        restored = service.restore_snapshot_authoritative(snapshot)
        assert restored.decisions["dec_y"].status == "approved"


# ---------------------------------------------------------------------------
# Ruleset binding + valid_decisions semantics + payload digest
# ---------------------------------------------------------------------------


class TestRulesetBinding:
    def test_rules_digest_stable_and_bound(self, tmp_path: Path) -> None:
        """Ruleset digest binds version->manifest; states carry it; tamper detectable."""
        import hashlib
        import json

        digest = compute_rules_digest()
        assert digest == compute_rules_digest()
        assert len(digest) == 64

        manifest_path = (
            Path(__file__).resolve().parent.parent
            / "artifacts"
            / "project-state"
            / "phase-4"
            / "governance_rules_v1.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["rules_version"] == "1.0.0"
        code_names = sorted(
            f"{s.from_phase.value}->{s.to_phase.value}:{s.name}" for s in LEGAL_TRANSITIONS.values()
        )
        file_names = sorted(
            f"{t['from_phase']}->{t['to_phase']}:{t['name']}"
            for t in manifest["fsm"]["transitions"]
        )
        assert code_names == file_names

        tampered = hashlib.sha256((digest + "x").encode()).hexdigest()
        assert tampered != digest

        vault = make_vault(tmp_path)
        pid = "prj_rules_bind"
        append(vault, pid, "project.created", {"name": "R"})
        state = ProjectStateService(vault).rebuild_project_state(pid)
        assert state.rules_digest == digest

    def test_unknown_precondition_fails_closed(self) -> None:
        engine = GovernanceEngine()
        state = _passing_state_for(ProjectPhase.DISCOVERY)
        event = _transition_event(ProjectPhase.DISCOVERY, ProjectPhase.PLANNING, evidence=["evi_x"])
        assert (
            engine._evaluate_precondition(
                "future_phase5_token", state, event, _authority({"evi_x"})
            )
            is False
        )


class TestValidDecisionsSemantics:
    def test_only_approved_are_valid(self, tmp_path: Path) -> None:
        """valid_decisions = approved; required_approvals = pending (synchronized)."""
        vault = make_vault(tmp_path)
        pid = "prj_validdec"
        tasks = TaskService(vault)
        make_taskvault_task(tasks, "task_anchor", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        decisions.create_decision(
            decision_id="dec_pending_1",
            task_id="task_anchor",
            title="Pending",
            requested_by="requester-1",
        )
        make_approved_decision(decisions, "dec_approved_1", "task_anchor")
        append(vault, pid, "project.created", {"name": "V"})
        append(vault, pid, "decision.associated", {"decision_id": "dec_pending_1"})
        append(vault, pid, "decision.associated", {"decision_id": "dec_approved_1"})
        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        state = service.rebuild_project_state(pid)
        assert state.valid_decisions == ["dec_approved_1"]
        assert state.required_approvals == ["dec_pending_1"]


class TestPayloadDigestDefense:
    def test_tampered_payload_digest_rejected(self, tmp_path: Path) -> None:
        """Reducer verifies payload_digest explicitly, not only the outer hash."""
        vault = make_vault(tmp_path)
        pid = "prj_digest_def"
        append(vault, pid, "project.created", {"name": "D"})
        store = ProjectEventStore(pid, vault)
        genuine = list(store.replay())
        tampered = genuine[0].model_copy(
            update={"payload": {"name": "tampered"}, "payload_digest": "0" * 64}
        )
        # Recompute outer hash over the tampered envelope so only the
        # payload-digest check can catch it.
        tampered.event_hash = compute_event_hash(tampered.model_dump())
        with pytest.raises(Exception, match="payload digest mismatch"):
            ProjectStateReducer().reduce([tampered])


# ---------------------------------------------------------------------------
# Positive control — real authoritative end-to-end (T30)
# ---------------------------------------------------------------------------


class TestPositiveAuthoritativeE2E:
    def test_full_lifecycle_authoritative(self, tmp_path: Path) -> None:
        """Positive: canonical rebuild -> expected state, gates PASS, DoR/DoD PASS."""
        vault = make_vault(tmp_path)
        pid = "prj_positive_e2e"
        service = _build_closed_project(vault, pid)
        state = service.rebuild_project_state(pid)

        assert state.current_phase == ProjectPhase.CLOSED
        assert state.tasks["task_alpha"].state == "completed"
        assert state.tasks["task_anchor"].state == "completed"
        assert state.decisions["dec_exec_gate"].status == "approved"
        assert state.decisions["dec_close"].status == "approved"
        assert state.valid_decisions == ["dec_close", "dec_exec_gate"]
        assert state.required_approvals == []
        assert state.raci.get("Accountable") == [LEAD]
        assert "evi_charter_01" in state.attached_evidence

        governance = GovernanceEngine()
        assert governance.evaluate_dor(state, ProjectPhase.EXECUTION).passed is True
        assert governance.evaluate_dod(state, ProjectPhase.CLOSED).passed is True

        # Explainability traces canonical authorities.
        explanation = service.reducer.explain(state, "valid_decisions")
        assert "DecisionService:v1" in explanation.authority_references
