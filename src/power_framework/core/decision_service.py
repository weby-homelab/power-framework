"""Durable decision and approval service bound to canonical Task v2 state."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .decision_models import (
    Decision,
    DecisionAction,
    DecisionAuthority,
    DecisionReceipt,
    ResponseType,
)
from .task_models import ensure_valid_task_id
from .task_service import TaskService
from .utils import atomic_write

_AUTHORITY_RANK: dict[str, int] = {"read-only": 0, "propose": 1, "apply": 2}


class DecisionService:
    """Manage durable decision gates without granting authority from free text."""

    def __init__(self, vault_dir: Path, *, task_service: TaskService | None = None) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self.task_service = task_service or TaskService(self.vault_dir)
        self.store = self.task_service.store
        self.decisions_dir = self.store.tasks_dir / "decisions"
        self.receipts_dir = self.decisions_dir / "receipts"

    def create_decision(
        self,
        *,
        decision_id: str,
        task_id: str,
        title: str,
        requested_by: str,
        task_revision: int | None = None,
        proposal_id: str | None = None,
        proposal_sha256: str | None = None,
        description: str = "",
        risk_level: str = "medium",
        required_authority: DecisionAuthority = "apply",
        allowed_actors: list[str] | None = None,
        response_schema: dict[str, ResponseType] | None = None,
        expires_at: str | None = None,
    ) -> Decision:
        """Create a pending decision bound to the current task revision."""
        with self.store.lock():
            task = self.task_service.get_task(task_id)
            if task is None:
                raise FileNotFoundError(f"Task {task_id} not found")
            bound_revision = task.revision if task_revision is None else task_revision
            if bound_revision != task.revision:
                raise ValueError(
                    f"Decision task revision is stale: expected {task.revision}, found {bound_revision}"
                )
            if expires_at is not None and _parse_timestamp(expires_at) <= datetime.now(UTC):
                raise ValueError("Decision expiry must be in the future")

            decision = Decision(
                decision_id=decision_id,
                task_id=task_id,
                task_revision=bound_revision,
                proposal_id=proposal_id,
                proposal_sha256=proposal_sha256,
                title=title,
                description=description,
                risk_level=cast("Any", risk_level),
                requested_by=requested_by,
                required_authority=required_authority,
                allowed_actors=allowed_actors or ["*"],
                response_schema=response_schema or {},
                expires_at=expires_at,
            )
            decision_file = self._decision_file(decision_id)
            if decision_file.exists():
                raise ValueError(f"Decision with ID {decision_id} already exists")
            self._ensure_dirs()
            with self.store._transaction(
                "decision_create",
                None,
                None,
                [(decision_file, "decision")],
                crash_point="decision.create",
            ):
                atomic_write(decision_file, _serialize(decision))
            return decision

    def get_decision(self, decision_id: str) -> Decision | None:
        """Read one decision without creating storage."""
        decision_file = self._decision_file(decision_id)
        if not decision_file.is_file():
            return None
        try:
            decision = Decision.model_validate_json(decision_file.read_text(encoding="utf-8"))
            return _effective_decision(decision)
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"Malformed decision snapshot {decision_id}") from exc

    def list_decisions(
        self,
        *,
        status: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Decision]:
        """List bounded decisions ordered by creation time descending."""
        if not 1 <= limit <= 500:
            raise ValueError("decision limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("decision offset must be non-negative")
        if task_id is not None:
            ensure_valid_task_id(task_id)
        if not self.decisions_dir.is_dir():
            return []

        decisions: list[Decision] = []
        for path in self.decisions_dir.glob("dec_*.json"):
            decision = self.get_decision(path.stem)
            if decision is None:
                continue
            if status is not None and decision.status != status:
                continue
            if task_id is not None and decision.task_id != task_id:
                continue
            decisions.append(decision)
        decisions.sort(key=lambda item: item.created_at, reverse=True)
        return decisions[offset : offset + limit]

    def resolve_decision(
        self,
        decision_id: str,
        *,
        action: DecisionAction,
        actor: str,
        authority: str,
        proposal_sha256: str | None = None,
        input_data: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> tuple[Decision, DecisionReceipt]:
        """Resolve a decision only when every original binding still holds."""
        if not actor.strip():
            raise ValueError("actor must be a non-empty string")
        with self.store.lock():
            decision = self.get_decision(decision_id)
            if decision is None:
                raise FileNotFoundError(f"Decision {decision_id} not found")

            response = {"comment": comment, "input_data": input_data}
            response_sha256 = DecisionReceipt.digest_payload(
                decision.decision_id,
                decision.task_id,
                decision.task_revision,
                action,
                actor,
                response,
            )
            receipt_id = f"dcr_{response_sha256}"
            if decision.status == "expired":
                raise ValueError("Decision has expired")
            if decision.status != "pending":
                receipt = self.get_receipt(decision.receipt_id or "")
                if (
                    receipt is not None
                    and receipt.receipt_id == receipt_id
                    and decision.resolution_action == action
                    and decision.resolved_by == actor
                ):
                    return decision, receipt
                raise ValueError("Decision is already resolved")

            if "*" not in decision.allowed_actors and actor not in decision.allowed_actors:
                raise PermissionError("Actor is not allowed to resolve this decision")
            if _AUTHORITY_RANK.get(authority, -1) < _AUTHORITY_RANK[decision.required_authority]:
                raise PermissionError("Decision resolution has insufficient authority")
            if decision.proposal_sha256 is not None and proposal_sha256 != decision.proposal_sha256:
                raise ValueError("Decision proposal hash does not match")

            task = self.task_service.get_task(decision.task_id)
            if task is None:
                raise FileNotFoundError(f"Task {decision.task_id} not found")
            if task.revision != decision.task_revision:
                raise ValueError(
                    f"Decision task revision is stale: expected {decision.task_revision}, "
                    f"found {task.revision}"
                )

            validated_input = _validate_response(decision, action, input_data)
            status = "approved" if action in {"approve", "provide_input"} else "rejected"
            receipt = DecisionReceipt(
                receipt_id=receipt_id,
                decision_id=decision.decision_id,
                task_id=decision.task_id,
                task_revision=decision.task_revision,
                action=action,
                actor=actor,
                response_sha256=response_sha256,
            )
            resolved = decision.model_copy(
                update={
                    "status": status,
                    "resolved_at": receipt.created_at,
                    "resolved_by": actor,
                    "resolution_action": action,
                    "resolution_comment": comment,
                    "resolution_input": validated_input,
                    "receipt_id": receipt.receipt_id,
                }
            )
            resolved = Decision.model_validate(resolved.model_dump())

            self._ensure_dirs()
            decision_file = self._decision_file(decision_id)
            receipt_file = self._receipt_file(receipt.receipt_id)
            with self.store._transaction(
                "decision_resolve",
                None,
                None,
                [(decision_file, "decision"), (receipt_file, "receipt")],
                crash_point="decision.resolve",
            ):
                atomic_write(decision_file, _serialize(resolved))
                atomic_write(receipt_file, _serialize(receipt))
            return resolved, receipt

    def get_receipt(self, receipt_id: str) -> DecisionReceipt | None:
        """Read one decision receipt without creating storage."""
        if not receipt_id:
            return None
        receipt_file = self._receipt_file(receipt_id)
        if not receipt_file.is_file():
            return None
        try:
            return DecisionReceipt.model_validate_json(receipt_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"Malformed decision receipt {receipt_id}") from exc

    def _ensure_dirs(self) -> None:
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def _decision_file(self, decision_id: str) -> Path:
        Decision.validate_decision_id(decision_id)
        return self.decisions_dir / f"{decision_id}.json"

    def _receipt_file(self, receipt_id: str) -> Path:
        DecisionReceipt.validate_receipt_id(receipt_id)
        return self.receipts_dir / f"{receipt_id}.json"


def _validate_response(
    decision: Decision,
    action: DecisionAction,
    input_data: dict[str, Any] | None,
) -> dict[str, str | bool | int | float] | None:
    if action != "provide_input":
        if input_data:
            raise ValueError("Only provide_input accepts structured input")
        return None
    if not decision.response_schema:
        raise ValueError("Decision does not allow structured input")
    if input_data is None or set(input_data) != set(decision.response_schema):
        raise ValueError("Decision input fields do not match the allowed response schema")

    validated: dict[str, str | bool | int | float] = {}
    for field, expected_type in decision.response_schema.items():
        value = input_data[field]
        if not _matches_type(value, expected_type):
            raise ValueError(f"Decision input field {field} must be {expected_type}")
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError(f"Decision input field {field} exceeds 4096 characters")
        validated[field] = cast("str | bool | int | float", value)
    return validated


def _matches_type(value: object, expected_type: ResponseType) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Decision timestamp must be valid ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("Decision timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _effective_decision(decision: Decision, *, now: datetime | None = None) -> Decision:
    """Project pending decisions past expiry as terminal without hidden writes."""
    if decision.status != "pending" or decision.expires_at is None:
        return decision
    if _parse_timestamp(decision.expires_at) > (now or datetime.now(UTC)):
        return decision
    return Decision.model_validate(decision.model_dump() | {"status": "expired"})


def _serialize(model: Decision | DecisionReceipt) -> str:
    return json.dumps(model.model_dump(), ensure_ascii=False, indent=2, sort_keys=True)


__all__ = ["DecisionService"]
