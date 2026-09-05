"""POWER 3.8 Phase 4 — temporal authority and historical causality regressions."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from power_framework.core.decision_service import DecisionService
from power_framework.core.governance_engine import compute_rules_digest
from power_framework.core.project_models import AppendCommand
from power_framework.core.project_store import ProjectEventStore
from power_framework.core.state_models import (
    IllegalStateTransitionError,
    StateEngineIntegrityError,
)
from power_framework.core.state_reducer import ProjectStateReducer
from power_framework.core.state_service import ProjectStateService
from power_framework.core.task_service import TaskService

LEAD = "user:lead"


def _append(
    vault: Path,
    project_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    actor: str = LEAD,
    source: str = "pse_governance",
    evidence_refs: list[str] | None = None,
) -> None:
    store = ProjectEventStore(project_id, vault)
    writer = store._append_governed if source == "pse_governance" else store.append_untrusted
    writer(
        AppendCommand(
            project_id=project_id,
            event_type=event_type,
            payload=payload or {},
            actor=actor,
            source=source,
            evidence_refs=evidence_refs or [],
        ),
    )


def _task(service: TaskService, task_id: str, state: str = "ready") -> None:
    service.create_task(
        task_id=task_id,
        title=task_id,
        objective="temporal authority regression",
        owner="local",
        state=state,  # type: ignore[arg-type]
    )


def _approved_decision(
    service: DecisionService,
    decision_id: str,
    task_id: str,
    *,
    approve: bool = True,
) -> None:
    service.create_decision(
        decision_id=decision_id,
        task_id=task_id,
        title=decision_id,
        requested_by="requester",
        allowed_actors=["operator"],
    )
    if approve:
        service.resolve_decision(
            decision_id,
            action="approve",
            actor="operator",
            authority="apply",
        )


def _discovery_to_planning(vault: Path, project_id: str, *, owner: str | None = LEAD) -> None:
    _append(
        vault,
        project_id,
        "project.created",
        {"name": project_id, **({"owner": owner} if owner else {})},
    )
    _append(
        vault,
        project_id,
        "evidence.attached",
        {"evidence_id": "evi_charter", "evidence_type": "charter"},
    )
    ProjectStateService(vault).append_governance_evaluation(
        project_id,
        "dor",
        actor=LEAD,
    )
    _append(
        vault,
        project_id,
        "project.phase.changed",
        {"target_phase": "PLANNING", "owner": owner or LEAD},
        evidence_refs=["evi_charter"],
    )


def _evaluate_dor(
    vault: Path,
    project_id: str,
    tasks: TaskService,
    decisions: DecisionService,
) -> None:
    ProjectStateService(
        vault, task_service=tasks, decision_service=decisions
    ).append_governance_evaluation(
        project_id,
        "dor",
        actor=LEAD,
        evidence_refs=["evi_charter"],
    )


class TestTemporalAuthority:
    def test_t13_future_task_association_cannot_satisfy_historical_dor(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t13_future_task"
        tasks = TaskService(vault)
        _task(tasks, "task_x")
        decisions = DecisionService(vault, task_service=tasks)
        _approved_decision(decisions, "dec_exec", "task_x")
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": LEAD})
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_exec"})
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_exec"},
            evidence_refs=["evi_charter"],
        )
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})

        with pytest.raises(
            IllegalStateTransitionError,
            match=r"MISSING_REQUIRED_APPROVAL|initial_tasks_registered|dor_passed_or_overridden|MISSING_CANONICAL_DOR_EVALUATION",
        ):
            ProjectStateService(
                vault, task_service=tasks, decision_service=decisions
            ).rebuild_project_state(project_id)

    def test_t14_future_task_completion_cannot_satisfy_historical_dod(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t14_future_completion"
        tasks = TaskService(vault)
        _task(tasks, "task_x", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": LEAD})
        _approved_decision(decisions, "dec_exec", "task_x")
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_exec"})
        _evaluate_dor(vault, project_id, tasks, decisions)
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_exec"},
            evidence_refs=["evi_charter"],
        )
        _append(vault, project_id, "evidence.attached", {"evidence_id": "evi_dod"})
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "CLOSING"},
            evidence_refs=["evi_dod"],
        )
        artifact = vault / "done.txt"
        artifact.write_text("done", encoding="utf-8")
        task = tasks.get_task("task_x")
        assert task is not None
        tasks.transition_task(
            "task_x",
            "completed",
            actor="local",
            expected_revision=task.revision,
            completion_postcondition="verified",
            completion_artifact_refs=[artifact.name],
        )

        with pytest.raises(IllegalStateTransitionError, match=r"all_tasks_terminal|DOD"):
            ProjectStateService(
                vault, task_service=tasks, decision_service=decisions
            ).rebuild_project_state(project_id)

    def test_t15_future_decision_association_cannot_satisfy_historical_approval(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t15_future_decision"
        tasks = TaskService(vault)
        _task(tasks, "task_x")
        decisions = DecisionService(vault, task_service=tasks)
        _approved_decision(decisions, "dec_future", "task_x")
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": LEAD})
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})
        _evaluate_dor(vault, project_id, tasks, decisions)
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_future"},
            evidence_refs=["evi_charter"],
        )
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_future"})

        with pytest.raises(IllegalStateTransitionError, match="MISSING_REQUIRED_APPROVAL"):
            ProjectStateService(
                vault, task_service=tasks, decision_service=decisions
            ).rebuild_project_state(project_id)

    def test_t16_future_decision_approval_cannot_authorize_earlier_transition(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t16_future_approval"
        tasks = TaskService(vault)
        _task(tasks, "task_x")
        decisions = DecisionService(vault, task_service=tasks)
        _approved_decision(decisions, "dec_later", "task_x", approve=False)
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": LEAD})
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_later"})
        _evaluate_dor(vault, project_id, tasks, decisions)
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_later"},
            evidence_refs=["evi_charter"],
        )
        decisions.resolve_decision(
            "dec_later", action="approve", actor="operator", authority="apply"
        )

        with pytest.raises(IllegalStateTransitionError, match="MISSING_REQUIRED_APPROVAL"):
            ProjectStateService(
                vault, task_service=tasks, decision_service=decisions
            ).rebuild_project_state(project_id)

    def test_t17_multiple_accountable_actors_fail_closed(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t17_multiple_accountable"
        tasks = TaskService(vault)
        _task(tasks, "task_x")
        decisions = DecisionService(vault, task_service=tasks)
        _approved_decision(decisions, "dec_exec", "task_x")
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": "user:a"})
        _append(vault, project_id, "raci.assigned", {"role": "A", "actor": "user:b"})
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_exec"})
        _evaluate_dor(vault, project_id, tasks, decisions)
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_exec"},
            evidence_refs=["evi_charter"],
        )

        with pytest.raises(
            IllegalStateTransitionError,
            match=r"RACI_ACCOUNTABLE_CARDINALITY_VIOLATION|raci_accountable_assigned",
        ):
            ProjectStateService(
                vault, task_service=tasks, decision_service=decisions
            ).rebuild_project_state(project_id)

    def test_future_raci_assignment_cannot_authorize_earlier_transition(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_future_raci"
        tasks = TaskService(vault)
        _task(tasks, "task_x")
        decisions = DecisionService(vault, task_service=tasks)
        _approved_decision(decisions, "dec_exec", "task_x")
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_exec"})
        _evaluate_dor(vault, project_id, tasks, decisions)
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_exec"},
            evidence_refs=["evi_charter"],
        )
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": LEAD})

        with pytest.raises(IllegalStateTransitionError, match="raci_accountable_assigned"):
            ProjectStateService(
                vault, task_service=tasks, decision_service=decisions
            ).rebuild_project_state(project_id)

    def test_future_evidence_attachment_cannot_authorize_earlier_transition(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_future_evidence"
        _append(vault, project_id, "project.created", {"name": project_id, "owner": LEAD})
        ProjectStateService(vault).append_governance_evaluation(
            project_id,
            "dor",
            actor=LEAD,
        )
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "PLANNING"},
            evidence_refs=["evi_later"],
        )
        _append(vault, project_id, "evidence.attached", {"evidence_id": "evi_later"})

        with pytest.raises(
            IllegalStateTransitionError, match="EVIDENCE_REF_NOT_CANONICALLY_ATTACHED"
        ):
            ProjectStateService(vault).rebuild_project_state(project_id)

    def test_t18_transition_cannot_self_declare_owner(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t18_self_owner"
        _append(vault, project_id, "project.created", {"name": project_id})
        _append(
            vault,
            project_id,
            "evidence.attached",
            {"evidence_id": "evi_charter", "evidence_type": "charter"},
        )
        ProjectStateService(vault).append_governance_evaluation(
            project_id,
            "dor",
            actor=LEAD,
        )
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "PLANNING", "owner": "user:fake"},
            evidence_refs=["evi_charter"],
        )

        with pytest.raises(IllegalStateTransitionError, match="owner_assigned"):
            ProjectStateService(vault).rebuild_project_state(project_id)

    def test_t19_transition_cannot_self_declare_charter(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_t19_self_charter"
        _append(vault, project_id, "project.created", {"name": project_id, "owner": LEAD})
        _append(vault, project_id, "evidence.attached", {"evidence_id": "evi_misc"})
        ProjectStateService(vault).append_governance_evaluation(
            project_id,
            "dor",
            actor=LEAD,
        )
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {
                "target_phase": "PLANNING",
                "charter_ref": "charter_fake",
                "evidence_refs": ["evi_misc"],
            },
            evidence_refs=["evi_misc"],
        )

        with pytest.raises(IllegalStateTransitionError, match="charter_present"):
            ProjectStateService(vault).rebuild_project_state(project_id)

    def test_t20_effective_rules_manifest_drift_is_detected(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parent.parent
            / "artifacts"
            / "project-state"
            / "phase-4"
            / "governance_rules_v1.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(manifest)
        mutated["override_policy"]["require_reason"] = not mutated["override_policy"][
            "require_reason"
        ]
        assert compute_rules_digest(mutated) != compute_rules_digest(manifest)

    def test_generic_evaluation_payload_cannot_mint_historical_authority(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_untrusted_evaluation"
        _append(vault, project_id, "project.created", {"name": project_id, "owner": LEAD})
        _append(
            vault,
            project_id,
            "dor.evaluated",
            {"result": "passed", "passed": True},
            source="cli",
        )

        with pytest.raises(
            StateEngineIntegrityError,
            match=r"Invalid historical governance evaluation|untrusted source",
        ):
            ProjectStateService(vault).rebuild_project_state(project_id)

    def test_reserved_governance_append_requires_service_capability(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_reserved_ingress"
        store = ProjectEventStore(project_id, vault)
        with pytest.raises(PermissionError, match="trusted PSE writer"):
            store.append(
                AppendCommand(
                    project_id=project_id,
                    event_type="dor.evaluated",
                    payload={"result": "passed"},
                    actor=LEAD,
                    source="pse_governance",
                )
            )
        assert store.verify().event_count == 0

    def test_snapshot_overlay_cannot_rewrite_historical_phase_validity(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        project_id = "prj_snapshot_temporal"
        tasks = TaskService(vault)
        _task(tasks, "task_x", state="working")
        decisions = DecisionService(vault, task_service=tasks)
        _approved_decision(decisions, "dec_exec", "task_x")
        _discovery_to_planning(vault, project_id)
        _append(vault, project_id, "raci.assigned", {"role": "Accountable", "actor": LEAD})
        _append(vault, project_id, "task.associated", {"task_id": "task_x"})
        _append(vault, project_id, "decision.associated", {"decision_id": "dec_exec"})
        _evaluate_dor(vault, project_id, tasks, decisions)
        _append(
            vault,
            project_id,
            "project.phase.changed",
            {"target_phase": "EXECUTION", "approval_ref": "dec_exec"},
            evidence_refs=["evi_charter"],
        )

        service = ProjectStateService(vault, task_service=tasks, decision_service=decisions)
        before = service.rebuild_project_state(project_id)
        snapshot = ProjectStateReducer().create_snapshot(before)
        historical_phase_history = before.phase_history

        artifact = vault / "done.txt"
        artifact.write_text("done", encoding="utf-8")
        task = tasks.get_task("task_x")
        assert task is not None
        tasks.transition_task(
            "task_x",
            "completed",
            actor="local",
            expected_revision=task.revision,
            completion_postcondition="verified",
            completion_artifact_refs=[artifact.name],
        )

        restored = service.restore_snapshot_authoritative(snapshot)
        assert restored.current_phase == before.current_phase
        assert restored.phase_history == historical_phase_history
        assert restored.tasks["task_x"].state == "completed"
