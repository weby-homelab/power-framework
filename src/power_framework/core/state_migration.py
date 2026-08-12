"""Read-only state-plane inventory for future vault migrations.

The Markdown vault remains the source of truth.  This module deliberately
stops at a deterministic plan: moving state is a platform-sensitive operation
and must not be enabled until the physical upgrade matrix proves crash,
symlink, and rollback behavior.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .vault_storage import existing_vault_cache_dir

STATE_MIGRATION_SCHEMA = "power.state-migration-plan.v1"
MAX_PLAN_ENTRIES = 20_000


@dataclass(frozen=True)
class StateEntry:
    """Content-free preimage metadata for one state-plane entry."""

    plane: str
    relative_path: str
    kind: str
    size_bytes: int
    sha256: str | None
    action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "plane": self.plane,
            "relative_path": self.relative_path,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "action": self.action,
        }


@dataclass(frozen=True)
class StateMigrationPlan:
    """Deterministic, non-mutating state-plane migration inventory."""

    schema_version: str
    vault_relative: str
    entries: tuple[StateEntry, ...]
    disk_budget_bytes: int
    estimated_copy_bytes: int
    rollback: dict[str, object]
    apply_available: bool = False

    def as_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "vault": self.vault_relative,
            "entries": [entry.as_dict() for entry in self.entries],
            "disk_budget_bytes": self.disk_budget_bytes,
            "estimated_copy_bytes": self.estimated_copy_bytes,
            "rollback": self.rollback,
            "apply_available": self.apply_available,
        }
        payload["plan_sha256"] = _payload_hash(payload)
        return payload


def build_state_migration_plan(vault_dir: Path) -> StateMigrationPlan:
    """Inventory source/control/runtime/evidence state without creating state.

    Runtime cache details are represented by a stable label rather than an
    absolute path.  The plan therefore remains safe to print or attach to a
    receipt and never includes note content.
    """
    root = Path(vault_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {root}")

    entries: list[StateEntry] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _ignored_runtime_path(relative):
            continue
        entries.append(_entry_for_path(path, relative))
        if len(entries) > MAX_PLAN_ENTRIES:
            raise ValueError(f"state migration plan exceeds {MAX_PLAN_ENTRIES} entries")

    cache_dir = existing_vault_cache_dir(root)
    if cache_dir is not None and cache_dir.is_dir():
        entries.append(
            StateEntry(
                plane="runtime",
                relative_path="<external-cache>/{vault-id}",
                kind="directory",
                size_bytes=_tree_size(cache_dir),
                sha256=None,
                action="leave-in-place-rebuildable",
            )
        )

    total_bytes = sum(entry.size_bytes for entry in entries)
    return StateMigrationPlan(
        schema_version=STATE_MIGRATION_SCHEMA,
        vault_relative=".",
        entries=tuple(entries),
        disk_budget_bytes=total_bytes,
        estimated_copy_bytes=0,
        rollback={
            "status": "not-applicable",
            "preimage": "all entries are hashed; no writes or moves occurred",
            "next_step": "run the platform upgrade matrix before enabling apply",
        },
    )


def apply_state_migration_plan(*_args: object, **_kwargs: object) -> None:
    """Fail closed until the state migration physical matrix is accepted."""
    raise PermissionError(
        "state migration is inventory-only; apply is disabled until the platform "
        "upgrade/rollback matrix is accepted"
    )


def _ignored_runtime_path(relative: Path) -> bool:
    """Exclude temporary Python/cache files from the source/control inventory."""
    return any(part in {"__pycache__", ".pytest_cache"} for part in relative.parts)


def _entry_for_path(path: Path, relative: Path) -> StateEntry:
    """Build one entry without following symlink targets."""
    relative_text = relative.as_posix()
    if path.is_symlink():
        plane = _plane_for(relative)
        return StateEntry(plane, relative_text, "symlink", 0, None, "manual-review")
    if path.is_dir():
        return StateEntry(_plane_for(relative), relative_text, "directory", 0, None, "keep")
    if not path.is_file():
        return StateEntry(_plane_for(relative), relative_text, "special", 0, None, "manual-review")
    data = path.read_bytes()
    return StateEntry(
        _plane_for(relative),
        relative_text,
        "file",
        len(data),
        hashlib.sha256(data).hexdigest(),
        "keep" if _plane_for(relative) in {"source", "control", "evidence"} else "rebuildable",
    )


def _plane_for(relative: Path) -> str:
    """Classify a vault-relative path into the four state planes."""
    if relative.parts and relative.parts[0] == ".power":
        if len(relative.parts) > 1 and relative.parts[1] == "evidence":
            return "evidence"
        return "control"
    if relative.name == "POWER_STATUS.md" or relative.name == "log.md":
        return "control"
    return "source"


def _tree_size(path: Path) -> int:
    """Sum regular-file bytes without following symlinks."""
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.stat().st_size
    return total


def _payload_hash(payload: dict[str, object]) -> str:
    """Hash a JSON payload while excluding its derived hash field."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
