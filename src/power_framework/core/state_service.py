"""POWER Project State Engine (PSE) Phase 4 — Trusted Authority Composition Boundary.

Integrity != authority. A self-consistent event chain, a matching
self-digest, a source identity string, an observed lifecycle payload, or a
snapshot seal never grant canonical authority by themselves.

Authoritative ProjectState may only be emitted from verified canonical
sources through ProjectStateService / ProjectStateEngine:

    service = ProjectStateService(vault_root)
    state = service.rebuild_project_state(project_id)

which (1) constructs ProjectEventStore(project_id, vault_root); (2) verifies
the canonical Phase-2 ledger; (3) re-reads the authoritative event sequence
from that store; (4) never trusts caller-supplied hashes as proof of ledger
membership; (5) resolves federated Task and Decision authority from their
canonical services; and (6) only then executes the pure reduction.

Canonical authority is established by independent resolution against the
owning authoritative subsystem. Digests/receipts record or protect the
result; they are not bearer credentials.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from power_framework.core.canonical_json import compute_event_hash, compute_payload_digest
from power_framework.core.decision_service import DecisionService
from power_framework.core.governance_engine import RULES_DIGEST, AuthorityContext
from power_framework.core.project_models import AppendCommand, LedgerIntegrityError, ProjectEvent
from power_framework.core.project_store import ProjectEventStore
from power_framework.core.state_models import (
    DecisionAuthorityView,
    DoDEvaluation,
    DoREvaluation,
    HistoricalGovernanceEvaluation,
    ProjectPhase,
    ProjectState,
    ProjectStateSnapshot,
    SnapshotIntegrityError,
    StateEngineIntegrityError,
    TaskAuthorityView,
)
from power_framework.core.state_reducer import ProjectStateReducer
from power_framework.core.task_service import TaskService

if TYPE_CHECKING:
    from collections.abc import Sequence


class AuthoritativeStateError(StateEngineIntegrityError):
    """Raised when caller-supplied material fails canonical authority checks."""


class ProjectStateService:
    """Trusted orchestration boundary for authoritative ProjectState."""

    def __init__(
        self,
        vault_root: Path,
        task_service: TaskService | None = None,
        decision_service: DecisionService | None = None,
    ) -> None:
        raw_vault_root = Path(vault_root).expanduser()
        for ancestor in (raw_vault_root, *raw_vault_root.parents):
            if ancestor.is_symlink():
                raise ValueError(f"Vault path contains a symlink ancestor: {ancestor}")
            if ancestor == ancestor.parent:
                break
        self.vault_root = raw_vault_root.resolve()
        self.task_service: TaskService = task_service or TaskService(self.vault_root)
        self.decision_service: DecisionService = decision_service or DecisionService(
            self.vault_root, task_service=self.task_service
        )
        if self.task_service.vault_dir.resolve() != self.vault_root:
            raise ValueError("TaskService vault does not match ProjectStateService vault")
        if self.decision_service.vault_dir.resolve() != self.vault_root:
            raise ValueError("DecisionService vault does not match ProjectStateService vault")
        if self.decision_service.task_service.store is not self.task_service.store:
            raise ValueError("DecisionService must use the ProjectStateService TaskStore")
        self.reducer = ProjectStateReducer()

    # ------------------------------------------------------------------
    # Canonical ledger access
    # ------------------------------------------------------------------
    def _canonical_store(self, project_id: str) -> ProjectEventStore:
        return ProjectEventStore(project_id, self.vault_root)

    def _read_canonical_events(self, project_id: str) -> list[ProjectEvent]:
        """Verify the canonical ledger and re-read the authoritative sequence."""
        store = self._canonical_store(project_id)
        verification = store.verify()
        if not verification.valid:
            raise LedgerIntegrityError(
                f"Canonical ledger verification failed for '{project_id}': "
                f"{'; '.join(verification.errors)}"
            )
        batch = store.read_verified_replay()
        events = list(batch.events)
        for event in events:
            expected = compute_payload_digest(event.payload or {})
            if expected != event.payload_digest:
                raise StateEngineIntegrityError(
                    f"Canonical ledger payload digest mismatch on {event.event_id}"
                )
        return events

    def _ledger_head(self, project_id: str) -> tuple[int, str]:
        store = self._canonical_store(project_id)
        verification = store.verify()
        if not verification.valid:
            raise LedgerIntegrityError(f"Canonical ledger verification failed for '{project_id}'")
        return verification.last_sequence, verification.last_event_hash

    # ------------------------------------------------------------------
    # Federated authority resolution
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_ids(events: Sequence[ProjectEvent]) -> tuple[set[str], set[str]]:
        """Return only relationships active at the canonical ledger head.

        Observations are never membership events.  Most importantly, an ID
        appearing in a future association is not allowed to enter the
        historical replay prefix before that association's sequence.
        """
        task_ids: set[str] = set()
        decision_ids: set[str] = set()
        for event in events:
            payload = event.payload or {}
            if event.event_type == "task.associated":
                task_id = payload.get("task_id")
                if isinstance(task_id, str) and task_id.strip():
                    task_ids.add(task_id.strip())
            elif event.event_type == "task.disassociated":
                task_id = payload.get("task_id")
                if isinstance(task_id, str) and task_id.strip():
                    task_ids.discard(task_id.strip())
            elif event.event_type == "decision.associated":
                decision_id = payload.get("decision_id")
                if isinstance(decision_id, str) and decision_id.strip():
                    decision_ids.add(decision_id.strip())
            elif event.event_type == "decision.disassociated":
                decision_id = payload.get("decision_id")
                if isinstance(decision_id, str) and decision_id.strip():
                    decision_ids.discard(decision_id.strip())
        return task_ids, decision_ids

    def _resolve_live_tasks(self, task_ids: set[str]) -> dict[str, TaskAuthorityView]:
        """Resolve live TaskStore truth; caller views are never consulted."""
        views: dict[str, TaskAuthorityView] = {}
        for task_id in sorted(task_ids):
            task = self.task_service.get_task(task_id)
            if task is None:
                continue
            views[task_id] = TaskAuthorityView.from_power_task(task)
        return views

    def _resolve_live_decisions(
        self, decision_ids: set[str]
    ) -> tuple[dict[str, DecisionAuthorityView], set[str]]:
        """Resolve live DecisionService truth plus canonical approved IDs."""
        views: dict[str, DecisionAuthorityView] = {}
        approved: set[str] = set()
        for decision_id in sorted(decision_ids):
            decision = self.decision_service.get_decision(decision_id)
            if decision is None:
                continue
            views[decision_id] = DecisionAuthorityView.from_decision(decision)
            if decision.status == "approved" and decision.receipt_id:
                receipt = self.decision_service.get_receipt(decision.receipt_id)
                if (
                    receipt is not None
                    and receipt.receipt_id == decision.receipt_id
                    and receipt.decision_id == decision_id
                    and receipt.task_id == decision.task_id
                    and receipt.task_revision == decision.task_revision
                    and receipt.action in {"approve", "provide_input"}
                ):
                    approved.add(decision_id)
        return views, approved

    def _verified_task_receipts(self, task_ids: set[str]) -> set[str]:
        verified: set[str] = set()
        for task_id in task_ids:
            task = self.task_service.get_task(task_id)
            if task is None:
                continue
            for receipt_id in task.receipt_ids:
                try:
                    receipt = self.task_service.store.get_completion_receipt(receipt_id)
                except ValueError:
                    continue
                if (
                    receipt is not None
                    and receipt.task_id == task_id
                    and task.state in {"completed", "failed", "canceled", "rejected"}
                    and receipt.status == "verified"
                    and receipt.task_revision == task.revision
                ):
                    verified.add(receipt_id)
        return verified

    def _validate_historical_evaluations(self, events: Sequence[ProjectEvent]) -> None:
        """Re-validate immutable evaluation bindings against owning services."""
        from power_framework.core.decision_models import DecisionReceipt
        from power_framework.core.task_models import PowerTask

        for event in events:
            if event.event_type not in {"dor.evaluated", "dod.evaluated"}:
                continue
            try:
                evaluation = HistoricalGovernanceEvaluation.model_validate(event.payload or {})
            except ValueError as exc:
                raise AuthoritativeStateError(
                    f"Invalid historical governance evaluation {event.event_id}"
                ) from exc
            if event.source != "pse_governance":
                raise AuthoritativeStateError(
                    f"Historical governance evaluation {event.event_id} has untrusted source"
                )
            for task_view in evaluation.task_views:
                task = self.task_service.get_task(task_view.task_id)
                if task is None:
                    # Preserve the immutable historical reference when the
                    # current subsystem has been cleaned up; the overlay will
                    # expose this as stale/unresolved rather than rewriting it.
                    continue
                for receipt_id in task_view.receipt_ids:
                    receipt = self.task_service.store.get_completion_receipt(receipt_id)
                    if (
                        receipt is None
                        or receipt.task_id != task_view.task_id
                        or receipt.task_revision != task_view.revision
                        or receipt.status != "verified"
                    ):
                        raise AuthoritativeStateError(
                            f"Historical evaluation references invalid task receipt '{receipt_id}'"
                        )
                    receipt_payload = {
                        "task_id": receipt.task_id,
                        "task_revision": receipt.task_revision,
                        "completion_policy": receipt.completion_policy,
                        "postcondition_sha256": receipt.postcondition_sha256,
                        "artifact_digests": receipt.artifact_digests,
                        "actor": receipt.actor,
                    }
                    expected_receipt_id = (
                        "tcr_"
                        + hashlib.sha256(
                            json.dumps(
                                receipt_payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            ).encode("utf-8")
                        ).hexdigest()
                    )
                    if receipt.receipt_id != expected_receipt_id:
                        raise AuthoritativeStateError(
                            f"Historical evaluation receipt derivation mismatch: '{receipt_id}'"
                        )
                matched = False
                for task_event in self.task_service.get_events(task_view.task_id):
                    result = task_event.payload.get("result")
                    if not isinstance(result, dict):
                        continue
                    try:
                        historical_task = PowerTask.model_validate(result)
                    except ValueError:
                        continue
                    historical_view = TaskAuthorityView.from_power_task(historical_task)
                    if (
                        historical_view.task_id == task_view.task_id
                        and historical_view.state == task_view.state
                        and historical_view.revision == task_view.revision
                        and historical_view.dependencies == task_view.dependencies
                        and historical_view.open_gates == task_view.open_gates
                        and historical_view.receipt_ids == task_view.receipt_ids
                        and historical_view.digest == task_view.digest
                    ):
                        matched = True
                        break
                if not matched:
                    raise AuthoritativeStateError(
                        f"Historical evaluation task view is not a canonical TaskStore snapshot: "
                        f"'{task_view.task_id}'"
                    )
            for decision_view in evaluation.decision_views:
                decision = self.decision_service.get_decision(decision_view.decision_id)
                if decision is None:
                    continue
                if decision_view.status == "approved":
                    decision_receipt_id = decision_view.receipt_id
                    decision_receipt = self.decision_service.get_receipt(decision_receipt_id or "")
                    if (
                        decision_receipt is None
                        or decision_receipt.decision_id != decision_view.decision_id
                        or decision_receipt.task_id != decision_view.task_id
                        or decision_receipt.task_revision != decision_view.task_revision
                        or decision_receipt.action not in {"approve", "provide_input"}
                    ):
                        raise AuthoritativeStateError(
                            f"Historical evaluation decision receipt is not canonical: "
                            f"'{decision_view.decision_id}'"
                        )
                    if decision.status == "approved":
                        response = {
                            "comment": decision.resolution_comment,
                            "input_data": decision.resolution_input,
                        }
                        expected_response = DecisionReceipt.digest_payload(
                            decision.decision_id,
                            decision.task_id,
                            decision.task_revision,
                            decision.resolution_action or decision_receipt.action,
                            decision.resolved_by or decision_receipt.actor,
                            response,
                        )
                        if (
                            decision_receipt.actor != decision.resolved_by
                            or decision_receipt.response_sha256 != expected_response
                            or decision_receipt.receipt_id != "dcr_" + expected_response
                        ):
                            raise AuthoritativeStateError(
                                f"Historical decision receipt derivation mismatch: "
                                f"'{decision_view.decision_id}'"
                            )

    def _assemble_authority(
        self, events: Sequence[ProjectEvent]
    ) -> tuple[AuthorityContext, dict[str, TaskAuthorityView], dict[str, DecisionAuthorityView]]:
        """Build the verified normalized authority bundle from canonical sources."""
        self._validate_historical_evaluations(events)
        task_ids, decision_ids = self._collect_ids(events)
        live_tasks = self._resolve_live_tasks(task_ids)
        live_decisions, approved_ids = self._resolve_live_decisions(decision_ids)

        attached: set[str] = set()
        raci: dict[str, set[str]] = {}
        for event in events:
            if event.event_type == "evidence.attached" or event.event_type.startswith("artifact."):
                for ref in ProjectStateReducer._collect_evidence_refs(event):
                    attached.add(ref)
            elif event.event_type == "raci.assigned":
                payload = event.payload or {}
                role = payload.get("role")
                actor = payload.get("actor")
                if (
                    isinstance(role, str)
                    and role.strip()
                    and isinstance(actor, str)
                    and actor.strip()
                ):
                    canonical_role = (
                        "Accountable"
                        if role.strip().casefold() in {"accountable", "a"}
                        else role.strip()
                    )
                    raci.setdefault(canonical_role, set()).add(actor.strip())
            elif event.event_type == "raci.revoked":
                payload = event.payload or {}
                role = payload.get("role")
                actor = payload.get("actor")
                if isinstance(role, str) and role.strip():
                    canonical_role = (
                        "Accountable"
                        if role.strip().casefold() in {"accountable", "a"}
                        else role.strip()
                    )
                else:
                    canonical_role = ""
                if canonical_role and canonical_role in raci:
                    if isinstance(actor, str) and actor.strip():
                        raci[canonical_role].discard(actor.strip())
                    else:
                        raci[canonical_role].clear()
                    if not raci[canonical_role]:
                        del raci[canonical_role]

        accountable_actors = sorted(
            {
                actor
                for role, actors in raci.items()
                if role.strip().casefold() in {"accountable", "a"}
                for actor in actors
            }
        )
        accountable = accountable_actors[0] if len(accountable_actors) == 1 else None

        authority = AuthorityContext(
            attached_evidence=attached,
            approved_decision_ids=approved_ids,
            raci={role: sorted(actors) for role, actors in raci.items()},
            accountable_actor=accountable,
            verified_task_receipts=self._verified_task_receipts(task_ids),
            permit_accountable_approval=True,
            historical=True,
            raci_accountable_cardinality_valid=len(accountable_actors) <= 1,
        )
        return authority, live_tasks, live_decisions

    # ------------------------------------------------------------------
    # Authoritative public API
    # ------------------------------------------------------------------
    def rebuild_project_state(self, project_id: str) -> ProjectState:
        """Rebuild historical governance, then apply a current federation overlay."""
        canonical_events = self._read_canonical_events(project_id)
        authority, live_tasks, live_decisions = self._assemble_authority(canonical_events)
        historical = self.reducer.reduce_internal(
            canonical_events,
            project_id=project_id,
            authority=authority,
        )
        return self._apply_current_overlay(historical, live_tasks, live_decisions, authority)

    def rebuild_historical_governance_state(self, project_id: str) -> ProjectState:
        """Replay only sequence-bound PSE governance evidence, never live stores."""
        canonical_events = self._read_canonical_events(project_id)
        authority, _live_tasks, _live_decisions = self._assemble_authority(canonical_events)
        return self.reducer.reduce_internal(
            canonical_events,
            project_id=project_id,
            authority=authority,
        )

    def _apply_current_overlay(
        self,
        historical: ProjectState,
        live_tasks: dict[str, TaskAuthorityView],
        live_decisions: dict[str, DecisionAuthorityView],
        authority: AuthorityContext,
    ) -> ProjectState:
        """Apply current subsystem projections without replaying past gates."""
        if any(task_id not in live_tasks for task_id in historical.tasks):
            historical.health_flags.append("STALE_AUTHORITATIVE_PROJECTION")
        if any(decision_id not in live_decisions for decision_id in historical.decisions):
            historical.health_flags.append("STALE_AUTHORITATIVE_PROJECTION")
        for task_id, task_view in live_tasks.items():
            historical.tasks[task_id] = task_view
        for decision_id, decision_view in live_decisions.items():
            historical.decisions[decision_id] = decision_view
        self.reducer._compute_projections(historical, authority)
        return historical

    def append_governance_evaluation(
        self,
        project_id: str,
        evaluation_type: Literal["dor", "dod"],
        *,
        actor: str,
        evidence_refs: Sequence[str] = (),
        event_id: str | None = None,
    ) -> ProjectEvent:
        """Evaluate current canonical authority and append immutable gate evidence.

        This is the trusted Phase-4 boundary for ``dor.evaluated`` and
        ``dod.evaluated``.  Callers cannot mint a passed boolean by selecting an
        event type: the service resolves current subsystem objects, verifies
        their receipts, validates prior canonical evidence, binds rules and
        event identity, and only then writes the evaluation record.
        """
        if not actor.strip():
            raise ValueError("actor must be non-empty")

        canonical_events = self._read_canonical_events(project_id)
        expected_sequence = canonical_events[-1].sequence if canonical_events else 0
        expected_hash = canonical_events[-1].event_hash if canonical_events else ""
        authority, live_tasks, live_decisions = self._assemble_authority(canonical_events)
        historical = self.reducer.reduce_internal(
            canonical_events,
            project_id=project_id,
            authority=authority,
        )
        candidate = self._apply_current_overlay(
            historical,
            dict(live_tasks),
            dict(live_decisions),
            authority,
        )
        required_evidence = sorted({ref.strip() for ref in evidence_refs if ref.strip()})
        if any(ref not in historical.attached_evidence for ref in required_evidence):
            raise ValueError("Governance evaluation requires prior canonical evidence")

        result: DoREvaluation | DoDEvaluation
        if evaluation_type == "dor":
            target_phase = (
                ProjectPhase.PLANNING
                if candidate.current_phase == ProjectPhase.DISCOVERY
                else ProjectPhase.EXECUTION
            )
            result = self.reducer.governance_engine.evaluate_dor(candidate, target_phase)
        else:
            target_phase = (
                ProjectPhase.CLOSED
                if candidate.current_phase == ProjectPhase.CLOSING
                else ProjectPhase.CLOSING
            )
            preview_payload = {
                "target_phase": target_phase.value,
                "evidence_refs": required_evidence,
            }
            preview_timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            preview_raw: dict[str, object] = {
                "event_id": event_id or f"evt_{project_id}_{uuid.uuid4().hex[:12]}",
                "schema_version": "power.project-event.v1",
                "project_id": project_id,
                "sequence": expected_sequence + 1,
                "timestamp": preview_timestamp,
                "actor": actor,
                "source": "pse_governance",
                "session_id": None,
                "event_type": "project.phase.changed",
                "payload": preview_payload,
                "payload_digest": compute_payload_digest(preview_payload),
                "prev_event_hash": expected_hash,
                "artifact_refs": [],
                "evidence_refs": required_evidence,
                "correlation_id": None,
                "causation_id": None,
                "idempotency_key": None,
            }
            preview_raw["event_hash"] = compute_event_hash(preview_raw)
            preview_event = ProjectEvent.model_validate(preview_raw)
            result = self.reducer.governance_engine.evaluate_dod(
                candidate,
                target_phase,
                event=preview_event,
                authority=authority,
            )
        if not result.passed:
            failure_codes = result.reason_codes
            if isinstance(result, DoDEvaluation):
                failure_codes = result.reason_codes or result.failed_conditions
            raise ValueError(
                f"{evaluation_type.upper()} evaluation failed: {sorted(failure_codes)}"
            )

        resolved_event_id = event_id or f"evt_{project_id}_{uuid.uuid4().hex[:12]}"
        active_task_ids, _active_decision_ids = self._collect_ids(canonical_events)
        if target_phase != ProjectPhase.PLANNING and set(live_tasks) != active_task_ids:
            missing = sorted(active_task_ids - set(live_tasks))
            raise ValueError(
                "Governance evaluation requires canonical TaskStore authority for active tasks: "
                + ", ".join(missing)
            )
        evaluation = HistoricalGovernanceEvaluation(
            evaluation_type=evaluation_type,
            result="passed",
            evaluated_from_phase=candidate.current_phase,
            evaluated_phase=target_phase,
            evaluation_event_id=resolved_event_id,
            task_views=[live_tasks[task_id] for task_id in sorted(live_tasks)],
            decision_views=[live_decisions[decision_id] for decision_id in sorted(live_decisions)],
            approved_decision_ids=sorted(
                decision_id
                for decision_id, view in live_decisions.items()
                if view.status == "approved" and decision_id in authority.approved_decision_ids
            ),
            verified_task_receipts=sorted(authority.verified_task_receipts),
            required_evidence_refs=required_evidence,
            accountable_actor=authority.accountable_actor,
            rules_version=self.reducer.rules_version,
            rules_digest=RULES_DIGEST,
        )
        command = self._governance_append_command(
            project_id=project_id,
            event_type=f"{evaluation_type}.evaluated",
            payload=evaluation.model_dump(mode="json"),
            actor=actor,
            event_id=resolved_event_id,
            evidence_refs=required_evidence,
        )
        return self._canonical_store(project_id)._append_governed(
            command,
            expected_last_sequence=expected_sequence,
            expected_last_event_hash=expected_hash,
        )

    def append_governed_gate_override(
        self,
        project_id: str,
        gate: str,
        *,
        actor: str,
        reason: str,
        approved_by: str,
        evidence_refs: Sequence[str],
    ) -> ProjectEvent:
        """Validate and append a canonical gate override through PSE authority."""
        if not gate.strip() or not reason.strip() or not approved_by.strip():
            raise ValueError("gate, reason, and approved_by must be non-empty")
        canonical_events = self._read_canonical_events(project_id)
        authority, _live_tasks, _live_decisions = self._assemble_authority(canonical_events)
        historical = self.reducer.reduce_internal(
            canonical_events,
            project_id=project_id,
            authority=authority,
        )
        refs = sorted({ref.strip() for ref in evidence_refs if ref.strip()})
        if not refs or any(ref not in historical.attached_evidence for ref in refs):
            raise ValueError("Gate override requires prior canonical evidence")

        store = self._canonical_store(project_id)
        verification = store.verify()
        event_id = f"evt_{project_id}_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload = {
            "gate": gate,
            "overridden_by": actor,
            "reason": reason,
            "approved_by": approved_by,
            "evidence_refs": refs,
        }
        raw_envelope: dict[str, object] = {
            "event_id": event_id,
            "schema_version": "power.project-event.v1",
            "project_id": project_id,
            "sequence": verification.last_sequence + 1,
            "timestamp": timestamp,
            "actor": actor,
            "source": "pse_governance",
            "session_id": None,
            "event_type": "gate.overridden",
            "payload": payload,
            "payload_digest": compute_payload_digest(payload),
            "prev_event_hash": verification.last_event_hash,
            "artifact_refs": [],
            "evidence_refs": refs,
            "correlation_id": None,
            "causation_id": None,
            "idempotency_key": None,
        }
        raw_envelope["event_hash"] = compute_event_hash(raw_envelope)
        candidate = ProjectEvent.model_validate(raw_envelope)
        effective_authority = self.reducer._effective_authority(historical, authority)
        if effective_authority is None:
            raise AuthoritativeStateError("Gate override requires historical authority context")
        evaluation = self.reducer.governance_engine.evaluate_gate_override(
            candidate,
            effective_authority,
        )
        if evaluation.decision.value != "ALLOW":
            raise AuthoritativeStateError(
                "Gate override rejected by canonical governance: "
                + ", ".join(evaluation.reason_codes)
            )
        command = AppendCommand(
            project_id=project_id,
            event_type="gate.overridden",
            payload=payload,
            actor=actor,
            source="pse_governance",
            event_id=event_id,
            timestamp=timestamp,
            evidence_refs=refs,
        )
        return store._append_governed(
            command,
            expected_last_sequence=verification.last_sequence,
            expected_last_event_hash=verification.last_event_hash,
        )

    @staticmethod
    def _governance_append_command(
        *,
        project_id: str,
        event_type: str,
        payload: dict[str, object],
        actor: str,
        event_id: str,
        evidence_refs: list[str],
    ) -> AppendCommand:
        """Build a governed append command without exposing ledger fields."""
        return AppendCommand(
            project_id=project_id,
            event_type=event_type,
            payload=payload,
            actor=actor,
            source="pse_governance",
            event_id=event_id,
            evidence_refs=evidence_refs,
        )

    def rebuild_from_candidates(
        self, project_id: str, candidate_events: Sequence[ProjectEvent]
    ) -> ProjectState:
        """Attempt an authoritative rebuild from caller-supplied events.

        Rejects fail-closed unless the candidates are an exact, ordered,
        byte-identical replay of the canonical ledger (membership proof by
        trusted re-read, never by caller hashes).
        """
        canonical_events = self._read_canonical_events(project_id)
        supplied = [
            e if isinstance(e, ProjectEvent) else ProjectEvent.model_validate(e)
            for e in candidate_events
        ]
        if len(supplied) != len(canonical_events):
            raise AuthoritativeStateError(
                "AUTHORITATIVE STATE = REJECTED: candidate stream length "
                f"({len(supplied)}) != canonical ledger length ({len(canonical_events)})"
            )
        for supplied_event, canonical_event in zip(supplied, canonical_events, strict=True):
            if supplied_event.model_dump() != canonical_event.model_dump():
                raise AuthoritativeStateError(
                    "AUTHORITATIVE STATE = REJECTED: candidate event "
                    f"'{supplied_event.event_id}' is not a canonical ledger member"
                )
        authority, live_tasks, live_decisions = self._assemble_authority(canonical_events)
        historical = self.reducer.reduce_internal(
            canonical_events,
            project_id=project_id,
            authority=authority,
        )
        return self._apply_current_overlay(historical, live_tasks, live_decisions, authority)

    def restore_snapshot_authoritative(self, snapshot: ProjectStateSnapshot) -> ProjectState:
        """Restore historical prefix/tail first, then compose current overlay."""
        if not snapshot.verify_integrity():
            raise SnapshotIntegrityError(
                f"AUTHORITATIVE RESTORE = REJECTED: snapshot integrity failed for {snapshot.project_id}"
            )
        if (
            snapshot.schema_version != self.reducer.schema_version
            or snapshot.rules_version != self.reducer.rules_version
            or snapshot.state.schema_version != snapshot.schema_version
            or snapshot.state.rules_version != snapshot.rules_version
            or not snapshot.state.rules_digest
            or snapshot.state.rules_digest != RULES_DIGEST
        ):
            raise SnapshotIntegrityError(
                "AUTHORITATIVE RESTORE = REJECTED: snapshot schema/rules binding mismatch"
            )
        canonical_events = self._read_canonical_events(snapshot.project_id)
        head_seq = canonical_events[-1].sequence if canonical_events else 0
        if snapshot.last_event_sequence > head_seq:
            raise SnapshotIntegrityError(
                "AUTHORITATIVE RESTORE = REJECTED: snapshot sequence beyond canonical head"
            )

        authority, live_tasks, live_decisions = self._assemble_authority(canonical_events)
        prefix = [
            event for event in canonical_events if event.sequence <= snapshot.last_event_sequence
        ]
        if prefix:
            prefix_head = prefix[-1]
            if prefix_head.sequence != snapshot.last_event_sequence:
                raise SnapshotIntegrityError(
                    "AUTHORITATIVE RESTORE = REJECTED: snapshot prefix sequence mismatch"
                )
            if prefix_head.event_hash != snapshot.last_event_hash:
                raise SnapshotIntegrityError(
                    "AUTHORITATIVE RESTORE = REJECTED: snapshot prefix hash mismatch"
                )
        elif snapshot.last_event_sequence != 0 or snapshot.last_event_hash:
            raise SnapshotIntegrityError(
                "AUTHORITATIVE RESTORE = REJECTED: snapshot lineage mismatch vs canonical ledger"
            )

        historical_prefix = self.reducer.reduce_internal(
            prefix,
            project_id=snapshot.project_id,
            authority=authority,
        )
        historical_fields = (
            "current_phase",
            "owner",
            "phase_history",
            "raci",
            "attached_evidence",
            "evidence_kinds",
            "historical_approved_decisions",
            "historical_task_receipts",
            "historical_evaluations",
            "historical_gate_evaluations",
            "historical_gate_origins",
            "overridden_gates",
            "risks",
            "issues",
            "assumptions",
            "dependencies",
            "contributing_events",
            "last_event_sequence",
            "last_event_hash",
            "schema_version",
            "rules_version",
            "rules_digest",
        )
        for field_name in historical_fields:
            if getattr(snapshot.state, field_name) != getattr(historical_prefix, field_name):
                raise SnapshotIntegrityError(
                    "AUTHORITATIVE RESTORE = REJECTED: snapshot historical state mismatch"
                )

        tail = [
            event for event in canonical_events if event.sequence > snapshot.last_event_sequence
        ]
        restored = historical_prefix
        if tail:
            restored = self.reducer.reduce_internal(
                tail,
                initial_state=historical_prefix,
                project_id=snapshot.project_id,
                authority=authority,
            )
        return self._apply_current_overlay(restored, live_tasks, live_decisions, authority)


ProjectStateEngine = ProjectStateService

__all__ = [
    "AuthoritativeStateError",
    "ProjectStateEngine",
    "ProjectStateService",
]
