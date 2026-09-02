"""Canonical task coordination service for POWER Task Manager v2."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .errors import ConflictError
from .task_models import (
    PowerTask,
    TaskAuthority,
    TaskCompletionReceipt,
    TaskEvent,
    TaskKind,
    TaskPriority,
    TaskState,
)
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
        source_revision: str = "",
        next_action: str = "inspect",
        open_gates: list[str] | None = None,
        required_input: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        receipt_ids: list[str] | None = None,
        external_refs: dict[str, str] | None = None,
        due_at: str | None = None,
        actor: str = "local",
        idempotency_key: str | None = None,
    ) -> PowerTask:
        """Create a new durable PowerTask v2 with initial event."""
        command_sha256 = _command_fingerprint(
            "create",
            {
                "task_id": task_id,
                "title": title,
                "objective": objective,
                "owner": owner,
                "assignee": assignee,
                "state": state,
                "priority": priority,
                "kind": kind,
                "scope": scope or [],
                "authority": authority,
                "dependencies": dependencies or [],
                "source_revision": source_revision,
                "next_action": next_action,
                "open_gates": open_gates or [],
                "required_input": required_input,
                "artifact_refs": artifact_refs or [],
                "receipt_ids": receipt_ids or [],
                "external_refs": external_refs or {},
                "due_at": due_at,
            },
        )
        with self.store.lock():
            existing = self.store.get_task(task_id)
            if existing:
                replay = self._find_idempotent_result(task_id, idempotency_key, command_sha256)
                if replay is not None:
                    return replay
                raise ConflictError(f"Task with ID {task_id} already exists")

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
                source_revision=source_revision,
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
                payload={
                    "initial_state": state,
                    "title": title,
                    "owner": owner,
                    "idempotency_key": idempotency_key,
                    "command_sha256": command_sha256,
                    "result": task.model_dump(),
                },
                prev_event_digest="",
            )

            self.store.save_task(
                task,
                event=event,
                idempotency_key=idempotency_key,
                command_sha256=command_sha256,
                crash_point="task.create",
            )
            return task

    def transition_task(
        self,
        task_id: str,
        new_state: TaskState,
        *,
        actor: str = "local",
        expected_revision: int | None = None,
        receipt_id: str | None = None,
        completion_postcondition: str | None = None,
        completion_artifact_refs: list[str] | None = None,
        idempotency_key: str | None = None,
        next_action: str | None = None,
        assignee: str | None = None,
        required_input: dict[str, Any] | None = None,
        open_gates: list[str] | None = None,
        error_ref: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> PowerTask:
        """Advance task state machine with optimistic concurrency and invariant validation."""
        command_sha256 = _command_fingerprint(
            "transition",
            {
                "task_id": task_id,
                "new_state": new_state,
                "expected_revision": expected_revision,
                "receipt_id": receipt_id,
                "completion_postcondition": completion_postcondition,
                "completion_artifact_refs": completion_artifact_refs,
                "next_action": next_action,
                "assignee": assignee,
                "required_input": required_input,
                "open_gates": open_gates,
                "error_ref": error_ref,
                "values": values,
            },
        )
        with self.store.lock():
            task = self.store.get_task(task_id)
            if not task:
                raise FileNotFoundError(f"Task {task_id} not found")

            replay = self._find_idempotent_result(task_id, idempotency_key, command_sha256)
            if replay is not None:
                return replay

            if expected_revision is not None and task.revision != expected_revision:
                raise ConflictError(
                    f"Revision conflict for task {task_id}: expected {expected_revision}, found {task.revision}"
                )

            completion_receipt = None
            if new_state == "completed":
                if expected_revision is None:
                    raise ValueError("Completion requires expected_revision")
                if receipt_id is not None:
                    completion_receipt = self.store.get_completion_receipt(receipt_id)
                    if completion_receipt is None:
                        raise ValueError("Completion receipt does not exist")
                    if (
                        completion_receipt.task_id != task_id
                        or completion_receipt.task_revision != task.revision + 1
                    ):
                        raise ValueError("Completion receipt is not bound to this task revision")
                else:
                    completion_receipt = self._build_completion_receipt(
                        task,
                        actor=actor,
                        postcondition=completion_postcondition,
                        artifact_refs=completion_artifact_refs,
                    )
                    receipt_id = completion_receipt.receipt_id

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
                mutable_fields = {
                    "next_action",
                    "assignee",
                    "required_input",
                    "open_gates",
                    "error_ref",
                    "artifact_refs",
                    "external_refs",
                    "max_attempts",
                    "retry_at",
                    "lease_owner",
                    "lease_expires_at",
                    "heartbeat_at",
                    "execution_state",
                    "dead_letter_reason",
                    "due_at",
                }
                unknown_fields = set(values) - mutable_fields
                if unknown_fields:
                    raise ValueError(
                        "Task update contains immutable or unknown fields: "
                        + ", ".join(sorted(unknown_fields))
                    )
                candidate = task.model_dump()
                candidate.update(values)
                task = PowerTask.model_validate(candidate)

            last_digest = self.store.get_last_event_digest(task_id)
            existing_events = self.store.get_task_events(task_id)
            next_seq = existing_events[-1].sequence + 1 if existing_events else 1

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
                    "idempotency_key": idempotency_key,
                    "command_sha256": command_sha256,
                    "result": task.model_dump(),
                },
                prev_event_digest=last_digest,
            )

            self.store.save_task(
                task,
                event=event,
                completion_receipt=completion_receipt,
                idempotency_key=idempotency_key,
                command_sha256=command_sha256,
                crash_point="task.transition",
            )
            return task

    def _find_idempotent_result(
        self,
        task_id: str,
        idempotency_key: str | None,
        command_sha256: str,
    ) -> PowerTask | None:
        if idempotency_key is None:
            return None
        for event in self.store.get_task_events(task_id):
            if event.payload.get("idempotency_key") != idempotency_key:
                continue
            if event.payload.get("command_sha256") != command_sha256:
                raise ValueError("Idempotency key was reused for a different task command")
            result = event.payload.get("result")
            if not isinstance(result, dict):
                raise ValueError("Idempotent task event is missing its result snapshot")
            return PowerTask.model_validate(result)
        return None

    def _build_completion_receipt(
        self,
        task: PowerTask,
        *,
        actor: str,
        postcondition: str | None,
        artifact_refs: list[str] | None,
    ) -> TaskCompletionReceipt:
        if not isinstance(postcondition, str) or not postcondition.strip():
            raise ValueError("Completion requires a verified postcondition")
        refs = artifact_refs if artifact_refs is not None else task.artifact_refs
        if not refs:
            raise ValueError("Completion requires at least one verifiable artifact")

        artifact_digests: dict[str, str] = {}
        for rel_path in refs:
            if not isinstance(rel_path, str) or not rel_path.strip():
                raise ValueError("Completion artifact references must be non-empty paths")
            raw_path = Path(rel_path)
            if (
                raw_path.is_absolute()
                or "\\" in rel_path
                or any(part in {"", ".", ".."} for part in raw_path.parts)
            ):
                raise ValueError("Completion artifact path is invalid")
            candidate = (self.vault_dir / raw_path).resolve(strict=True)
            try:
                canonical_rel = candidate.relative_to(self.vault_dir).as_posix()
            except ValueError as exc:
                raise ValueError("Completion artifact escapes the vault") from exc
            if not candidate.is_file():
                raise ValueError("Completion artifact must be an existing file")
            artifact_digests[canonical_rel] = hashlib.sha256(candidate.read_bytes()).hexdigest()

        postcondition_sha256 = hashlib.sha256(postcondition.strip().encode("utf-8")).hexdigest()
        receipt_payload: dict[str, object] = {
            "task_id": task.task_id,
            "task_revision": task.revision + 1,
            "completion_policy": task.completion_policy,
            "postcondition_sha256": postcondition_sha256,
            "artifact_digests": artifact_digests,
            "actor": actor,
        }
        digest = hashlib.sha256(
            json.dumps(receipt_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return TaskCompletionReceipt(
            receipt_id=f"tcr_{digest}",
            task_id=task.task_id,
            task_revision=task.revision + 1,
            completion_policy=task.completion_policy,
            postcondition_sha256=postcondition_sha256,
            artifact_digests=artifact_digests,
            actor=actor,
        )

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
        """Migrate existing .power/work-packets/ v1 JSONs into PowerTask v2.

        Idempotent (re-run skips migrated tasks), recoverable (interrupt-safe:
        each packet is committed before the next), reversible (a content-free
        manifest + retained v1 originals enable :meth:`rollback_v1_migration`).
        The original v1 bytes are copied to a backup directory and never deleted
        by migration (Phase I).
        """
        import json

        control_dir = self.store.power_dir
        v1_dir = control_dir / "work-packets"
        if not v1_dir.is_dir():
            return {"migrated": 0, "skipped": 0, "errors": 0}

        backup_dir = control_dir / "migration" / "v1-backup"
        manifest_path = control_dir / "migration" / "v1_manifest.json"
        manifest = self._read_migration_manifest(manifest_path)
        migrated_ids = {e["task_id"] for e in manifest.get("entries", [])}

        migrated = 0
        skipped = 0
        errors = 0

        for packet_file in sorted(v1_dir.glob("*.json")):
            try:
                data = json.loads(packet_file.read_text(encoding="utf-8"))
                task_id = data.get("task_id") or packet_file.stem
                if task_id in migrated_ids or self.store.get_task(task_id):
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
                    payload={
                        "original_file": packet_file.name,
                        "checkpoint_count": len(data.get("checkpoints", [])),
                    },
                )
                # Retain original v1 bytes before any further action.
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_file = backup_dir / packet_file.name
                if not backup_file.exists():
                    backup_file.write_bytes(packet_file.read_bytes())
                source_sha256 = hashlib.sha256(packet_file.read_bytes()).hexdigest()

                self.store.save_task(task, event=ev, crash_point="task.migrate")
                manifest.setdefault("entries", []).append(
                    {
                        "task_id": task_id,
                        "source_sha256": source_sha256,
                        "revision": task.revision,
                        "event_sequence": 1,
                        "status": "migrated",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                self._write_migration_manifest(manifest_path, manifest)
                migrated += 1
            except Exception as exc:
                logger.error("Failed to migrate packet %s: %s", packet_file, exc)
                errors += 1

        return {
            "migrated": migrated,
            "skipped": skipped,
            "errors": errors,
            "manifest": str(manifest_path),
        }

    def _read_migration_manifest(self, path: Path) -> dict[str, Any]:
        if path.is_file():
            try:
                return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                return {"entries": []}
        return {"entries": []}

    @staticmethod
    def _write_migration_manifest(path: Path, manifest: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )

    def rollback_v1_migration(self) -> dict[str, Any]:
        """Reverse :meth:`migrate_v1_work_packets` using the content-free manifest.

        Deletes migrated v2 tasks and restores the retained v1 originals. The
        original v1 evidence is only copied back, never destroyed (Phase I).
        """
        control_dir = self.store.power_dir
        manifest_path = control_dir / "migration" / "v1_manifest.json"
        manifest = self._read_migration_manifest(manifest_path)
        entries = manifest.get("entries", [])
        backup_dir = control_dir / "migration" / "v1-backup"
        v1_dir = control_dir / "work-packets"
        rolled_back = 0
        restored = 0
        for entry in entries:
            task_id = entry["task_id"]
            if self.store.get_task(task_id) is not None:
                self.store.delete_task(task_id)
                rolled_back += 1
            backup_file = backup_dir / f"{task_id}.json"
            if backup_file.is_file():
                v1_dir.mkdir(parents=True, exist_ok=True)
                (v1_dir / f"{task_id}.json").write_bytes(backup_file.read_bytes())
                restored += 1
        if manifest_path.is_file():
            manifest_path.unlink()
        return {"rolled_back": rolled_back, "restored": restored}


__all__ = ["TaskService"]


def _command_fingerprint(operation: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
