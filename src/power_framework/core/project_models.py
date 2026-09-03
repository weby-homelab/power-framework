"""Pydantic v2 Models for POWER Project State Engine (PSE) Phase 2.

Defines schemas and invariants for:
- ProjectEvent v1 (canonical append-only ledger events)
- AppendCommand (external client command interface)
- PrivacyMode & RedactionRecord
- Saga payload models for Task/Decision cross-subsystem integration
- Ledger verification results
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LedgerIntegrityError(Exception):
    """Raised when ledger integrity verification fails due to corruption, schema mismatch, or tampering."""


class IdempotencyConflictError(ValueError):
    """Raised when an append command reuses an idempotency key with conflicting payload or parameters."""


PROJECT_ID_REGEX = r"^prj_[a-z0-9][a-z0-9_-]{2,63}$"
EVENT_ID_REGEX = r"^evt_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
TIMESTAMP_REGEX = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|\+00:00)$"
HASH_REGEX = r"^[0-9a-f]{64}$"
PREV_HASH_REGEX = r"^([0-9a-f]{64})?$"

_PROJECT_ID_COMPILED = re.compile(PROJECT_ID_REGEX)
_EVENT_ID_COMPILED = re.compile(EVENT_ID_REGEX)


def validate_project_id(project_id: str) -> str:
    """Validate project ID against strict regex and bounds, rejecting path traversal."""
    if not isinstance(project_id, str):
        raise ValueError(f"project_id must be a string, got {type(project_id).__name__}")
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise ValueError(f"Path traversal characters forbidden in project_id: {project_id}")
    if not _PROJECT_ID_COMPILED.match(project_id):
        raise ValueError(f"Invalid project_id format: {project_id}. Must match {PROJECT_ID_REGEX}")
    return project_id


def validate_event_id(event_id: str) -> str:
    """Validate event ID against strict regex."""
    if not isinstance(event_id, str):
        raise ValueError(f"event_id must be a string, got {type(event_id).__name__}")
    if not _EVENT_ID_COMPILED.match(event_id):
        raise ValueError(f"Invalid event_id format: {event_id}. Must match {EVENT_ID_REGEX}")
    return event_id


PROJECT_EVENT_TYPES: set[str] = {
    "project.created",
    "project.updated",
    "project.renamed",
    "project.relocated",
    "project.phase.proposed",
    "project.phase.changed",
    "project.archived",
    "project.reopened",
    "session.started",
    "session.ended",
    "task.association.requested",
    "task.associated",
    "task.disassociated",
    "task.association.failed",
    "task.lifecycle.observed",
    "decision.association.requested",
    "decision.associated",
    "decision.disassociated",
    "decision.association.failed",
    "decision.lifecycle.observed",
    "risk.opened",
    "risk.updated",
    "risk.closed",
    "assumption.created",
    "assumption.updated",
    "assumption.invalidated",
    "assumption.confirmed",
    "issue.opened",
    "issue.updated",
    "issue.resolved",
    "issue.closed",
    "dependency.created",
    "dependency.updated",
    "dependency.resolved",
    "raci.assigned",
    "raci.revoked",
    "dor.evaluated",
    "dod.evaluated",
    "gate.overridden",
    "artifact.created",
    "artifact.updated",
    "observation.recorded",
    "lesson.recorded",
    "evidence.attached",
}


class PrivacyMode(StrEnum):
    """Operational privacy modes for project events and evidence."""

    METADATA_ONLY = "metadata-only"
    STRUCTURED_EVENTS = "structured-events"
    FULL_CONTENT = "full-content"


class RedactionRecord(BaseModel):
    """Metadata detailing redaction actions performed without exposing secret values."""

    model_config = ConfigDict(extra="forbid")

    replacements_count: int = Field(default=0, ge=0)
    detected_secret_classes: list[str] = Field(default_factory=list)
    timestamp: str = Field(..., pattern=TIMESTAMP_REGEX)


class ProjectEvent(BaseModel):
    """Canonical append-only ledger event schema for POWER Project State Engine v1."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., pattern=EVENT_ID_REGEX, max_length=132)
    schema_version: Literal["power.project-event.v1"] = "power.project-event.v1"
    project_id: str = Field(..., pattern=PROJECT_ID_REGEX, max_length=68)
    sequence: int = Field(..., ge=1)
    timestamp: str = Field(..., pattern=TIMESTAMP_REGEX)
    actor: str = Field(..., min_length=1, max_length=128)
    source: str = Field(..., min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=128)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_digest: str = Field(..., pattern=HASH_REGEX)
    prev_event_hash: str = Field(default="", pattern=PREV_HASH_REGEX)
    event_hash: str = Field(..., pattern=HASH_REGEX)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    correlation_id: str | None = Field(default=None, max_length=128)
    causation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in PROJECT_EVENT_TYPES:
            raise ValueError(f"Unknown or disallowed event_type: {v}")
        return v

    @field_validator("project_id")
    @classmethod
    def validate_project_id_field(cls, v: str) -> str:
        return validate_project_id(v)

    @field_validator("event_id")
    @classmethod
    def validate_event_id_field(cls, v: str) -> str:
        return validate_event_id(v)


class AppendCommand(BaseModel):
    """External client append command.

    Sequence, prev_event_hash, and event_hash are explicitly NOT part of this command,
    as they are strictly assigned by the EventStore under project lock.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX, max_length=68)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(..., min_length=1, max_length=128)
    source: str = Field(..., min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=128)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    correlation_id: str | None = Field(default=None, max_length=128)
    causation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)
    event_id: str | None = Field(default=None, pattern=EVENT_ID_REGEX, max_length=132)
    timestamp: str | None = Field(default=None, pattern=TIMESTAMP_REGEX)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in PROJECT_EVENT_TYPES:
            raise ValueError(f"Unknown or disallowed event_type: {v}")
        return v

    @field_validator("project_id")
    @classmethod
    def validate_project_id_field(cls, v: str) -> str:
        return validate_project_id(v)

    @field_validator("event_id")
    @classmethod
    def validate_event_id_field(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_event_id(v)
        return v

    @model_validator(mode="after")
    def validate_saga_payload(self) -> AppendCommand:
        model_cls = SAGA_PAYLOAD_MODELS.get(self.event_type)
        if model_cls is not None:
            if not isinstance(self.payload, dict) or not self.payload:
                raise ValueError(
                    f"Payload for saga event '{self.event_type}' must be a non-empty dictionary conforming to {model_cls.__name__}"
                )
            payload_data = dict(self.payload)
            if "project_id" not in payload_data:
                payload_data["project_id"] = self.project_id
            if "correlation_id" not in payload_data and self.correlation_id:
                payload_data["correlation_id"] = self.correlation_id
            if "idempotency_key" not in payload_data and self.idempotency_key:
                payload_data["idempotency_key"] = self.idempotency_key
            model_cls.model_validate(payload_data)
        return self


class LedgerVerificationResult(BaseModel):
    """Cryptographic and schema verification result for a project event stream."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    event_count: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)
    last_event_hash: str = Field(default="")
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Cross-Subsystem Association Saga Payloads (ADR-PSE-008)
# ---------------------------------------------------------------------------

class TaskAssociationRequestedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    task_id: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(default="contributes_to")
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)


class TaskAssociatedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    task_id: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(default="contributes_to")
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


class TaskAssociationFailedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    task_id: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(default="contributes_to")
    reason: str = Field(..., min_length=1, max_length=512)
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


class DecisionAssociationRequestedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    decision_id: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(default="governs")
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)


class DecisionAssociatedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    decision_id: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(default="governs")
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


class DecisionAssociationFailedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., pattern=PROJECT_ID_REGEX)
    decision_id: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(default="governs")
    reason: str = Field(..., min_length=1, max_length=512)
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


SAGA_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "task.association.requested": TaskAssociationRequestedPayload,
    "task.associated": TaskAssociatedPayload,
    "task.association.failed": TaskAssociationFailedPayload,
    "decision.association.requested": DecisionAssociationRequestedPayload,
    "decision.associated": DecisionAssociatedPayload,
    "decision.association.failed": DecisionAssociationFailedPayload,
}

