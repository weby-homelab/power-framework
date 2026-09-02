"""Durable, content-free work packets for cross-agent handoff.

Work packets are the control-plane state for a bounded workflow.  They are
Markdown so a human can inspect them without POWER, but their frontmatter is
strictly validated and contains no note content.  Retrieved text is data and
never becomes authority or an executable action through this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .mutation import execute_vault_mutation
from .utils import atomic_write, vault_control_dir

WORK_PACKET_SCHEMA_VERSION = 1
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TASK_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAINTENANCE_PHASES = ("detect", "dry-run", "repair", "verify", "receipt")
_NEXT_MAINTENANCE_PHASE = {
    "detect": "dry-run",
    "dry-run": "repair",
    "repair": "verify",
    "verify": "receipt",
    "receipt": "receipt",
}
_TERMINAL_STATES = frozenset({"completed", "failed", "canceled"})


class WorkPacketState(StrEnum):
    """Durable states understood by every POWER handoff client."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class WorkPacket(BaseModel):
    """Strict, content-free state carried between agents."""

    schema_version: Literal[1] = 1
    task_id: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=200)
    actor: str = Field(min_length=1, max_length=200)
    scope: list[str] = Field(default_factory=list, max_length=64)
    authority: Literal["read-only", "propose", "apply"] = "read-only"
    state: WorkPacketState = WorkPacketState.SUBMITTED
    profile: Literal["standard", "maintenance"] = "standard"
    maintenance_phase: str | None = None
    source_revision: str = Field(default="unknown", max_length=200)
    changed_artifacts: list[str] = Field(default_factory=list, max_length=64)
    receipt_ids: list[str] = Field(default_factory=list, max_length=64)
    open_gates: list[str] = Field(default_factory=list, max_length=64)
    next_action: str = Field(min_length=1, max_length=1000)
    blocker: str | None = Field(default=None, max_length=1000)
    required_approval: str | None = Field(default=None, max_length=200)
    human_interventions: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)
    checkpoint: int = Field(default=0, ge=0)
    last_action: str = Field(default="create", max_length=64)
    last_idempotency_key: str = Field(min_length=1, max_length=128)
    last_action_fingerprint: str = Field(min_length=64, max_length=64)
    content_capture: Literal["disabled"] = "disabled"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_validator("scope", "changed_artifacts", "receipt_ids", "open_gates")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if len(normalized) != len(values):
            raise ValueError("work packet lists must contain non-empty strings")
        return normalized

    @field_validator("maintenance_phase")
    @classmethod
    def validate_maintenance_phase(cls, value: str | None) -> str | None:
        if value is not None and value not in _MAINTENANCE_PHASES:
            raise ValueError("unknown maintenance phase")
        return value


def create_work_packet(
    vault_dir: Path,
    *,
    task_id: str,
    objective: str,
    owner: str,
    actor: str,
    scope: list[str] | None = None,
    authority: Literal["read-only", "propose", "apply"] = "read-only",
    source_revision: str = "unknown",
    next_action: str = "inspect",
    profile: Literal["standard", "maintenance"] = "standard",
    required_approval: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    """Create one packet or return the same packet for an idempotent retry."""
    _validate_task_id(task_id)
    key = idempotency_key or task_id
    _validate_token(key, "idempotency_key")
    if profile == "maintenance":
        next_action = "detect"
        maintenance_phase = "detect"
    else:
        maintenance_phase = None
    creation_fingerprint = _creation_fingerprint(
        task_id=task_id,
        objective=objective,
        owner=owner,
        actor=actor,
        scope=scope or [],
        authority=authority,
        source_revision=source_revision,
        next_action=next_action,
        profile=profile,
        required_approval=required_approval,
    )

    def create() -> dict[str, object]:
        packet_path = _packet_path(vault_dir, task_id)
        if packet_path.exists():
            existing = _load_packet(vault_dir, task_id, recover=False)
            if (
                existing.last_action == "create"
                and existing.last_idempotency_key == key
                and existing.last_action_fingerprint == creation_fingerprint
            ):
                return _public_packet(existing)
            raise FileExistsError(f"Work packet already exists: {task_id}")
        if _latest_checkpoint_path(vault_dir, task_id) is not None:
            existing = _load_packet(vault_dir, task_id, recover=True)
            if (
                existing.last_action == "create"
                and existing.last_idempotency_key == key
                and existing.last_action_fingerprint == creation_fingerprint
            ):
                return _public_packet(existing)
            raise FileExistsError(f"Work packet checkpoint already exists: {task_id}")

        now = datetime.now(UTC)
        packet = WorkPacket(
            task_id=task_id,
            objective=objective,
            owner=owner,
            actor=actor,
            scope=scope or [],
            authority=authority,
            profile=profile,
            maintenance_phase=maintenance_phase,
            source_revision=source_revision,
            next_action=next_action,
            required_approval=required_approval,
            idempotency_key=key,
            last_idempotency_key=key,
            last_action_fingerprint=creation_fingerprint,
            created_at=now,
            updated_at=now,
        )
        _write_packet(vault_dir, packet, "create", key, creation_fingerprint)
        return _public_packet(packet)

    return execute_vault_mutation(vault_dir, create)


def advance_work_packet(
    vault_dir: Path,
    task_id: str,
    *,
    action: Literal["resume", "checkpoint", "input-required", "complete", "fail", "cancel"],
    idempotency_key: str,
    actor: str,
    approved: bool = False,
    next_action: str | None = None,
    blocker: str | None = None,
    required_approval: str | None = None,
    receipt_id: str | None = None,
    changed_artifacts: list[str] | None = None,
    open_gates: list[str] | None = None,
    phase: str | None = None,
) -> dict[str, object]:
    """Advance a packet under an explicit, idempotent lifecycle action.

    This function changes only the packet and immutable checkpoint Markdown.
    It never executes ``next_action``, opens a network connection, or applies a
    note mutation.  A caller must invoke the separate governed mutation API for
    any actual write.
    """
    _validate_task_id(task_id)
    _validate_token(idempotency_key, "idempotency_key")
    if receipt_id is not None:
        _validate_token(receipt_id, "receipt_id")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be a non-empty string")
    if phase is not None and phase not in _MAINTENANCE_PHASES:
        raise ValueError("unknown maintenance phase")

    def advance() -> dict[str, object]:
        packet = _load_packet(vault_dir, task_id, recover=True)
        fingerprint = _action_fingerprint(
            action,
            {
                "task_id": task_id,
                "actor": actor,
                "idempotency_key": idempotency_key,
                "approved": approved,
                "next_action": next_action,
                "blocker": blocker,
                "required_approval": required_approval,
                "receipt_id": receipt_id,
                "changed_artifacts": changed_artifacts or [],
                "open_gates": open_gates or [],
                "phase": phase,
            },
        )
        prior = _find_checkpoint_by_idempotency(vault_dir, task_id, idempotency_key)
        if prior is not None:
            prior_fingerprint, prior_packet = prior
            if prior_fingerprint != fingerprint:
                raise RuntimeError("idempotency key reused for a different work-packet action")
            return _public_packet(prior_packet)

        if packet.state in _TERMINAL_STATES:
            raise RuntimeError(f"work packet is already {packet.state}")
        if action == "resume":
            if packet.state == WorkPacketState.INPUT_REQUIRED and not approved:
                raise PermissionError("resume requires explicit approval for the requested input")
            new_state = WorkPacketState.WORKING
            new_phase = packet.maintenance_phase
            new_blocker = None
            new_approval = None
        elif action == "checkpoint":
            if packet.state != WorkPacketState.WORKING:
                raise RuntimeError("checkpoint requires a working packet")
            new_state = WorkPacketState.WORKING
            new_phase = _advance_maintenance_phase(packet, phase, approved)
            new_blocker = None
            new_approval = None
        elif action == "input-required":
            if not blocker or not blocker.strip():
                raise ValueError("input-required requires a blocker")
            new_state = WorkPacketState.INPUT_REQUIRED
            new_phase = packet.maintenance_phase
            new_blocker = blocker.strip()
            new_approval = required_approval or "caller"
        elif action == "complete":
            if packet.state != WorkPacketState.WORKING:
                raise RuntimeError("only a working packet can be completed")
            if not receipt_id or not _TOKEN_PATTERN.fullmatch(receipt_id):
                raise ValueError("complete requires a receipt_id")
            if packet.open_gates or (
                packet.profile == "maintenance" and packet.maintenance_phase != "receipt"
            ):
                raise RuntimeError("cannot complete a packet with open gates")
            new_state = WorkPacketState.COMPLETED
            new_phase = packet.maintenance_phase
            new_blocker = None
            new_approval = None
        elif action == "fail":
            if not blocker or not blocker.strip():
                raise ValueError("fail requires a blocker")
            new_state = WorkPacketState.FAILED
            new_phase = packet.maintenance_phase
            new_blocker = blocker.strip()
            new_approval = None
        else:  # cancel
            if not approved:
                raise PermissionError("cancel requires explicit approved=True")
            new_state = WorkPacketState.CANCELED
            new_phase = packet.maintenance_phase
            new_blocker = blocker.strip() if blocker else "canceled by caller"
            new_approval = None

        now = datetime.now(UTC)
        updated_receipts = list(packet.receipt_ids)
        if receipt_id and receipt_id not in updated_receipts:
            updated_receipts.append(receipt_id)
        updated_artifacts = list(packet.changed_artifacts)
        for artifact in changed_artifacts or []:
            if artifact not in updated_artifacts:
                updated_artifacts.append(artifact)
        updated_gates = list(open_gates) if open_gates is not None else list(packet.open_gates)
        updated_next_action = next_action or _default_next_action(new_state, new_phase)
        intervention = (
            action == "input-required"
            or action == "cancel"
            or (action == "checkpoint" and phase == "repair" and approved)
        )
        interventions = packet.human_interventions + (1 if intervention else 0)
        updated = WorkPacket.model_validate(
            {
                **packet.model_dump(),
                "actor": actor,
                "state": new_state,
                "maintenance_phase": new_phase,
                "changed_artifacts": updated_artifacts,
                "receipt_ids": updated_receipts,
                "open_gates": updated_gates,
                "next_action": updated_next_action,
                "blocker": new_blocker,
                "required_approval": new_approval,
                "human_interventions": interventions,
                "checkpoint": packet.checkpoint + 1,
                "last_action": action,
                "last_idempotency_key": idempotency_key,
                "last_action_fingerprint": fingerprint,
                "updated_at": now,
            }
        )
        _write_packet(vault_dir, updated, action, idempotency_key, fingerprint)
        return _public_packet(updated)

    return execute_vault_mutation(vault_dir, advance)


def read_work_packet(vault_dir: Path, task_id: str) -> dict[str, object]:
    """Read one packet without creating any vault or cache state."""
    _validate_task_id(task_id)
    return _public_packet(_load_packet(vault_dir, task_id, recover=False))


def list_work_packets(vault_dir: Path) -> list[dict[str, object]]:
    """List packet summaries without reading note content or creating state."""
    directory = _packet_directory(vault_dir)
    if not directory.is_dir():
        return []
    packets = [
        _public_packet(_load_packet(vault_dir, path.stem, recover=False))
        for path in directory.glob("*.md")
    ]
    return sorted(packets, key=lambda item: str(item["updated_at"]), reverse=True)


def _advance_maintenance_phase(packet: WorkPacket, phase: str | None, approved: bool) -> str | None:
    if packet.profile != "maintenance":
        if phase is not None:
            raise ValueError("phase is valid only for maintenance packets")
        return None
    if phase is None or phase != packet.maintenance_phase:
        raise RuntimeError(
            f"maintenance phase must advance from {packet.maintenance_phase!r}; got {phase!r}"
        )
    if phase == "repair" and not approved:
        raise PermissionError("maintenance repair requires explicit approved=True")
    return _NEXT_MAINTENANCE_PHASE[phase]


def _default_next_action(state: WorkPacketState, phase: str | None) -> str:
    if state == WorkPacketState.WORKING and phase:
        return phase
    if state == WorkPacketState.COMPLETED:
        return "none"
    if state in {WorkPacketState.FAILED, WorkPacketState.CANCELED}:
        return "handoff"
    if state == WorkPacketState.INPUT_REQUIRED:
        return "provide-input-or-approval"
    return "inspect"


def _validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or not _TASK_PATTERN.fullmatch(task_id):
        raise ValueError("task_id must be a safe token")


def _validate_token(value: str, field: str) -> None:
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a safe token")


def _packet_directory(vault_dir: Path) -> Path:
    return vault_control_dir(Path(vault_dir)) / "work-packets"


def _packet_path(vault_dir: Path, task_id: str) -> Path:
    return _packet_directory(vault_dir) / f"{task_id}.md"


def _checkpoint_directory(vault_dir: Path, task_id: str) -> Path:
    return _packet_directory(vault_dir) / task_id / "checkpoints"


def _latest_checkpoint_path(vault_dir: Path, task_id: str) -> Path | None:
    directory = _checkpoint_directory(vault_dir, task_id)
    if not directory.is_dir():
        return None
    paths = sorted(directory.glob("*.md"))
    if not paths:
        return None
    if any(not re.fullmatch(r"\d{6}", path.stem) for path in paths):
        raise ValueError("work-packet checkpoint has an invalid filename")
    return paths[-1]


def _load_packet(vault_dir: Path, task_id: str, *, recover: bool) -> WorkPacket:
    """Load state and use the latest immutable checkpoint for recovery."""
    packet_path = _packet_path(vault_dir, task_id)
    latest_path = _latest_checkpoint_path(vault_dir, task_id)
    if latest_path is None:
        if not packet_path.is_file():
            raise FileNotFoundError(f"Work packet not found: {task_id}")
        packet = _read_packet(packet_path)
        if packet.checkpoint != 0:
            raise ValueError("work packet has no immutable checkpoint for its state")
        return packet

    checkpoint_fingerprint, checkpoint_packet = _read_packet_with_checkpoint(latest_path)
    if checkpoint_packet.task_id != task_id:
        raise ValueError("work-packet checkpoint task_id does not match its path")
    if not packet_path.is_file():
        if recover:
            atomic_write(packet_path, _render_packet(checkpoint_packet))
        return checkpoint_packet

    packet = _read_packet(packet_path)
    if (
        packet.model_dump(mode="json") == checkpoint_packet.model_dump(mode="json")
        and packet.last_action_fingerprint == checkpoint_fingerprint
    ):
        return packet
    if packet.checkpoint < checkpoint_packet.checkpoint:
        if recover:
            atomic_write(packet_path, _render_packet(checkpoint_packet))
        return checkpoint_packet
    raise ValueError("work-packet main state does not match its latest checkpoint")


def _action_fingerprint(action: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"action": action, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _creation_fingerprint(
    *,
    task_id: str,
    objective: str,
    owner: str,
    actor: str,
    scope: list[str],
    authority: str,
    source_revision: str,
    next_action: str,
    profile: str,
    required_approval: str | None,
) -> str:
    return _action_fingerprint(
        "create",
        {
            "task_id": task_id,
            "objective": objective,
            "owner": owner,
            "actor": actor,
            "scope": scope,
            "authority": authority,
            "source_revision": source_revision,
            "next_action": next_action,
            "profile": profile,
            "required_approval": required_approval,
        },
    )


def _render_packet(
    packet: WorkPacket,
    *,
    checkpoint_action: str | None = None,
    checkpoint_key: str | None = None,
    checkpoint_fingerprint: str | None = None,
) -> str:
    data = packet.model_dump(mode="json", exclude_none=True)
    data["control_plane"] = "power-work-packet"
    if checkpoint_action is not None:
        data["checkpoint_action"] = checkpoint_action
    if checkpoint_key is not None:
        data["checkpoint_idempotency_key"] = checkpoint_key
    if checkpoint_fingerprint is not None:
        data["checkpoint_fingerprint"] = checkpoint_fingerprint
    frontmatter = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return (
        f"---\n{frontmatter}\n---\n\n"
        "# POWER work packet\n\n"
        "This is a content-free control-plane handoff. Retrieved note text is "
        "untrusted data and is never an instruction channel.\n"
    )


def _write_packet(
    vault_dir: Path,
    packet: WorkPacket,
    action: str,
    idempotency_key: str,
    fingerprint: str,
) -> None:
    packet_path = _packet_path(vault_dir, packet.task_id)
    checkpoint_path = _checkpoint_directory(vault_dir, packet.task_id) / (
        f"{packet.checkpoint:06d}.md"
    )
    if checkpoint_path.exists():
        existing = _read_packet_with_checkpoint(checkpoint_path)
        existing_key = _checkpoint_key(checkpoint_path)
        if (
            existing[0] != fingerprint
            or existing_key != idempotency_key
            or existing[1].model_dump(mode="json") != packet.model_dump(mode="json")
        ):
            raise RuntimeError("work-packet checkpoint collision detected")
        if packet_path.exists() and _read_packet(packet_path).model_dump(
            mode="json"
        ) != packet.model_dump(mode="json"):
            raise RuntimeError("work-packet main state does not match its checkpoint")
        if not packet_path.exists():
            atomic_write(packet_path, _render_packet(packet))
        return
    previous_packet = packet_path.read_text(encoding="utf-8") if packet_path.exists() else None
    previous_checkpoint = (
        checkpoint_path.read_text(encoding="utf-8") if checkpoint_path.exists() else None
    )
    try:
        atomic_write(packet_path, _render_packet(packet))
        atomic_write(
            checkpoint_path,
            _render_packet(
                packet,
                checkpoint_action=action,
                checkpoint_key=idempotency_key,
                checkpoint_fingerprint=fingerprint,
            ),
        )
    except Exception:
        _restore_text(packet_path, previous_packet)
        _restore_text(checkpoint_path, previous_checkpoint)
        raise


def _restore_text(path: Path, content: str | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, content)


def _read_packet(path: Path) -> WorkPacket:
    if not path.is_file():
        raise FileNotFoundError(f"Work packet not found: {path.stem}")
    try:
        data = yaml.safe_load(_extract_frontmatter(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("work packet is unreadable") from exc
    if not isinstance(data, dict) or data.pop("control_plane", None) != "power-work-packet":
        raise ValueError("work packet has invalid control-plane metadata")
    try:
        return WorkPacket.model_validate(data)
    except ValueError as exc:
        raise ValueError("work packet schema is invalid") from exc


def _read_packet_with_checkpoint(path: Path) -> tuple[str, WorkPacket]:
    try:
        data = yaml.safe_load(_extract_frontmatter(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("work-packet checkpoint is unreadable") from exc
    if not isinstance(data, dict) or data.pop("control_plane", None) != "power-work-packet":
        raise ValueError("work-packet checkpoint has invalid control-plane metadata")
    fingerprint = data.pop("checkpoint_fingerprint", None)
    data.pop("checkpoint_action", None)
    data.pop("checkpoint_idempotency_key", None)
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ValueError("work-packet checkpoint has no valid fingerprint")
    try:
        packet = WorkPacket.model_validate(data)
    except ValueError as exc:
        raise ValueError("work-packet checkpoint schema is invalid") from exc
    return fingerprint, packet


def _find_checkpoint_by_idempotency(
    vault_dir: Path, task_id: str, idempotency_key: str
) -> tuple[str, WorkPacket] | None:
    directory = _checkpoint_directory(vault_dir, task_id)
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.md")):
        checkpoint_key = _checkpoint_key(path)
        if checkpoint_key == idempotency_key:
            return _read_packet_with_checkpoint(path)
    return None


def _checkpoint_key(path: Path) -> str | None:
    try:
        data = yaml.safe_load(_extract_frontmatter(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError("work-packet checkpoint is unreadable") from exc
    if not isinstance(data, dict):
        raise ValueError("work-packet checkpoint metadata is invalid")
    value = data.get("checkpoint_idempotency_key")
    if not isinstance(value, str):
        raise ValueError("work-packet checkpoint has no idempotency key")
    _validate_token(value, "checkpoint_idempotency_key")
    return value


def _extract_frontmatter(content: str) -> str:
    if not content.startswith("---\n"):
        raise ValueError("work packet has no frontmatter")
    marker = content.find("\n---\n", 4)
    if marker < 0:
        raise ValueError("work packet frontmatter is incomplete")
    return content[4:marker]


def _public_packet(packet: WorkPacket) -> dict[str, object]:
    """Return machine-readable packet state without Markdown body content."""
    return packet.model_dump(mode="json", exclude_none=True)
