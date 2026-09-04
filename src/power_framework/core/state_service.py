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

from pathlib import Path
from typing import TYPE_CHECKING

from power_framework.core.canonical_json import compute_payload_digest
from power_framework.core.decision_service import DecisionService
from power_framework.core.governance_engine import AuthorityContext
from power_framework.core.project_models import LedgerIntegrityError, ProjectEvent
from power_framework.core.project_store import ProjectEventStore
from power_framework.core.state_models import (
    DecisionAuthorityView,
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


_ACCOUNTABLE_ROLES = ("Accountable", "accountable", "A")


class ProjectStateService:
    """Trusted orchestration boundary for authoritative ProjectState."""

    def __init__(
        self,
        vault_root: Path,
        task_service: TaskService | None = None,
        decision_service: DecisionService | None = None,
    ) -> None:
        self.vault_root = Path(vault_root).expanduser().resolve()
        self.task_service: TaskService = task_service or TaskService(self.vault_root)
        self.decision_service: DecisionService = decision_service or DecisionService(
            self.vault_root, task_service=self.task_service
        )
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
        task_ids: set[str] = set()
        decision_ids: set[str] = set()
        for event in events:
            payload = event.payload or {}
            if event.event_type in (
                "task.associated",
                "task.disassociated",
                "task.lifecycle.observed",
            ):
                task_id = payload.get("task_id")
                if isinstance(task_id, str) and task_id.strip():
                    task_ids.add(task_id.strip())
            elif event.event_type in (
                "decision.associated",
                "decision.disassociated",
                "decision.lifecycle.observed",
            ):
                decision_id = payload.get("decision_id")
                if isinstance(decision_id, str) and decision_id.strip():
                    decision_ids.add(decision_id.strip())
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
                if receipt is not None and receipt.decision_id == decision_id:
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
                    and 1 <= receipt.task_revision <= task.revision
                ):
                    verified.add(receipt_id)
        return verified

    def _assemble_authority(
        self, events: Sequence[ProjectEvent]
    ) -> tuple[AuthorityContext, dict[str, TaskAuthorityView], dict[str, DecisionAuthorityView]]:
        """Build the verified normalized authority bundle from canonical sources."""
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
                    raci.setdefault(role.strip(), set()).add(actor.strip())
            elif event.event_type == "raci.revoked":
                payload = event.payload or {}
                role = payload.get("role")
                actor = payload.get("actor")
                if isinstance(role, str) and role.strip() and role.strip() in raci:
                    if isinstance(actor, str) and actor.strip():
                        raci[role.strip()].discard(actor.strip())
                    else:
                        raci[role.strip()].clear()
                    if not raci[role.strip()]:
                        del raci[role.strip()]

        accountable: str | None = None
        for role_key in _ACCOUNTABLE_ROLES:
            actors = sorted(raci.get(role_key, set()))
            if len(actors) == 1:
                accountable = actors[0]
                break
            if len(actors) > 1:
                accountable = None
                break

        authority = AuthorityContext(
            attached_evidence=attached,
            approved_decision_ids=approved_ids,
            raci={role: sorted(actors) for role, actors in raci.items()},
            accountable_actor=accountable,
            verified_task_receipts=self._verified_task_receipts(task_ids),
            permit_accountable_approval=True,
        )
        return authority, live_tasks, live_decisions

    # ------------------------------------------------------------------
    # Authoritative public API
    # ------------------------------------------------------------------
    def rebuild_project_state(self, project_id: str) -> ProjectState:
        """Rebuild authoritative ProjectState from verified canonical sources."""
        canonical_events = self._read_canonical_events(project_id)
        authority, live_tasks, live_decisions = self._assemble_authority(canonical_events)
        return self.reducer.reduce_internal(
            canonical_events,
            tasks=list(live_tasks.values()),
            decisions=list(live_decisions.values()),
            project_id=project_id,
            authority=authority,
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
        return self.reducer.reduce_internal(
            canonical_events,
            tasks=list(live_tasks.values()),
            decisions=list(live_decisions.values()),
            project_id=project_id,
            authority=authority,
        )

    def restore_snapshot_authoritative(self, snapshot: ProjectStateSnapshot) -> ProjectState:
        """Authoritatively restore a snapshot: ledger lineage + live re-resolution.

        (1) verifies snapshot internal integrity; (2) verifies lineage against
        a trusted re-read of the canonical ledger; (3) replays any tail with
        trusted authority; (4) re-resolves current tasks/decisions from their
        canonical subsystems; (5) recomputes readiness/approvals/DoR/DoD/health
        and state_revision. Stale federated truth never becomes canonical.
        """
        if not snapshot.verify_integrity():
            raise SnapshotIntegrityError(
                f"AUTHORITATIVE RESTORE = REJECTED: snapshot integrity failed for {snapshot.project_id}"
            )
        canonical_events = self._read_canonical_events(snapshot.project_id)
        head_seq = canonical_events[-1].sequence if canonical_events else 0
        head_hash = canonical_events[-1].event_hash if canonical_events else ""
        if not self.reducer.verify_snapshot_lineage(snapshot, head_seq, head_hash):
            # Allow snapshot-behind-head only with exact tail linkage.
            if snapshot.last_event_sequence > head_seq:
                raise SnapshotIntegrityError(
                    "AUTHORITATIVE RESTORE = REJECTED: snapshot sequence beyond canonical head"
                )
            tail = [e for e in canonical_events if e.sequence > snapshot.last_event_sequence]
            if tail:
                expected_seq = snapshot.last_event_sequence + 1
                if (
                    tail[0].sequence != expected_seq
                    or tail[0].prev_event_hash != snapshot.last_event_hash
                ):
                    raise SnapshotIntegrityError(
                        "AUTHORITATIVE RESTORE = REJECTED: tail does not link snapshot head"
                    )
            else:
                raise SnapshotIntegrityError(
                    "AUTHORITATIVE RESTORE = REJECTED: snapshot lineage mismatch vs canonical ledger"
                )
            authority_tail, live_tasks, live_decisions = self._assemble_authority(canonical_events)
            restored = self.reducer.restore_from_snapshot(snapshot, tail, authority_tail)
            # Federated re-resolution: live authorities win over snapshot-frozen views.
            for task_id, task_view in live_tasks.items():
                restored.tasks[task_id] = task_view
            for decision_id, decision_view in live_decisions.items():
                restored.decisions[decision_id] = decision_view
            self.reducer._compute_projections(restored, authority_tail)
            return restored
        # Snapshot at canonical head: full authoritative rebuild guarantees
        # live federated truth (snapshot never freezes external authority).
        return self.rebuild_project_state(snapshot.project_id)


ProjectStateEngine = ProjectStateService

__all__ = [
    "AuthoritativeStateError",
    "ProjectStateEngine",
    "ProjectStateService",
]
