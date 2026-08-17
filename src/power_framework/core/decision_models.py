"""Typed decision and approval domain models for POWER Task Manager v2."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .task_models import ensure_valid_task_id

DECISION_ID_PATTERN = re.compile(r"^dec_[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
DECISION_RECEIPT_PATTERN = re.compile(r"^dcr_[0-9a-f]{64}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RESPONSE_FIELD_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
ResponseType = Literal["string", "boolean", "number"]
DecisionAction = Literal["approve", "reject", "provide_input"]
DecisionStatus = Literal["pending", "approved", "rejected", "expired"]
DecisionAuthority = Literal["propose", "apply"]


class Decision(BaseModel):
    """A durable approval or structured-input gate bound to one task revision."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    task_id: str
    task_revision: int = Field(ge=1)
    proposal_id: str | None = Field(default=None, max_length=128)
    proposal_sha256: str | None = None
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    status: DecisionStatus = "pending"
    requested_by: str = Field(min_length=1, max_length=200)
    required_authority: DecisionAuthority = "apply"
    allowed_actors: list[str] = Field(default_factory=lambda: ["*"])
    response_schema: dict[str, ResponseType] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution_action: DecisionAction | None = None
    resolution_comment: str | None = Field(default=None, max_length=4096)
    resolution_input: dict[str, str | bool | int | float] | None = None
    receipt_id: str | None = None

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, value: str) -> str:
        if not DECISION_ID_PATTERN.fullmatch(value):
            raise ValueError("decision_id must be a safe decision token")
        return value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return ensure_valid_task_id(value)

    @field_validator("proposal_sha256")
    @classmethod
    def validate_proposal_hash(cls, value: str | None) -> str | None:
        if value is not None and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("proposal_sha256 must be a lowercase SHA-256 digest")
        return value

    @field_validator("allowed_actors")
    @classmethod
    def validate_allowed_actors(cls, value: list[str]) -> list[str]:
        if not value or any(not actor.strip() or len(actor) > 200 for actor in value):
            raise ValueError("allowed_actors must contain non-empty actor identifiers")
        return value

    @field_validator("response_schema")
    @classmethod
    def validate_response_schema(cls, value: dict[str, ResponseType]) -> dict[str, ResponseType]:
        if len(value) > 32:
            raise ValueError("response_schema cannot contain more than 32 fields")
        if any(not RESPONSE_FIELD_PATTERN.fullmatch(field) for field in value):
            raise ValueError("response_schema field names must be safe identifiers")
        return value

    @model_validator(mode="after")
    def validate_binding(self) -> Decision:
        if self.proposal_id is not None and self.proposal_sha256 is None:
            raise ValueError("proposal_id requires proposal_sha256")
        if self.status == "pending" and self.receipt_id is not None:
            raise ValueError("pending decisions cannot have a resolution receipt")
        if self.status != "pending" and self.receipt_id is None:
            raise ValueError("resolved decisions require a resolution receipt")
        return self


class DecisionReceipt(BaseModel):
    """Content-free durable evidence of one decision resolution."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    decision_id: str
    task_id: str
    task_revision: int = Field(ge=1)
    action: DecisionAction
    actor: str = Field(min_length=1, max_length=200)
    response_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str) -> str:
        if not DECISION_RECEIPT_PATTERN.fullmatch(value):
            raise ValueError("receipt_id must be a canonical decision receipt token")
        return value

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, value: str) -> str:
        if not DECISION_ID_PATTERN.fullmatch(value):
            raise ValueError("decision_id must be a safe decision token")
        return value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return ensure_valid_task_id(value)

    @staticmethod
    def digest_payload(
        decision_id: str,
        task_id: str,
        task_revision: int,
        action: DecisionAction,
        actor: str,
        response: object,
    ) -> str:
        payload = {
            "decision_id": decision_id,
            "task_id": task_id,
            "task_revision": task_revision,
            "action": action,
            "actor": actor,
            "response": response,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


__all__ = [
    "DECISION_ID_PATTERN",
    "DECISION_RECEIPT_PATTERN",
    "Decision",
    "DecisionAction",
    "DecisionAuthority",
    "DecisionReceipt",
    "DecisionStatus",
    "ResponseType",
]
