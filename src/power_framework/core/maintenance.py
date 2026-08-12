"""Policy-driven, preview-first maintenance for the lean release.

The plan is a durable contract between detection and mutation.  Every
reversible repair is bound to the source hash observed during planning.  A
changed source aborts the whole apply before the first write; a later failure
restores all backups already created.  Irreversible retention/archive findings
are intentionally reported as plan-only until a reversible implementation is
proven.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .healer import DEFAULT_EXCLUDED, heal_frontmatter
from .ignore import should_skip
from .mutation import execute_vault_mutation
from .utils import atomic_write, create_backup, prune_backups, restore_backup

if TYPE_CHECKING:
    from collections.abc import Iterable


MaintenanceClass = Literal["safe_auto", "approval_required", "informational"]


@dataclass(frozen=True)
class MaintenanceAction:
    """One content-free, hash-bound maintenance finding."""

    action_id: str
    kind: str
    path: str
    action_class: MaintenanceClass
    before_sha256: str
    after_sha256: str | None = None
    detail: str = ""
    reversible: bool = False
    transform_timestamp: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "path": self.path,
            "action_class": self.action_class,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "detail": self.detail,
            "reversible": self.reversible,
            "transform_timestamp": self.transform_timestamp,
        }


@dataclass(frozen=True)
class MaintenancePlan:
    """Deterministic preview of maintenance work."""

    vault: str
    generated_at: str
    actions: tuple[MaintenanceAction, ...] = field(default_factory=tuple)
    schema_version: str = "power.maintenance-plan.v1"

    @property
    def plan_sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "vault": self.vault,
            "actions": [action.as_dict() for action in self.actions],
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "vault": self.vault,
            "generated_at": self.generated_at,
            "plan_sha256": self.plan_sha256,
            "actions": [action.as_dict() for action in self.actions],
            "apply_policy": {
                "default": "dry-run",
                "safe_auto": "reversible_hash_bound",
                "approval_required": "plan_only",
            },
        }


@dataclass(frozen=True)
class MaintenanceReceipt:
    """Content-free receipt for a successful maintenance apply."""

    plan_sha256: str
    applied_action_ids: tuple[str, ...]
    status: Literal["ok", "no-op"]
    schema_version: str = "power.maintenance-receipt.v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_sha256": self.plan_sha256,
            "applied_action_ids": list(self.applied_action_ids),
            "status": self.status,
        }


def build_maintenance_plan(
    vault_dir: Path,
    *,
    backup_max_count: int | None = 50,
    backup_max_age_days: float | None = 30,
    backup_max_bytes: int | None = 500 * 1024 * 1024,
) -> MaintenancePlan:
    """Detect reversible repairs and plan-only destructive candidates."""
    root = Path(vault_dir).expanduser().resolve()
    planned_at = datetime.now(UTC)
    actions: list[MaintenanceAction] = []
    for filepath in _candidate_notes(root):
        content = filepath.read_text(encoding="utf-8")
        healed, changes = heal_frontmatter(content, filepath, root, now=planned_at)
        if not changes or healed == content:
            continue
        rel = filepath.relative_to(root).as_posix()
        actions.append(
            MaintenanceAction(
                action_id=_action_id("heal.frontmatter", rel, content),
                kind="heal.frontmatter",
                path=rel,
                action_class="safe_auto",
                before_sha256=_sha256(content),
                after_sha256=_sha256(healed),
                detail="; ".join(changes),
                reversible=True,
                transform_timestamp=planned_at.isoformat(),
            )
        )

    for backup_dir in _backup_directories(root):
        for backup in prune_backups(
            backup_dir,
            max_count=backup_max_count,
            max_age_days=backup_max_age_days,
            max_bytes=backup_max_bytes,
            dry_run=True,
        ):
            rel = backup.relative_to(root).as_posix()
            backup_content = backup.read_bytes()
            actions.append(
                MaintenanceAction(
                    action_id=_action_id("retention.backup", rel, backup_content),
                    kind="retention.backup",
                    path=rel,
                    action_class="approval_required",
                    before_sha256=_sha256(backup_content),
                    detail="retention candidate; deletion remains plan-only",
                    reversible=False,
                )
            )

    actions.sort(key=lambda action: (action.kind, action.path, action.action_id))
    return MaintenancePlan(
        vault=str(root),
        generated_at=planned_at.isoformat(),
        actions=tuple(actions),
    )


def apply_maintenance_plan(
    vault_dir: Path,
    plan: MaintenancePlan,
    *,
    approved: bool = False,
) -> MaintenanceReceipt:
    """Apply only hash-bound reversible actions from a plan.

    Approval is explicit even for ``safe_auto`` actions.  Approval-required
    actions are rejected rather than silently deleting backups or moving human
    notes without a rollback contract.
    """
    root = Path(vault_dir).expanduser().resolve()
    if str(root) != plan.vault:
        raise ValueError("maintenance plan belongs to a different vault")
    if not approved:
        raise PermissionError("maintenance apply requires explicit approved=True")
    if any(action.action_class != "safe_auto" for action in plan.actions):
        raise PermissionError("plan contains approval-required or plan-only actions")

    def apply() -> MaintenanceReceipt:
        _verify_preconditions(root, plan.actions)
        backups: list[tuple[Path, Path]] = []
        applied: list[str] = []
        try:
            for action in plan.actions:
                target = _inside_vault(root, action.path)
                content = target.read_text(encoding="utf-8")
                healed, _ = heal_frontmatter(
                    content, target, root, now=_parse_timestamp(action.transform_timestamp)
                )
                if action.after_sha256 != _sha256(healed):
                    raise RuntimeError(f"maintenance postcondition changed: {action.path}")
                backup = create_backup(target)
                if backup is None:
                    raise FileNotFoundError(f"maintenance target disappeared: {action.path}")
                backups.append((target, backup))
                atomic_write(target, healed)
                applied.append(action.action_id)
        except Exception:
            for target, backup in reversed(backups):
                restore_backup(backup, target, overwrite=True)
            raise
        return MaintenanceReceipt(
            plan_sha256=plan.plan_sha256,
            applied_action_ids=tuple(applied),
            status="ok" if applied else "no-op",
        )

    return execute_vault_mutation(root, apply)


def _candidate_notes(root: Path) -> Iterable[Path]:
    for filepath in root.rglob("*.md"):
        rel = filepath.relative_to(root)
        if should_skip(root, rel.as_posix()) or any(part in DEFAULT_EXCLUDED for part in rel.parts):
            continue
        if filepath.name in DEFAULT_EXCLUDED or not filepath.is_file() or filepath.is_symlink():
            continue
        yield filepath


def _backup_directories(root: Path) -> Iterable[Path]:
    for directory in root.rglob(".backups"):
        if directory.is_dir() and not directory.is_symlink():
            yield directory


def _inside_vault(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("maintenance path escapes vault") from exc
    if target.is_symlink():
        raise ValueError("maintenance refuses symlink targets")
    return target


def _verify_preconditions(root: Path, actions: Iterable[MaintenanceAction]) -> None:
    for action in actions:
        target = _inside_vault(root, action.path)
        if not target.is_file():
            raise FileNotFoundError(f"maintenance target is not a regular file: {action.path}")
        if _sha256(target.read_bytes()) != action.before_sha256:
            raise RuntimeError(f"maintenance plan is stale: {action.path}")


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _action_id(kind: str, path: str, content: bytes | str) -> str:
    return hashlib.sha256(f"{kind}\0{path}\0{_sha256(content)}".encode()).hexdigest()[:24]


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


__all__ = [
    "MaintenanceAction",
    "MaintenancePlan",
    "MaintenanceReceipt",
    "apply_maintenance_plan",
    "build_maintenance_plan",
]
