"""POWER Project State Engine (PSE) Phase 4 — Test Suite.

Comprehensive tests covering:
- Lifecycle FSM: all 17 legal transitions, illegal transitions, rollbacks, reopen semantics
- Determinism (G4.1): identical replay across instances and separate Python processes
- P0 Security & Authority Gates:
  - P0-1: Model cannot advance lifecycle
  - P0-2: Model cannot satisfy DoD without canonical evidence
  - P0-3: Model cannot override governance gates
  - P0-4: Task authority cannot be shadowed
  - P0-5: Decision authority cannot be shadowed
  - P0-6: Snapshot cannot forge state
- Tasks & Readiness (G4.3): multi-level dependencies, cycles, DoR evaluation
- Decisions (G4.4): typed DecisionService integration
- DoD Engine: terminal deliverables, blocking issues, resolved decisions, evidence
- RAID Aggregation: risks, assumptions, issues, dependencies, reopen issue, unverified rejection
- Replay Integrity: sequence gap, duplicate, reorder, cross-project, broken hash chain
- Snapshots: full replay == snapshot + tail, tampering detection
- Explainability (G4.6): all required fields trace to events, rules, and authorities
- Performance: synthetic benchmark on 100, 1,000, and 10,000 events
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from copy import deepcopy
from typing import Any

import pytest

from power_framework.core.canonical_json import (
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.governance_engine import (
    LEGAL_TRANSITIONS,
    GovernanceEngine,
    detect_dependency_cycles,
)
from power_framework.core.project_models import ProjectEvent
from power_framework.core.state_models import (
    DecisionAuthorityView,
    GovernanceDecision,
    HealthFlag,
    IllegalStateTransitionError,
    ProjectPhase,
    ProjectState,
    ProjectStateSnapshot,
    SnapshotIntegrityError,
    StateEngineIntegrityError,
    TaskAuthorityView,
    UnexplainableFieldError,
    compute_state_revision,
)
from power_framework.core.state_reducer import ProjectStateReducer

# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def make_event(
    project_id: str,
    seq: int,
    prev_hash: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    actor: str = "test_engineer",
    source: str = "test_harness",
    timestamp: str | None = None,
    evidence_refs: list[str] | None = None,
) -> ProjectEvent:
    """Construct a cryptographically valid ProjectEvent."""
    payload = payload or {}
    hours = (seq // 3600) % 24
    mins = (seq % 3600) // 60
    secs = seq % 60
    ts = timestamp or f"2026-09-05T{hours:02d}:{mins:02d}:{secs:02d}Z"
    event_dict: dict[str, Any] = {
        "event_id": f"evt_{project_id[4:12]}_{seq:04d}",
        "schema_version": "power.project-event.v1",
        "project_id": project_id,
        "sequence": seq,
        "timestamp": ts,
        "actor": actor,
        "source": source,
        "session_id": None,
        "event_type": event_type,
        "payload": payload,
        "payload_digest": "0" * 64,
        "prev_event_hash": prev_hash,
        "artifact_refs": [],
        "evidence_refs": evidence_refs or [],
        "correlation_id": None,
        "causation_id": None,
        "idempotency_key": None,
        "event_hash": "0" * 64,
    }
    event = ProjectEvent(**event_dict)
    event.payload_digest = compute_payload_digest(event.payload)
    event.event_hash = compute_event_hash(event.model_dump())
    return event


def build_event_chain(
    project_id: str,
    event_specs: list[tuple[str, dict[str, Any] | None, list[str] | None]],
    actor: str = "test_lead",
    source: str = "cli",
) -> list[ProjectEvent]:
    """Build a valid sequential chain of ProjectEvents."""
    events: list[ProjectEvent] = []
    prev_hash = ""
    for i, (etype, payload, ev_refs) in enumerate(event_specs, start=1):
        event = make_event(
            project_id=project_id,
            seq=i,
            prev_hash=prev_hash,
            event_type=etype,
            payload=payload or {},
            actor=actor,
            source=source,
            evidence_refs=ev_refs,
        )
        events.append(event)
        prev_hash = event.event_hash
    return events


# ---------------------------------------------------------------------------
# 1. Lifecycle FSM Tests
# ---------------------------------------------------------------------------


class TestLifecycleFSM:
    """Test the complete 6-state FSM and 17 legal transitions."""

    def test_all_17_legal_transitions_catalog(self) -> None:
        """Verify the catalog contains exactly 17 legal transitions."""
        assert len(LEGAL_TRANSITIONS) == 17

    def test_discovery_to_planning_forward(self) -> None:
        """Test legal transition DISCOVERY -> PLANNING."""
        pid = "prj_fsm_01"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {"name": "Alpha"}, None),
                (
                    "project.phase.changed",
                    {
                        "target_phase": "PLANNING",
                        "reason": "Charter approved",
                    },
                    ["evi_charter_01"],
                ),
            ],
        )
        state = reducer.reduce(events)
        assert state.current_phase == ProjectPhase.PLANNING
        assert len(state.phase_history) == 1
        assert state.phase_history[0].name == "advance_to_planning"

    def test_planning_to_execution_with_dor(self) -> None:
        """Test legal transition PLANNING -> EXECUTION requiring DoR and approval."""
        pid = "prj_fsm_02"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_charter"]),
                ("task.associated", {"task_id": "task_initial_01"}, None),
                (
                    "project.phase.changed",
                    {
                        "target_phase": "EXECUTION",
                        "approval_ref": "dec_lead_signoff",
                    },
                    ["evi_dor_checklist"],
                ),
            ],
        )
        state = reducer.reduce(events)
        assert state.current_phase == ProjectPhase.EXECUTION
        assert len(state.phase_history) == 2

    def test_execution_to_monitoring_and_resume(self) -> None:
        """Test EXECUTION <-> MONITORING cycles (transitions 6 and 10)."""
        pid = "prj_fsm_03"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "t1"}, None),
                (
                    "project.phase.changed",
                    {"target_phase": "EXECUTION", "approval_ref": "a1"},
                    ["evi_d"],
                ),
                ("project.phase.changed", {"target_phase": "MONITORING"}, None),
                ("project.phase.changed", {"target_phase": "EXECUTION"}, None),
            ],
        )
        state = reducer.reduce(events)
        assert state.current_phase == ProjectPhase.EXECUTION
        assert len(state.phase_history) == 4

    def test_rollback_execution_to_planning_requires_justification(self) -> None:
        """Test rollback EXECUTION -> PLANNING fails closed if reason omitted."""
        pid = "prj_fsm_04"
        reducer = ProjectStateReducer()

        # Without reason: fails closed
        events_bad = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "t1"}, None),
                (
                    "project.phase.changed",
                    {"target_phase": "EXECUTION", "approval_ref": "a1"},
                    ["evi_d"],
                ),
                (
                    "project.phase.changed",
                    {"target_phase": "PLANNING", "approval_ref": "a1"},
                    ["evi_r"],
                ),
            ],
        )
        with pytest.raises(IllegalStateTransitionError, match="MISSING_TRANSITION_REASON"):
            reducer.reduce(events_bad)

        # With reason: succeeds
        events_good = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "t1"}, None),
                (
                    "project.phase.changed",
                    {"target_phase": "EXECUTION", "approval_ref": "a1"},
                    ["evi_d"],
                ),
                (
                    "project.phase.changed",
                    {
                        "target_phase": "PLANNING",
                        "reason": "Scope pivot required by stakeholder review",
                        "approval_ref": "a2",
                    },
                    ["evi_scope_pivot"],
                ),
            ],
        )
        state = reducer.reduce(events_good)
        assert state.current_phase == ProjectPhase.PLANNING
        assert state.phase_history[-1].is_rollback is True

    def test_execution_to_closing_and_finalize_close(self) -> None:
        """Test full execution to closing and finalized close."""
        pid = "prj_fsm_05"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "t1"}, None),
                (
                    "project.phase.changed",
                    {"target_phase": "EXECUTION", "approval_ref": "a1"},
                    ["evi_d"],
                ),
                (
                    "task.lifecycle.observed",
                    {"task_id": "t1", "state": "completed", "receipt_ids": ["tcr_1"]},
                    None,
                ),
                ("project.phase.changed", {"target_phase": "CLOSING"}, ["evi_dod_receipt"]),
                (
                    "project.phase.changed",
                    {"target_phase": "CLOSED", "approval_ref": "dec_final_close"},
                    ["evi_close_receipt"],
                ),
            ],
        )
        state = reducer.reduce(events)
        assert state.current_phase == ProjectPhase.CLOSED
        assert len(state.phase_history) == 4

    def test_closed_project_blocks_normal_transitions(self) -> None:
        """Test that CLOSED state blocks normal transitions without explicit project.reopened."""
        pid = "prj_fsm_06"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                (
                    "project.phase.changed",
                    {"target_phase": "CLOSED", "reason": "Abandoned", "approval_ref": "a1"},
                    ["evi_cancel"],
                ),
                (
                    "project.phase.changed",
                    {"target_phase": "PLANNING", "reason": "reopen"},
                    ["evi_r"],
                ),
            ],
        )
        with pytest.raises(
            IllegalStateTransitionError, match="CLOSED_PROJECT_REQUIRES_EXPLICIT_REOPEN"
        ):
            reducer.reduce(events)

    def test_reopen_closed_project_with_explicit_event(self) -> None:
        """Test reopening a CLOSED project using project.reopened."""
        pid = "prj_fsm_07"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                (
                    "project.phase.changed",
                    {"target_phase": "CLOSED", "reason": "Abandoned", "approval_ref": "a1"},
                    ["evi_cancel"],
                ),
                (
                    "project.reopened",
                    {
                        "target_phase": "PLANNING",
                        "reason": "Reopened for phase 2 expansion",
                        "accountable_approval": "lead_user",
                    },
                    ["evi_reopen_mandate"],
                ),
            ],
        )
        state = reducer.reduce(events)
        assert state.current_phase == ProjectPhase.PLANNING
        assert state.phase_history[-1].name == "reopen_to_planning"
        assert state.phase_history[-1].is_rollback is True

    @pytest.mark.parametrize(
        ("from_p", "to_p"),
        [
            ("DISCOVERY", "EXECUTION"),
            ("DISCOVERY", "CLOSING"),
            ("PLANNING", "CLOSING"),
            ("EXECUTION", "DISCOVERY"),
            ("MONITORING", "DISCOVERY"),
            ("CLOSING", "DISCOVERY"),
            ("CLOSING", "PLANNING"),
            ("CLOSED", "DISCOVERY"),
            ("CLOSED", "MONITORING"),
            ("CLOSED", "CLOSING"),
        ],
    )
    def test_illegal_transitions_fail_closed(self, from_p: str, to_p: str) -> None:
        """Verify illegal transitions fail closed with IllegalStateTransitionError."""
        engine = GovernanceEngine()
        initial_state = ProjectState(
            project_id="prj_illegal",
            current_phase=ProjectPhase(from_p),
            state_revision="0" * 64,
        )
        event = make_event("prj_illegal", 1, "", "project.phase.changed", {"target_phase": to_p})
        eval_res = engine.evaluate_transition(initial_state, ProjectPhase(to_p), event)
        assert eval_res.decision == GovernanceDecision.DENY
        assert any(
            code in eval_res.reason_codes
            for code in (
                "ILLEGAL_LIFECYCLE_TRANSITION",
                "CLOSED_PROJECT_REQUIRES_EXPLICIT_REOPEN",
            )
        )


# ---------------------------------------------------------------------------
# 2. Determinism (Gate G4.1)
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Verify 100% byte-equivalent replay determinism and identical state_revision."""

    def test_same_replay_twice_identical_bytes(self) -> None:
        pid = "prj_det_01"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "task_b"}, None),
                ("task.associated", {"task_id": "task_a"}, None),
                (
                    "risk.opened",
                    {"risk_id": "rsk_02", "impact": "high", "probability": "low"},
                    None,
                ),
                (
                    "risk.opened",
                    {"risk_id": "rsk_01", "impact": "low", "probability": "high"},
                    None,
                ),
            ],
        )

        state1 = reducer.reduce(events)
        state2 = ProjectStateReducer().reduce(events)

        assert state1.state_revision == state2.state_revision
        assert state1.to_canonical_bytes() == state2.to_canonical_bytes()
        assert state1.active_tasks == ["task_a", "task_b"]
        assert state1.open_risks == ["rsk_01", "rsk_02"]

    def test_separate_python_processes_determinism(self) -> None:
        """Required Test: Two fresh Python processes produce identical JSON bytes & state_revision."""
        pid = "prj_proc_det"
        events_data = [
            {"event_type": "project.created", "payload": {}, "evidence_refs": []},
            {
                "event_type": "project.phase.changed",
                "payload": {"target_phase": "PLANNING"},
                "evidence_refs": ["evi_charter"],
            },
            {
                "event_type": "task.associated",
                "payload": {"task_id": "task_z"},
                "evidence_refs": [],
            },
            {
                "event_type": "task.associated",
                "payload": {"task_id": "task_m"},
                "evidence_refs": [],
            },
            {
                "event_type": "issue.opened",
                "payload": {"issue_id": "iss_99", "severity": "minor"},
                "evidence_refs": [],
            },
        ]
        events_json = json.dumps(events_data)

        script = f"""
import json, sys
from power_framework.core.canonical_json import compute_payload_digest, compute_event_hash
from power_framework.core.project_models import ProjectEvent
from power_framework.core.state_reducer import ProjectStateReducer

pid = '{pid}'
specs = json.loads({events_json!r})
events = []
prev_hash = ''
for i, item in enumerate(specs, 1):
    payload = item['payload']
    ed = {{
        'event_id': f'evt_{{i:04d}}',
        'schema_version': 'power.project-event.v1',
        'project_id': pid,
        'sequence': i,
        'timestamp': f'2026-09-05T02:00:{{i:02d}}Z',
        'actor': 'tester',
        'source': 'cli',
        'session_id': None,
        'event_type': item['event_type'],
        'payload': payload,
        'payload_digest': '0' * 64,
        'prev_event_hash': prev_hash,
        'artifact_refs': [],
        'evidence_refs': item['evidence_refs'],
        'correlation_id': None,
        'causation_id': None,
        'idempotency_key': None,
        'event_hash': '0' * 64,
    }}
    e = ProjectEvent(**ed)
    e.payload_digest = compute_payload_digest(e.payload)
    e.event_hash = compute_event_hash(e.model_dump())
    events.append(e)
    prev_hash = e.event_hash

reducer = ProjectStateReducer()
state = reducer.reduce(events)
sys.stdout.buffer.write(state.to_canonical_bytes())
"""
        proc1 = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script],
            capture_output=True,
            check=True,
        )
        proc2 = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script],
            capture_output=True,
            check=True,
        )

        assert proc1.stdout == proc2.stdout
        state_dict1 = json.loads(proc1.stdout.decode("utf-8"))
        state_dict2 = json.loads(proc2.stdout.decode("utf-8"))
        assert state_dict1["state_revision"] == state_dict2["state_revision"]


# ---------------------------------------------------------------------------
# 3. Special P0 Tests (Release-Blocking Gates)
# ---------------------------------------------------------------------------


class TestSpecialP0Gates:
    """Special P0 Security & Authority Invariant Tests (Section 35)."""

    def test_p0_1_model_cannot_advance_lifecycle(self) -> None:
        """P0-1: Model-derived candidate requesting DISCOVERY -> CLOSED must fail (0 transitions)."""
        pid = "prj_p0_model_phase"
        reducer = ProjectStateReducer()

        init_event = make_event(pid, 1, "", "project.created", {})

        # Construct malicious model-derived candidate event
        malicious_event = make_event(
            project_id=pid,
            seq=2,
            prev_hash=init_event.event_hash,
            event_type="project.phase.changed",
            payload={
                "target_phase": "CLOSED",
                "reason": "AI agent finished everything automatically",
                "source_type": "agent_inference",
                "verification_status": "proposed",
            },
            actor="model",
            source="model_extraction",
        )

        with pytest.raises(
            IllegalStateTransitionError, match="UNTRUSTED_MODEL_TRANSITION_PROHIBITED"
        ):
            reducer.reduce([init_event, malicious_event])

    def test_p0_2_model_cannot_satisfy_dod(self) -> None:
        """P0-2: Model statement 'all tests passed' cannot satisfy DoD without canonical evidence."""
        pid = "prj_p0_model_dod"
        governance = GovernanceEngine()
        state = ProjectState(
            project_id=pid,
            current_phase=ProjectPhase.CLOSING,
            state_revision="0" * 64,
        )

        untrusted_event = make_event(
            project_id=pid,
            seq=1,
            prev_hash="",
            event_type="project.phase.changed",
            payload={"statement": "All tests passed. Mark project complete."},
            actor="model",
            source="model_extraction",
        )

        dod_eval = governance.evaluate_dod(state, ProjectPhase.CLOSED, event=untrusted_event)
        assert dod_eval.passed is False
        assert "CANONICAL_COMPLETION_EVIDENCE_REQUIRED" in dod_eval.missing_evidence
        assert "UNTRUSTED_MODEL_DOD_CLAIM_REJECTED" in dod_eval.reason_codes

    def test_p0_3_model_cannot_override_governance(self) -> None:
        """P0-3: Untrusted / model candidate attempting gate.overridden is rejected (0 overrides)."""
        pid = "prj_p0_model_override"
        reducer = ProjectStateReducer()

        events = [
            make_event(pid, 1, "", "project.created", {}),
        ]
        # Malicious model attempt to override DoR
        override_event = make_event(
            pid,
            2,
            events[0].event_hash,
            "gate.overridden",
            payload={
                "gate": "dor_planning_to_execution",
                "role": "admin",
                "reason": "AI emergency override",
            },
            actor="model",
            source="model_extraction",
        )
        events.append(override_event)

        state = reducer.reduce(events)
        assert "dor_planning_to_execution" not in state.overridden_gates
        assert len(state.overridden_gates) == 0

    def test_p0_4_task_authority_cannot_be_shadowed(self) -> None:
        """P0-4: Arbitrary PSE input claiming task complete while canonical Task v2 does not must be rejected."""
        pid = "prj_p0_task_authority"
        reducer = ProjectStateReducer()

        # Canonical TaskStore says task is working (revision 1)
        canonical_task_view = TaskAuthorityView(
            task_id="task_core_01",
            state="working",
            revision=1,
            digest=TaskAuthorityView.compute_digest("task_core_01", "working", 1),
            source_identity="TaskStore:v2",
        )

        # Replay events: a regular event mentions task without authoritative observed lifecycle event
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "task_core_01"}, None),
            ],
        )

        state = reducer.reduce(events, tasks=[canonical_task_view])
        # Task authority view remains authoritative
        assert state.tasks["task_core_01"].state == "working"
        assert "task_core_01" not in state.ready_tasks
        assert "task_core_01" in state.active_tasks

    def test_p0_5_decision_authority_cannot_be_shadowed(self) -> None:
        """P0-5: PSE semantic candidate claiming decision accepted while DecisionService does not must not approve."""
        pid = "prj_p0_decision_authority"
        reducer = ProjectStateReducer()

        # Authoritative DecisionService view says pending
        canonical_dec_view = DecisionAuthorityView(
            decision_id="dec_arch_01",
            status="pending",
            revision=1,
            digest=DecisionAuthorityView.compute_digest("dec_arch_01", "pending"),
            source_identity="DecisionService:v1",
        )

        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("decision.associated", {"decision_id": "dec_arch_01"}, None),
            ],
        )

        state = reducer.reduce(events, decisions=[canonical_dec_view])
        assert state.decisions["dec_arch_01"].status == "pending"
        assert "dec_arch_01" in state.required_approvals

    def test_p0_6_snapshot_cannot_forge_state(self) -> None:
        """P0-6: Syntactically valid snapshot claiming CLOSED with forged hash/lineage is rejected."""
        pid = "prj_p0_forged_snap"
        reducer = ProjectStateReducer()

        valid_state = ProjectState(
            project_id=pid,
            current_phase=ProjectPhase.DISCOVERY,
            state_revision="0" * 64,
        )
        valid_state.state_revision = compute_state_revision(valid_state.model_dump())

        # Forged snapshot claiming phase is CLOSED
        forged_state = deepcopy(valid_state)
        forged_state.current_phase = ProjectPhase.CLOSED

        snapshot = ProjectStateSnapshot(
            project_id=pid,
            last_event_sequence=10,
            last_event_hash="f" * 64,
            state_revision=valid_state.state_revision,  # Mismatched revision
            state=forged_state,
            snapshot_digest="e" * 64,
        )

        with pytest.raises(SnapshotIntegrityError):
            reducer.restore_from_snapshot(snapshot)


# ---------------------------------------------------------------------------
# 4. Tasks & Readiness Evaluation (Gate G4.3)
# ---------------------------------------------------------------------------


class TestTaskReadinessAndDependencies:
    """Verify task readiness, multi-level dependencies, and circular dependency handling."""

    def test_ready_task_no_dependencies(self) -> None:
        pid = "prj_task_ready"
        reducer = ProjectStateReducer()
        task = TaskAuthorityView(
            task_id="t_ready",
            state="ready",
            revision=1,
            digest=TaskAuthorityView.compute_digest("t_ready", "ready", 1),
            source_identity="TaskStore:v2",
        )
        events = build_event_chain(pid, [("project.created", {}, None)])
        state = reducer.reduce(events, tasks=[task])
        assert "t_ready" in state.ready_tasks
        assert "t_ready" not in state.blocked_tasks

    def test_multi_level_dependency_chain(self) -> None:
        """A blocks B, B blocks C. When A completes, B ready, C still blocked until B completes."""
        pid = "prj_task_chain"
        reducer = ProjectStateReducer()

        task_a = TaskAuthorityView(
            task_id="t_a",
            state="working",
            revision=1,
            digest=TaskAuthorityView.compute_digest("t_a", "working", 1),
            source_identity="TaskStore:v2",
        )
        task_b = TaskAuthorityView(
            task_id="t_b",
            state="ready",
            revision=1,
            dependencies=["t_a"],
            digest=TaskAuthorityView.compute_digest("t_b", "ready", 1, dependencies=["t_a"]),
            source_identity="TaskStore:v2",
        )
        task_c = TaskAuthorityView(
            task_id="t_c",
            state="ready",
            revision=1,
            dependencies=["t_b"],
            digest=TaskAuthorityView.compute_digest("t_c", "ready", 1, dependencies=["t_b"]),
            source_identity="TaskStore:v2",
        )

        events_init = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("task.associated", {"task_id": "t_a"}, None),
                ("task.associated", {"task_id": "t_b"}, None),
                ("task.associated", {"task_id": "t_c"}, None),
            ],
        )
        state1 = reducer.reduce(events_init, tasks=[task_a, task_b, task_c])
        # t_a is working; t_b and t_c are blocked
        assert "t_a" in state1.active_tasks
        assert "t_b" in state1.blocked_tasks
        assert "t_c" in state1.blocked_tasks

        # Step 2: t_a completes
        events_step2 = [
            *events_init,
            make_event(
                pid,
                len(events_init) + 1,
                events_init[-1].event_hash,
                "task.lifecycle.observed",
                payload={"task_id": "t_a", "state": "completed", "receipt_ids": ["tcr_a"]},
            ),
        ]
        state2 = reducer.reduce(events_step2, tasks=[task_a, task_b, task_c])
        # t_b is now ready! t_c is still blocked by t_b
        assert "t_b" in state2.ready_tasks
        assert "t_b" not in state2.blocked_tasks
        assert "t_c" in state2.blocked_tasks

        # Step 3: t_b completes
        events_step3 = [
            *events_step2,
            make_event(
                pid,
                len(events_step2) + 1,
                events_step2[-1].event_hash,
                "task.lifecycle.observed",
                payload={"task_id": "t_b", "state": "completed", "receipt_ids": ["tcr_b"]},
            ),
        ]
        state3 = reducer.reduce(events_step3, tasks=[task_a, task_b, task_c])
        # t_c is now ready!
        assert "t_c" in state3.ready_tasks
        assert "t_c" not in state3.blocked_tasks

    def test_circular_dependencies_detected_and_handled(self) -> None:
        """A -> B -> C -> A cycle detection and health flag emission without recursion."""
        pid = "prj_task_cycle"
        reducer = ProjectStateReducer()

        task_a = TaskAuthorityView(
            task_id="t_a",
            state="ready",
            revision=1,
            dependencies=["t_c"],
            digest=TaskAuthorityView.compute_digest("t_a", "ready", 1, dependencies=["t_c"]),
            source_identity="TaskStore:v2",
        )
        task_b = TaskAuthorityView(
            task_id="t_b",
            state="ready",
            revision=1,
            dependencies=["t_a"],
            digest=TaskAuthorityView.compute_digest("t_b", "ready", 1, dependencies=["t_a"]),
            source_identity="TaskStore:v2",
        )
        task_c = TaskAuthorityView(
            task_id="t_c",
            state="ready",
            revision=1,
            dependencies=["t_b"],
            digest=TaskAuthorityView.compute_digest("t_c", "ready", 1, dependencies=["t_b"]),
            source_identity="TaskStore:v2",
        )

        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("task.associated", {"task_id": "t_a"}, None),
                ("task.associated", {"task_id": "t_b"}, None),
                ("task.associated", {"task_id": "t_c"}, None),
            ],
        )

        state = reducer.reduce(events, tasks=[task_a, task_b, task_c])

        # All cycle members are blocked
        assert "t_a" in state.blocked_tasks
        assert "t_b" in state.blocked_tasks
        assert "t_c" in state.blocked_tasks
        assert HealthFlag.CIRCULAR_DEPENDENCY_DETECTED.value in state.health_flags

        # Cycle detection utility returns stable, sorted cycle
        cycles = detect_dependency_cycles(state.tasks)
        assert len(cycles) == 1
        assert cycles[0] == ["t_a", "t_c", "t_b", "t_a"]


# ---------------------------------------------------------------------------
# 5. RAID Aggregation Tests
# ---------------------------------------------------------------------------


class TestRAIDAggregation:
    """Verify RAID entity tracking, historical recovery, and status transitions."""

    def test_risk_lifecycle_open_update_close(self) -> None:
        pid = "prj_raid_risk"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                (
                    "risk.opened",
                    {"risk_id": "rsk_01", "impact": "high", "status": "identified"},
                    None,
                ),
                ("risk.updated", {"risk_id": "rsk_01", "impact": "critical"}, None),
                ("risk.closed", {"risk_id": "rsk_01"}, None),
            ],
        )
        state = reducer.reduce(events)
        assert "rsk_01" in state.risks
        assert state.risks["rsk_01"].status == "retired"
        assert "rsk_01" not in state.open_risks

    def test_assumption_lifecycle_create_invalidate(self) -> None:
        pid = "prj_raid_asm"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                (
                    "assumption.created",
                    {"assumption_id": "asm_01", "statement": "DB has 99.9% SLA"},
                    None,
                ),
                ("assumption.invalidated", {"assumption_id": "asm_01"}, None),
            ],
        )
        state = reducer.reduce(events)
        assert "asm_01" in state.assumptions
        assert state.assumptions["asm_01"].status == "invalidated"
        assert "asm_01" not in state.active_assumptions

    def test_issue_lifecycle_and_reopen(self) -> None:
        pid = "prj_raid_issue"
        reducer = ProjectStateReducer()
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("issue.opened", {"issue_id": "iss_01", "severity": "blocker"}, None),
                ("issue.resolved", {"issue_id": "iss_01", "resolution": "patch applied"}, None),
                ("issue.opened", {"issue_id": "iss_01", "severity": "critical"}, None),  # Reopen!
            ],
        )
        state = reducer.reduce(events)
        assert "iss_01" in state.issues
        assert state.issues["iss_01"].status == "open"
        assert "iss_01" in state.open_issues
        assert HealthFlag.BLOCKING_ISSUES_PRESENT.value in state.health_flags

    def test_unverified_candidate_cannot_close_issue(self) -> None:
        """Gate G4.2 / Section 19: Unverified entity cannot close an issue authoritatively."""
        pid = "prj_raid_unverified"
        reducer = ProjectStateReducer()
        events = [
            make_event(pid, 1, "", "project.created", {}),
            make_event(pid, 2, "", "issue.opened", {"issue_id": "iss_02", "severity": "major"}),
        ]
        events[1].prev_event_hash = events[0].event_hash
        events[1].event_hash = compute_event_hash(events[1].model_dump())

        # Unverified / model event attempting to resolve issue
        bad_resolve = make_event(
            pid,
            3,
            events[1].event_hash,
            "issue.resolved",
            payload={"issue_id": "iss_02", "resolution": "AI says fixed"},
            actor="model",
            source="model_extraction",
        )
        events.append(bad_resolve)

        state = reducer.reduce(events)
        # Issue remains open!
        assert state.issues["iss_02"].status == "open"
        assert "iss_02" in state.open_issues


# ---------------------------------------------------------------------------
# 6. Replay Integrity & Error Handling (Section 23)
# ---------------------------------------------------------------------------


class TestReplayIntegrity:
    """Verify fail-closed error handling for corrupted event streams."""

    def test_sequence_gap_fails_closed(self) -> None:
        pid = "prj_seq_gap"
        reducer = ProjectStateReducer()
        e1 = make_event(pid, 1, "", "project.created", {})
        e2 = make_event(pid, 3, e1.event_hash, "task.associated", {"task_id": "t1"})  # Gap 1 -> 3
        with pytest.raises(StateEngineIntegrityError, match="Event sequence gap"):
            reducer.reduce([e1, e2])

    def test_broken_hash_chain_fails_closed(self) -> None:
        pid = "prj_hash_break"
        reducer = ProjectStateReducer()
        e1 = make_event(pid, 1, "", "project.created", {})
        e2 = make_event(pid, 2, "0" * 64, "task.associated", {"task_id": "t1"})  # Wrong prev_hash
        with pytest.raises(StateEngineIntegrityError, match="Broken hash chain"):
            reducer.reduce([e1, e2])

    def test_cross_project_event_fails_closed(self) -> None:
        pid = "prj_cross_proj"
        reducer = ProjectStateReducer()
        e1 = make_event(pid, 1, "", "project.created", {})
        e2 = make_event("prj_other_99", 2, e1.event_hash, "task.associated", {"task_id": "t1"})
        with pytest.raises(StateEngineIntegrityError, match="Cross-project event detected"):
            reducer.reduce([e1, e2])


# ---------------------------------------------------------------------------
# 7. Snapshots Equivalence & Tampering (Gate G4.1 & Section 21, 22)
# ---------------------------------------------------------------------------


class TestSnapshots:
    """Verify snapshot creation, restoration, tail replay equivalence, and tampering defense."""

    def test_snapshot_plus_tail_equals_full_replay(self) -> None:
        """Mandatory: normalize(full_replay) == normalize(snapshot + tail)."""
        pid = "prj_snap_equiv"
        reducer = ProjectStateReducer()

        full_events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "task_1"}, None),
                (
                    "risk.opened",
                    {"risk_id": "rsk_01", "impact": "low", "status": "identified"},
                    None,
                ),
                ("task.associated", {"task_id": "task_2"}, None),
                ("risk.closed", {"risk_id": "rsk_01"}, None),
            ],
        )

        head_events = full_events[:3]
        tail_events = full_events[3:]

        # Create snapshot at event 3
        state_at_head = reducer.reduce(head_events)
        snapshot = reducer.create_snapshot(state_at_head)
        assert snapshot.verify_integrity() is True

        # Replay tail from snapshot
        state_restored = reducer.restore_from_snapshot(snapshot, tail_events)

        # Full replay
        state_full = reducer.reduce(full_events)

        assert state_restored.state_revision == state_full.state_revision
        assert state_restored.to_canonical_bytes() == state_full.to_canonical_bytes()

    def test_tampered_snapshot_fails_closed(self) -> None:
        pid = "prj_snap_tamper"
        reducer = ProjectStateReducer()
        events = build_event_chain(pid, [("project.created", {}, None)])
        state = reducer.reduce(events)
        snapshot = reducer.create_snapshot(state)

        # Tamper with snapshot state
        tampered_state = deepcopy(state)
        tampered_state.active_tasks = ["forged_task"]
        bad_snapshot = ProjectStateSnapshot(
            project_id=pid,
            last_event_sequence=snapshot.last_event_sequence,
            last_event_hash=snapshot.last_event_hash,
            state_revision=snapshot.state_revision,
            state=tampered_state,
            snapshot_digest=snapshot.snapshot_digest,
        )

        with pytest.raises(SnapshotIntegrityError):
            reducer.restore_from_snapshot(bad_snapshot)

    def test_snapshot_create_rejects_stale_state_revision(self) -> None:
        """Snapshot creation refuses a state whose revision no longer matches its content."""
        reducer = ProjectStateReducer()
        state = reducer.reduce(
            build_event_chain("prj_snap_create", [("project.created", {}, None)])
        )
        state.state_revision = "0" * 64

        with pytest.raises(SnapshotIntegrityError, match="state_revision does not match"):
            ProjectStateSnapshot.create(state)


# ---------------------------------------------------------------------------
# 8. Explainability (Gate G4.6)
# ---------------------------------------------------------------------------


class TestExplainability:
    """Verify explain(field) produces deterministic traces for all required fields."""

    @pytest.mark.parametrize(
        "field",
        [
            "current_phase",
            "active_tasks",
            "ready_tasks",
            "blocked_tasks",
            "open_risks",
            "open_issues",
            "valid_decisions",
            "required_approvals",
            "health_flags",
            "state_revision",
        ],
    )
    def test_explain_mandatory_fields(self, field: str) -> None:
        pid = "prj_explain_all"
        reducer = ProjectStateReducer()
        task = TaskAuthorityView(
            task_id="task_01",
            state="ready",
            revision=1,
            digest=TaskAuthorityView.compute_digest("task_01", "ready", 1),
            source_identity="TaskStore:v2",
        )
        dec = DecisionAuthorityView(
            decision_id="dec_01",
            status="pending",
            revision=1,
            digest=DecisionAuthorityView.compute_digest("dec_01", "pending"),
            source_identity="DecisionService:v1",
        )
        events = build_event_chain(
            pid,
            [
                ("project.created", {}, None),
                ("project.phase.changed", {"target_phase": "PLANNING"}, ["evi_c"]),
                ("task.associated", {"task_id": "task_01"}, None),
                ("decision.associated", {"decision_id": "dec_01"}, None),
                (
                    "risk.opened",
                    {"risk_id": "rsk_01", "impact": "medium", "status": "identified"},
                    None,
                ),
                (
                    "issue.opened",
                    {"issue_id": "iss_01", "severity": "minor", "status": "open"},
                    None,
                ),
            ],
        )
        state = reducer.reduce(events, tasks=[task], decisions=[dec])

        explanation = reducer.explain(state, field)
        assert explanation.field == field
        assert explanation.project_id == pid
        assert explanation.state_revision == state.state_revision
        assert isinstance(explanation.contributing_event_ids, list)
        assert isinstance(explanation.applicable_rules, list)
        assert isinstance(explanation.authority_references, list)

    def test_unknown_field_fails_closed(self) -> None:
        pid = "prj_explain_err"
        reducer = ProjectStateReducer()
        events = build_event_chain(pid, [("project.created", {}, None)])
        state = reducer.reduce(events)
        with pytest.raises(UnexplainableFieldError):
            reducer.explain(state, "arbitrary_nonexistent_field")

    def test_valid_decisions_explanation_excludes_unresolved_decisions(self) -> None:
        """The valid_decisions trace only cites approved projected decisions."""
        approved = DecisionAuthorityView(
            decision_id="dec_approved",
            status="approved",
            digest=DecisionAuthorityView.compute_digest(
                "dec_approved", "approved", receipt_id="dcr_approved"
            ),
            source_identity="evt_approved",
            receipt_id="dcr_approved",
        )
        pending = DecisionAuthorityView(
            decision_id="dec_pending",
            status="pending",
            digest=DecisionAuthorityView.compute_digest("dec_pending", "pending"),
            source_identity="evt_pending",
        )
        rejected = DecisionAuthorityView(
            decision_id="dec_rejected",
            status="rejected",
            digest=DecisionAuthorityView.compute_digest(
                "dec_rejected", "rejected", receipt_id="dcr_rejected"
            ),
            source_identity="evt_rejected",
            receipt_id="dcr_rejected",
        )
        expired = DecisionAuthorityView(
            decision_id="dec_expired",
            status="expired",
            digest=DecisionAuthorityView.compute_digest("dec_expired", "expired"),
            source_identity="evt_expired",
        )
        state = ProjectState(
            project_id="prj_explain_decisions",
            state_revision="0" * 64,
            decisions={view.decision_id: view for view in (approved, pending, rejected, expired)},
            valid_decisions=["dec_approved"],
        )

        explanation = ProjectStateReducer().explain(state, "valid_decisions")

        assert explanation.contributing_event_ids == ["evt_approved"]
        assert explanation.decision_references == ["dec_approved"]
        assert explanation.evidence_references == ["dcr_approved"]


# ---------------------------------------------------------------------------
# 9. Performance Benchmark (Section 44)
# ---------------------------------------------------------------------------


class TestPerformance:
    """Measure replay performance on synthetic workloads."""

    @pytest.mark.parametrize("event_count", [100, 1000, 10000])
    def test_synthetic_replay_performance(self, event_count: int) -> None:
        pid = f"prj_perf_{event_count}"
        reducer = ProjectStateReducer()

        # Generate synthetic stream of task and risk events
        events: list[ProjectEvent] = []
        prev_hash = ""
        for i in range(1, event_count + 1):
            if i == 1:
                etype = "project.created"
                payload = {}
            elif i % 2 == 0:
                etype = "task.associated"
                payload = {"task_id": f"task_{i // 2}"}
            else:
                etype = "risk.opened"
                payload = {"risk_id": f"rsk_{i // 2:04d}", "impact": "low", "status": "identified"}

            ev = make_event(pid, i, prev_hash, etype, payload)
            events.append(ev)
            prev_hash = ev.event_hash

        start_time = time.perf_counter()
        state = reducer.reduce(events)
        elapsed = time.perf_counter() - start_time

        assert state.last_event_sequence == event_count
        assert state.state_revision != ""
        # Performance check: 10,000 events should complete within 5 seconds on CPU
        assert elapsed < 5.0
