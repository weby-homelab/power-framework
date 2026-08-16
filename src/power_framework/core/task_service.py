"""Canonical task coordination service for POWER Task Manager v2."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .task_models import PowerTask, TaskAuthority, TaskEvent, TaskKind, TaskPriority, TaskState
from .task_store import TaskStore

logger = logging.getLogger(__name__)


class TaskService:
    """Canonical domain service managing task lifecycles, revisions, and events."""

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self.store = TaskStore(self.vault_dir)

    def create_task(
        self,
        *,
        task_id: str,
        title: str,
        objective: str = "",
        owner: str = "local",
        assignee: str | None = None,
        state: TaskState = "backlog",
        priority: TaskPriority = "normal",
        kind: TaskKind = "human",
        scope: list[str] | None = None,
        authority: TaskAuthority = "read-only",
        dependencies: list[str] | None = None,
        next_action: str = "inspect",
        open_gates: list[str] | None = None,
        required_input: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        receipt_ids: list[str] | None = None,
        external_refs: dict[str, str] | None = None,
        due_at: str | None = None,
        actor: str = "local",
    ) -> PowerTask:
        """Create a new durable PowerTask v2 with initial event."""
        with self.store.lock():
            existing = self.store.get_task(task_id)
            if existing:
                raise ValueError(f"Task with ID {task_id} already exists")

            now_iso = datetime.now(UTC).isoformat()
            task = PowerTask(
                task_id=task_id,
                vault_id="default",
                tenant_id="local",
                kind=kind,
                title=title,
                objective=objective,
                owner=owner,
                assignee=assignee,
                state=state,
                priority=priority,
                scope=scope or [],
                authority=authority,
                dependencies=dependencies or [],
                next_action=next_action,
                open_gates=open_gates or [],
                required_input=required_input,
                artifact_refs=artifact_refs or [],
                receipt_ids=receipt_ids or [],
                external_refs=external_refs or {},
                revision=1,
                created_at=now_iso,
                updated_at=now_iso,
                due_at=due_at,
            )

            event = TaskEvent.create(
                task_id=task_id,
                sequence=1,
                actor=actor,
                event_type="task_created",
                payload={"initial_state": state, "title": title, "owner": owner},
                prev_event_digest="",
            )

            self.store.save_task(task, event=event)
            return task

    def transition_task(
        self,
        task_id: str,
        new_state: TaskState,
        *,
        actor: str = "local",
        expected_revision: int | None = None,
        receipt_id: str | None = None,
        next_action: str | None = None,
        assignee: str | None = None,
        required_input: dict[str, Any] | None = None,
        open_gates: list[str] | None = None,
        error_ref: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> PowerTask:
        """Advance task state machine with optimistic concurrency and invariant validation."""
        with self.store.lock():
            task = self.store.get_task(task_id)
            if not task:
                raise FileNotFoundError(f"Task {task_id} not found")

            if expected_revision is not None and task.revision != expected_revision:
                raise ValueError(
                    f"Revision conflict for task {task_id}: expected {expected_revision}, found {task.revision}"
                )

            # Validate state transition rules
            task.validate_transition(new_state, receipt_id=receipt_id, actor=actor)

            prev_state = task.state
            task.state = new_state
            task.revision += 1
            task.updated_at = datetime.now(UTC).isoformat()

            if receipt_id and receipt_id not in task.receipt_ids:
                task.receipt_ids.append(receipt_id)
            if next_action is not None:
                task.next_action = next_action
            if assignee is not None:
                task.assignee = assignee
            if required_input is not None:
                task.required_input = required_input
            if open_gates is not None:
                task.open_gates = open_gates
            if error_ref is not None:
                task.error_ref = error_ref

            if values:
                for k, v in values.items():
                    if hasattr(task, k) and k not in {"task_id", "revision", "created_at"}:
                        setattr(task, k, v)

            last_digest = self.store.get_last_event_digest(task_id)
            next_seq = task.revision

            event = TaskEvent.create(
                task_id=task_id,
                sequence=next_seq,
                actor=actor,
                event_type="state_transition",
                payload={
                    "from_state": prev_state,
                    "to_state": new_state,
                    "receipt_id": receipt_id,
                    "next_action": task.next_action,
                },
                prev_event_digest=last_digest,
            )

            self.store.save_task(task, event=event)
            return task

    def get_task(self, task_id: str) -> PowerTask | None:
        """Get a task by ID."""
        return self.store.get_task(task_id)

    def list_tasks(
        self,
        *,
        state: str | None = None,
        owner: str | None = None,
        assignee: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PowerTask]:
        """List tasks matching filters."""
        return self.store.list_tasks(
            state=state, owner=owner, assignee=assignee, limit=limit, offset=offset
        )

    def get_events(self, task_id: str, since_sequence: int = 0) -> list[TaskEvent]:
        """Get event stream for a task."""
        return self.store.get_task_events(task_id, since_sequence=since_sequence)

    def migrate_v1_work_packets(self) -> dict[str, Any]:
        """Migrate existing .power/work-packets/ v1 JSONs into PowerTask v2."""
        v1_dir = self.vault_dir / ".power" / "work-packets"
        if not v1_dir.is_dir():
            return {"migrated": 0, "skipped": 0, "errors": 0}

        migrated = 0
        skipped = 0
        errors = 0

        for packet_file in v1_dir.glob("*.json"):
            try:
                import json

                data = json.loads(packet_file.read_text(encoding="utf-8"))
                task_id = data.get("task_id") or packet_file.stem
                if self.store.get_task(task_id):
                    skipped += 1
                    continue

                v1_state = data.get("state", "submitted")
                mapped_state: TaskState = "ready"
                if v1_state in {"working", "input-required", "completed", "failed", "canceled"}:
                    mapped_state = cast("TaskState", v1_state)

                task = PowerTask(
                    task_id=task_id,
                    vault_id="default",
                    tenant_id="local",
                    kind="agent" if data.get("profile") == "maintenance" else "human",
                    title=f"Migrated Task {task_id}",
                    objective=data.get("objective", ""),
                    owner=data.get("owner", "local"),
                    assignee=None,
                    state=mapped_state,
                    priority="normal",
                    scope=data.get("scope", []),
                    authority=data.get("authority", "read-only"),
                    next_action=data.get("next_action", "inspect"),
                    receipt_ids=[data.get("last_receipt_id")]
                    if data.get("last_receipt_id")
                    else [],
                    revision=len(data.get("checkpoints", [])) + 1,
                    created_at=data.get("created_at", datetime.now(UTC).isoformat()),
                    updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
                )

                ev = TaskEvent.create(
                    task_id=task_id,
                    sequence=1,
                    actor="migration_v1",
                    event_type="migrated_from_v1",
                    payload={"original_file": packet_file.name},
                )
                self.store.save_task(task, event=ev)
                migrated += 1
            except Exception as exc:
                logger.error("Failed to migrate packet %s: %s", packet_file, exc)
                errors += 1

        return {"migrated": migrated, "skipped": skipped, "errors": errors}


__all__ = ["TaskService"]
