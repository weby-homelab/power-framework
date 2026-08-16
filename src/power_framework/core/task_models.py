"""State machine, invariants, and transition validation for POWER Task Manager v2."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskState = Literal[
    "backlog",
    "ready",
    "submitted",
    "working",
    "input-required",
    "auth-required",
    "blocked",
    "completed",
    "failed",
    "canceled",
    "rejected",
]

TaskPriority = Literal["low", "normal", "high", "critical"]
TaskAuthority = Literal["read-only", "propose", "apply"]
TaskKind = Literal["human", "agent", "maintenance", "fleet", "federated"]
ExecutionState = Literal[
    "none", "queued", "leased", "running", "retry-wait", "waiting-network", "dead-letter"
]

TERMINAL_STATES: set[TaskState] = {"completed", "failed", "canceled", "rejected"}

# Allowed transitions mapping: from_state -> set of allowed to_states
VALID_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    "backlog": {"ready", "submitted", "working", "canceled"},
    "ready": {
        "backlog",
        "working",
        "input-required",
        "auth-required",
        "blocked",
        "canceled",
        "rejected",
    },
    "submitted": {
        "backlog",
        "ready",
        "working",
        "input-required",
        "auth-required",
        "blocked",
        "canceled",
        "rejected",
    },
    "working": {
        "ready",
        "completed",
        "failed",
        "blocked",
        "input-required",
        "auth-required",
        "canceled",
    },
    "input-required": {"working", "ready", "canceled", "failed"},
    "auth-required": {"working", "ready", "canceled", "failed", "rejected"},
    "blocked": {"ready", "working", "canceled", "failed"},
    "completed": set(),
    "failed": set(),
    "canceled": set(),
    "rejected": set(),
}


class PowerTask(BaseModel):
    """Canonical PowerTask v2 domain entity."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    vault_id: str = Field(default="default", max_length=64)
    tenant_id: str = Field(default="local", max_length=64)
    kind: TaskKind = "human"
    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(default="", max_length=4096)
    owner: str = Field(default="local", max_length=64)
    assignee: str | None = Field(default=None, max_length=64)
    state: TaskState = "backlog"
    priority: TaskPriority = "normal"
    scope: list[str] = Field(default_factory=list)
    authority: TaskAuthority = "read-only"
    dependencies: list[str] = Field(default_factory=list)
    source_revision: str = Field(default="", max_length=128)
    next_action: str = Field(default="inspect", max_length=512)
    open_gates: list[str] = Field(default_factory=list)
    required_input: dict[str, Any] | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    external_refs: dict[str, str] = Field(default_factory=dict)
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_at: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    execution_state: ExecutionState = "none"
    error_ref: str | None = None
    dead_letter_reason: str | None = None
    revision: int = Field(default=1, ge=1)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    due_at: str | None = None
    completion_policy: str = Field(default="standard", max_length=64)

    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.state in TERMINAL_STATES

    def can_transition_to(self, new_state: TaskState) -> bool:
        """Validate if transition to new_state is allowed."""
        if self.state == new_state:
            return True
        return new_state in VALID_TRANSITIONS.get(self.state, set())

    def validate_transition(
        self,
        new_state: TaskState,
        *,
        receipt_id: str | None = None,
        actor: str = "local",
    ) -> None:
        """Enforce strict transition invariants."""
        if self.is_terminal() and new_state != self.state:
            raise ValueError(
                f"Cannot transition terminal task {self.task_id} from {self.state} to {new_state}"
            )
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Illegal state transition for task {self.task_id}: {self.state} -> {new_state}"
            )
        if new_state == "completed" and not receipt_id and not self.receipt_ids:
            raise ValueError("Transition to completed requires a terminal receipt ID")


class TaskEvent(BaseModel):
    """Append-only task lifecycle event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    task_id: str
    sequence: int = Field(ge=1)
    actor: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_digest: str
    prev_event_digest: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def create(
        cls,
        task_id: str,
        sequence: int,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
        prev_event_digest: str = "",
    ) -> TaskEvent:
        event_id = f"evt_{task_id}_{sequence}_{int(datetime.now(UTC).timestamp() * 1000)}"
        payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        return cls(
            event_id=event_id,
            task_id=task_id,
            sequence=sequence,
            actor=actor,
            event_type=event_type,
            payload=payload,
            payload_digest=payload_digest,
            prev_event_digest=prev_event_digest,
        )


__all__ = [
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
    "ExecutionState",
    "PowerTask",
    "TaskAuthority",
    "TaskEvent",
    "TaskKind",
    "TaskPriority",
    "TaskState",
]
