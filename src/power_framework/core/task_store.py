from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import threading
import uuid
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from power_framework.core.lock_tracker import LockHierarchyTracker

from .errors import TaskJournalIntegrityError
from .fault_injection import fault_injector
from .models import VAULT_STRUCTURE
from .task_models import (
    PowerTask,
    TaskCompletionReceipt,
    TaskEvent,
    canonical_payload_digest,
    ensure_valid_task_id,
)
from .utils import atomic_write, vault_control_dir

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows requires a separate lock adapter.
    fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

logger = logging.getLogger(__name__)
_RECOVERY_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_TASK_STATE_BYTES = 10_000_000
_RECOVERY_OPERATION_LABELS: dict[str, frozenset[str]] = {
    "task_created": frozenset({"snapshot", "event", "checkpoint", "receipt"}),
    "migrated_from_v1": frozenset({"snapshot", "event", "checkpoint", "receipt"}),
    "state_transition": frozenset({"snapshot", "event", "checkpoint", "receipt"}),
    "task_event_append": frozenset({"event", "checkpoint"}),
    "task_snapshot": frozenset({"snapshot"}),
    "memory_apply": frozenset({"note", "history", "log"}),
    "decision_create": frozenset({"decision"}),
    "decision_resolve": frozenset({"decision", "receipt"}),
}


def _assert_no_symlink_components(path: Path) -> None:
    """Reject symlinked recovery-storage components before opening them."""

    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                raise ValueError("recovery storage must not contain symlinks")
        except OSError as exc:
            raise ValueError("recovery storage is unavailable") from exc


def _open_no_follow(path: Path, *, directory: bool = False) -> int:
    """Open an absolute path by traversing every component without symlinks."""

    candidate = Path(path).absolute()
    if not candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("recovery path contains unsafe components")
    components = candidate.parts
    if len(components) < 2:
        raise ValueError("recovery path must name a filesystem entry")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    parent_fd = os.open(components[0], directory_flags)
    try:
        for component in components[1:-1]:
            child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        final_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        if directory:
            final_flags |= getattr(os, "O_DIRECTORY", 0)
        return os.open(components[-1], final_flags, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def _fsync_directory(path: Path) -> None:
    """Durably publish recovery-state directory entries."""

    _assert_no_symlink_components(path)
    descriptor = _open_no_follow(path, directory=True)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_secure_bytes(path: Path, *, max_bytes: int = MAX_TASK_STATE_BYTES) -> bytes:
    """Read one bounded regular file without following a final symlink."""

    candidate = Path(path).absolute()
    _assert_no_symlink_components(candidate)
    before = candidate.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > max_bytes:
        raise ValueError("task state file is not a bounded regular file")
    descriptor = _open_no_follow(candidate)
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise ValueError("task state file changed during read")
        data = os.read(descriptor, max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("task state file exceeds its size limit")
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != len(data)
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise ValueError("task state file changed while it was read")
        return data
    finally:
        os.close(descriptor)


def _read_secure_text(path: Path, *, max_bytes: int = MAX_TASK_STATE_BYTES) -> str:
    """Read one bounded UTF-8 recovery/state file through the secure byte reader."""

    return _read_secure_bytes(path, max_bytes=max_bytes).decode("utf-8")


class TaskStore:
    """Filesystem-backed durable store for tasks, checkpoints, and event journals."""

    def __init__(self, vault_dir: Path, *, create_vault: bool = True) -> None:
        raw_vault_dir = Path(vault_dir).expanduser()
        if raw_vault_dir == raw_vault_dir.parent:
            raise ValueError("Vault path must be a dedicated directory, not the filesystem root")
        for parent in (raw_vault_dir, *raw_vault_dir.parents):
            if parent.is_symlink():
                raise ValueError("Vault path symlink ancestors are not followed")
        if not raw_vault_dir.exists():
            if not create_vault:
                raise FileNotFoundError(f"Vault path does not exist: {raw_vault_dir}")
            raw_vault_dir.mkdir(parents=True)
        self.vault_dir = raw_vault_dir.resolve()
        self.power_dir = vault_control_dir(self.vault_dir, create=False)
        self.tasks_dir = self.power_dir / "tasks"
        self.events_dir = self.tasks_dir / "events"
        self.checkpoints_dir = self.tasks_dir / "checkpoints"
        self.receipts_dir = self.tasks_dir / "receipts"
        self.tx_dir = self.tasks_dir / ".tx"
        self.recovery_log = self.tasks_dir / "recovery.log"
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._lock_fd: IO[str] | None = None
        self._recovered = False
        self._recovery_blocked = False

    def _ensure_dirs(self) -> None:
        for directory in (
            self.tasks_dir,
            self.events_dir,
            self.checkpoints_dir,
            self.receipts_dir,
            self.tx_dir,
        ):
            _assert_no_symlink_components(directory)
            if directory.is_symlink():
                raise ValueError(f"task state directory must not be a symlink: {directory}")
            directory.mkdir(parents=True, exist_ok=True)
            _assert_no_symlink_components(directory)

    @contextmanager
    def lock(self) -> Generator[None]:
        """Acquire a per-vault writer lock with thread reentrancy."""
        with (
            LockHierarchyTracker.hold_level(LockHierarchyTracker.LEVEL_TASK),
            self._thread_lock,
        ):
            self._ensure_dirs()
            lock_file = self.tasks_dir / ".lock"
            if lock_file.is_symlink():
                raise ValueError(f"task lock must not be a symlink: {lock_file}")
            if self._recovery_blocked:
                raise RuntimeError(
                    "TaskStore recovery is blocked; repair preserved transaction evidence"
                )
            if self._lock_depth == 0:
                if fcntl is None:
                    raise RuntimeError("Task writer locking is unavailable")
                lock_handle: IO[str] = open(lock_file, "a+", encoding="utf-8")  # noqa: SIM115
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                except OSError as exc:
                    lock_handle.close()
                    raise RuntimeError("Unable to acquire task writer lock") from exc
                self._lock_fd = lock_handle
                if not self._recovered:
                    try:
                        self.recover()
                        if self._recovery_blocked:
                            raise RuntimeError(
                                "TaskStore recovery is blocked; repair preserved transaction evidence"
                            )
                    except Exception:
                        self._lock_fd = None
                        with suppress(OSError):
                            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                        lock_handle.close()
                        raise
                    self._recovered = True
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if self._lock_depth == 0 and self._lock_fd is not None:
                    lock_handle = self._lock_fd
                    self._lock_fd = None
                    try:
                        if fcntl is None:
                            raise RuntimeError("Task writer locking is unavailable")
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    except OSError as exc:
                        raise RuntimeError("Unable to release task writer lock") from exc
                    finally:
                        lock_handle.close()

    def _task_file(self, task_id: str) -> Path:
        ensure_valid_task_id(task_id)
        return self.tasks_dir / f"{task_id}.json"

    def _events_file(self, task_id: str) -> Path:
        ensure_valid_task_id(task_id)
        return self.events_dir / f"{task_id}.jsonl"

    def save_task(
        self,
        task: PowerTask,
        event: TaskEvent | None = None,
        completion_receipt: TaskCompletionReceipt | None = None,
        *,
        idempotency_key: str | None = None,
        command_sha256: str | None = None,
        crash_point: str | None = None,
    ) -> None:
        """Persist a task snapshot atomically and journal its event."""
        with self.lock():
            snapshot_file = self._task_file(task.task_id)
            if event is not None and event.task_id != task.task_id:
                raise ValueError("Task snapshot and event task IDs must match")
            if snapshot_file.is_file():
                self.get_task_events(task.task_id)
            event_file = self._events_file(task.task_id)
            checkpoint_file = self._checkpoint_file(event) if event is not None else None
            receipt_file = (
                self._completion_receipt_file(completion_receipt.receipt_id)
                if completion_receipt is not None
                else None
            )
            if completion_receipt is not None:
                if completion_receipt.task_id != task.task_id:
                    raise ValueError("Completion receipt task ID does not match snapshot")
                if completion_receipt.task_revision != task.revision:
                    raise ValueError("Completion receipt revision does not match snapshot")
            op = event.event_type if event is not None else "task_snapshot"
            touched: list[tuple[Path, str]] = [(snapshot_file, "snapshot")]
            if event is not None:
                touched.append((event_file, "event"))
                if event.sequence % 5 == 0 and checkpoint_file is not None:
                    touched.append((checkpoint_file, "checkpoint"))
            if receipt_file is not None:
                touched.append((receipt_file, "receipt"))
            with self._transaction(
                op, idempotency_key, command_sha256, touched, crash_point=crash_point
            ):
                data = task.model_dump()
                raw_json = json.dumps(data, indent=2, ensure_ascii=False)
                atomic_write(snapshot_file, raw_json)
                if completion_receipt is not None:
                    assert receipt_file is not None
                    atomic_write(
                        receipt_file,
                        json.dumps(
                            completion_receipt.model_dump(),
                            indent=2,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                if event is not None:
                    self._append_event_unlocked(event)

    def append_event(self, event: TaskEvent) -> None:
        """Append an immutable event to the task event journal."""
        with self.lock():
            if self._task_file(event.task_id).is_file():
                self.get_task_events(event.task_id)
            ev_file = self._events_file(event.task_id)
            checkpoint_file = self._checkpoint_file(event)
            touched: list[tuple[Path, str]] = [(ev_file, "event")]
            if event.sequence % 5 == 0:
                touched.append((checkpoint_file, "checkpoint"))
            with self._transaction("task_event_append", None, None, touched):
                self._append_event_unlocked(event)

    def _append_event_unlocked(self, event: TaskEvent) -> None:
        ev_file = self._events_file(event.task_id)
        previous_events = self._read_text(ev_file)
        checkpoint_file = self._checkpoint_file(event)
        previous_checkpoint = self._read_text(checkpoint_file)
        try:
            existing = self.get_task_events(event.task_id, allow_missing=True)
            if existing and event.sequence <= existing[-1].sequence:
                raise ValueError("Task event sequence must be strictly increasing")
            ev_data = event.model_dump()
            line = json.dumps(ev_data, ensure_ascii=False) + "\n"
            atomic_write(ev_file, f"{previous_events or ''}{line}")

            if event.sequence % 5 == 0:
                task = self.get_task(event.task_id)
                if task:
                    atomic_write(
                        checkpoint_file,
                        json.dumps(task.model_dump(), indent=2, ensure_ascii=False),
                    )
        except Exception:
            self._restore_text(ev_file, previous_events)
            self._restore_text(checkpoint_file, previous_checkpoint)
            raise

    def _checkpoint_file(self, event: TaskEvent) -> Path:
        ensure_valid_task_id(event.task_id)
        return self.checkpoints_dir / f"{event.task_id}_seq_{event.sequence}.json"

    def _completion_receipt_file(self, receipt_id: str) -> Path:
        TaskCompletionReceipt.validate_receipt_id(receipt_id)
        return self.receipts_dir / f"{receipt_id}.json"

    @staticmethod
    def _read_text(path: Path | None) -> str | None:
        if path is None or not path.is_file():
            return None
        return _read_secure_text(path)

    @staticmethod
    def _restore_text(path: Path | None, content: str | None) -> None:
        if path is None:
            return
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, content)

    def get_task(self, task_id: str) -> PowerTask | None:
        """Load a task by ID."""
        tf = self._task_file(task_id)
        if not tf.is_file():
            return None
        try:
            raw = json.loads(_read_secure_text(tf))
            return PowerTask.model_validate(raw)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed task snapshot {task_id}") from exc

    def get_completion_receipt(self, receipt_id: str) -> TaskCompletionReceipt | None:
        """Load one verified task completion receipt without creating storage."""
        receipt_file = self._completion_receipt_file(receipt_id)
        if not receipt_file.is_file():
            return None
        try:
            raw = json.loads(_read_secure_text(receipt_file))
            receipt = TaskCompletionReceipt.model_validate(raw)
            expected_id = TaskCompletionReceipt.derive_receipt_id(
                task_id=receipt.task_id,
                task_revision=receipt.task_revision,
                completion_policy=receipt.completion_policy,
                postcondition_sha256=receipt.postcondition_sha256,
                artifact_digests=receipt.artifact_digests,
                actor=receipt.actor,
            )
            if receipt.receipt_id != expected_id:
                raise ValueError("Task completion receipt derivation mismatch")
            return receipt
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed task completion receipt {receipt_id}") from exc

    def list_tasks(
        self,
        *,
        state: str | None = None,
        owner: str | None = None,
        assignee: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PowerTask]:
        """List tasks matching filters ordered by updated_at descending."""
        results: list[PowerTask] = []
        if not self.tasks_dir.is_dir():
            return []

        for p in self.tasks_dir.glob("*.json"):
            if p.name.startswith("."):
                continue
            task = self.get_task(p.stem)
            if not task:
                continue
            if state and task.state != state:
                continue
            if owner and task.owner != owner:
                continue
            if assignee and task.assignee != assignee:
                continue
            results.append(task)

        # Sort by updated_at descending
        results.sort(key=lambda t: t.updated_at, reverse=True)
        return results[offset : offset + limit]

    def get_task_events(
        self, task_id: str, since_sequence: int = 0, *, allow_missing: bool = False
    ) -> list[TaskEvent]:
        """Retrieve events for a given task starting from since_sequence."""
        ev_file = self._events_file(task_id)
        if not ev_file.is_file():
            if self._task_file(task_id).is_file() and not allow_missing:
                raise TaskJournalIntegrityError("Task event journal is missing")
            return []
        events: list[TaskEvent] = []
        raw_events = _read_secure_text(ev_file)
        if not raw_events.strip() and self._task_file(task_id).is_file() and not allow_missing:
            raise TaskJournalIntegrityError("Task event journal is empty")
        expected_sequence = 1
        previous_digest = ""
        for line_number, line in enumerate(raw_events.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                ev_dict = json.loads(line)
                ev = TaskEvent.model_validate(ev_dict)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise TaskJournalIntegrityError(
                    f"Malformed task event journal {ev_file.name} at line {line_number}"
                ) from exc
            if ev.task_id != task_id:
                raise TaskJournalIntegrityError("Task event task ID does not match its journal")
            if ev.sequence != expected_sequence:
                raise TaskJournalIntegrityError("Task event journal sequence is not monotonic")
            expected_previous = previous_digest
            if ev.prev_event_digest != expected_previous:
                raise TaskJournalIntegrityError("Task event journal hash chain is invalid")
            if ev.payload_digest != canonical_payload_digest(ev.payload):
                raise TaskJournalIntegrityError("Task event payload digest is invalid")
            previous_digest = ev.payload_digest
            expected_sequence += 1
            if ev.sequence > since_sequence:
                events.append(ev)
        if expected_sequence == 1 and self._task_file(task_id).is_file() and not allow_missing:
            raise TaskJournalIntegrityError("Task event journal is empty")
        return events

    def get_last_event_digest(self, task_id: str) -> str:
        """Get the payload digest of the last recorded event for hash chaining."""
        events = self.get_task_events(task_id)
        if not events:
            return ""
        return events[-1].payload_digest

    def delete_task(self, task_id: str) -> None:
        """Remove a task and its canonical artifacts (migration rollback only)."""
        with self.lock():
            self._task_file(task_id).unlink(missing_ok=True)
            self._events_file(task_id).unlink(missing_ok=True)
            for cp in self.checkpoints_dir.glob(f"{task_id}_seq_*.json"):
                cp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Crash-recovery transaction manifest (Phase B / 3.6.4)
    # ------------------------------------------------------------------
    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        """Write bytes atomically via temp file + rename."""
        import tempfile

        path = Path(path)
        _assert_no_symlink_components(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_components(path.parent)
        if path.exists() and path.is_symlink():
            raise ValueError("recovery target must not be a symlink")
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        published = False
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
            published = True
            _fsync_directory(path.parent)
        finally:
            if not published:
                with suppress(OSError):
                    os.unlink(tmp_path)

    @staticmethod
    def _write_manifest(tx_dir: Path, manifest: dict[str, Any]) -> None:
        TaskStore._atomic_write_bytes(
            tx_dir / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )

    def _recovery_path(self, value: object) -> Path:
        """Resolve a manifest path only inside the canonical vault boundary."""

        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("recovery path is invalid")
        relative = Path(value)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("recovery path must be a safe vault-relative path")
        current = self.vault_dir
        for component in relative.parts:
            current /= component
            if current.is_symlink():
                raise ValueError("recovery path must not traverse a symlink")
        candidate = self.vault_dir / relative
        if not candidate.is_relative_to(self.vault_dir):
            raise ValueError("recovery path escaped the vault")
        return candidate

    def _allowed_recovery_path(
        self, label: object, value: object, operation: object | None = None
    ) -> Path:
        """Restrict recovery artifacts to the exact TaskStore file classes."""

        safe_label = self._recovery_label(label)
        if not isinstance(operation, str) or safe_label not in _RECOVERY_OPERATION_LABELS.get(
            operation, frozenset()
        ):
            raise ValueError("recovery label is not allowed for this operation")
        candidate = self._recovery_path(value)
        vault_relative = candidate.relative_to(self.vault_dir)
        relative = (
            candidate.relative_to(self.tasks_dir)
            if candidate.is_relative_to(self.tasks_dir)
            else None
        )
        task_id = relative.name.removesuffix(".json").removesuffix(".jsonl") if relative else ""
        if (
            safe_label == "snapshot"
            and relative is not None
            and relative.parent == Path(".")
            and relative.name.endswith(".json")
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_id)
        ):
            return candidate
        if (
            safe_label == "event"
            and relative is not None
            and relative.parent == Path("events")
            and relative.name.endswith(".jsonl")
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_id)
        ):
            return candidate
        if (
            safe_label == "checkpoint"
            and relative is not None
            and relative.parent == Path("checkpoints")
            and relative.name.endswith(".json")
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}_seq_[0-9]+", task_id)
        ):
            return candidate
        if (
            safe_label == "receipt"
            and relative is not None
            and (
                (
                    operation in {"task_created", "migrated_from_v1", "state_transition"}
                    and relative.parent == Path("receipts")
                    and re.fullmatch(r"tcr_[0-9a-f]{64}", task_id)
                )
                or (
                    operation == "decision_resolve"
                    and relative.parent == Path("decisions/receipts")
                    and re.fullmatch(r"dcr_[0-9a-f]{64}", task_id)
                )
            )
        ):
            return candidate
        if (
            safe_label == "decision"
            and relative is not None
            and relative.parent == Path("decisions")
            and relative.name.endswith(".json")
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_id)
        ):
            return candidate
        if safe_label == "history" and vault_relative == Path(".power/memory-history.jsonl"):
            return candidate
        if safe_label == "log" and operation == "memory_apply" and vault_relative == Path("log.md"):
            return candidate
        if (
            safe_label == "note"
            and operation == "memory_apply"
            and candidate.suffix == ".md"
            and vault_relative.parts
            and (len(vault_relative.parts) == 1 or vault_relative.parts[0] in VAULT_STRUCTURE)
            and not candidate.is_relative_to(self.power_dir)
        ):
            return candidate
        raise ValueError("recovery artifact is outside the TaskStore file classes")

    @staticmethod
    def _recovery_label(value: object) -> str:
        """Validate the backup filename stem from a recovery manifest."""

        if not isinstance(value, str) or not _RECOVERY_LABEL_PATTERN.fullmatch(value):
            raise ValueError("recovery label is invalid")
        return value

    def _validate_recovery_manifest(self, manifest: object, tx_id: str) -> dict[str, Any]:
        """Validate untrusted recovery metadata before any filesystem mutation."""

        if not isinstance(manifest, dict):
            raise ValueError("recovery manifest is not an object")
        required = {
            "tx_id",
            "op",
            "idempotency_key",
            "command_sha256",
            "stage",
            "created_at",
            "vault",
            "touched",
        }
        if set(manifest) != required:
            raise ValueError("recovery manifest schema is invalid")
        if manifest["tx_id"] != tx_id or manifest["vault"] != self.vault_dir.as_posix():
            raise ValueError("recovery manifest binding is invalid")
        if manifest["stage"] not in {"prepared", "committed"}:
            raise ValueError("recovery manifest stage is invalid")
        if not isinstance(manifest["op"], str) or manifest["op"] not in _RECOVERY_OPERATION_LABELS:
            raise ValueError("recovery manifest operation is invalid")
        if manifest["idempotency_key"] is not None and not isinstance(
            manifest["idempotency_key"], str
        ):
            raise ValueError("recovery manifest idempotency key is invalid")
        command_sha256 = manifest["command_sha256"]
        if command_sha256 is not None and (
            not isinstance(command_sha256, str)
            or not command_sha256
            or len(command_sha256) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in command_sha256)
        ):
            raise ValueError("recovery manifest command digest is invalid")
        created_at = manifest["created_at"]
        if not isinstance(created_at, str):
            raise ValueError("recovery manifest timestamp is invalid")
        parsed_created_at = datetime.fromisoformat(created_at)
        if parsed_created_at.tzinfo is None:
            raise ValueError("recovery manifest timestamp must include timezone")
        touched = manifest["touched"]
        if not isinstance(touched, list) or len(touched) > 256:
            raise ValueError("recovery manifest touched list is invalid")
        for item in touched:
            if not isinstance(item, dict) or set(item) not in (
                {"label", "rel", "preimage_digest"},
                {"label", "rel", "preimage_digest", "postimage_digest"},
            ):
                raise ValueError("recovery manifest entry is invalid")
            if manifest["stage"] == "committed" and set(item) != {
                "label",
                "rel",
                "preimage_digest",
                "postimage_digest",
            }:
                raise ValueError("committed recovery entry requires a postimage digest")
            self._recovery_label(item["label"])
            self._allowed_recovery_path(item["label"], item["rel"], manifest["op"])
            for field in ("preimage_digest", "postimage_digest"):
                digest = item.get(field)
                if digest is not None and (
                    not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                ):
                    raise ValueError("recovery manifest image digest is invalid")
        return manifest

    @contextmanager
    def _transaction(
        self,
        op: str,
        idempotency_key: str | None,
        command_sha256: str | None,
        touched: list[tuple[Path, str]],
        *,
        crash_point: str | None = None,
    ) -> Iterator[None]:
        """Run a transaction while holding the canonical TaskStore lock."""

        with (
            self.lock(),
            self._transaction_locked(
                op,
                idempotency_key,
                command_sha256,
                touched,
                crash_point=crash_point,
            ),
        ):
            yield

    @contextmanager
    def _transaction_locked(
        self,
        op: str,
        idempotency_key: str | None,
        command_sha256: str | None,
        touched: list[tuple[Path, str]],
        *,
        crash_point: str | None = None,
    ) -> Iterator[None]:
        """Wrap a multi-artifact write in a recoverable transaction manifest.

        Writes a ``prepared`` manifest + preimage backups, runs the write body,
        then flips the manifest to ``committed`` and cleans up. A hard process
        kill leaves the manifest on disk; :meth:`recover` reconciles it on the
        next process start (deterministic, idempotent, fail-closed).

        ``crash_point`` names a deterministic fault-injection hook (see
        :mod:`power_framework.core.fault_injection`); when armed, the fault is
        raised right after the ``prepared`` manifest is durable -- reproducing a
        hard kill between manifest and postimage copies.
        """
        tx_id = uuid.uuid4().hex
        tx_dir = self.tx_dir / tx_id
        _assert_no_symlink_components(self.tx_dir)
        tx_dir.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_components(tx_dir)
        _fsync_directory(self.tx_dir)
        manifest: dict[str, Any] = {
            "tx_id": tx_id,
            "op": op,
            "idempotency_key": idempotency_key,
            "command_sha256": command_sha256,
            "stage": "prepared",
            "created_at": datetime.now(UTC).isoformat(),
            "vault": self.vault_dir.as_posix(),
            "touched": [],
        }
        for path, label in touched:
            if path is None:
                continue
            safe_label = self._recovery_label(label)
            relative_path = path.relative_to(self.vault_dir).as_posix()
            self._allowed_recovery_path(safe_label, relative_path, op)
            pre = _read_secure_bytes(path) if path.is_file() else None
            pre_digest = hashlib.sha256(pre).hexdigest() if pre is not None else None
            if pre is not None:
                self._atomic_write_bytes(tx_dir / f"{safe_label}.bak", pre)
            manifest["touched"].append(
                {
                    "label": safe_label,
                    "rel": relative_path,
                    "preimage_digest": pre_digest,
                }
            )
        self._write_manifest(tx_dir, manifest)
        fault_injector.maybe_raise(crash_point or op)
        cleanup_tx = True
        try:
            yield
            for t in manifest["touched"]:
                p = self._allowed_recovery_path(t["label"], t["rel"], op)
                post = _read_secure_bytes(p) if p.is_file() else None
                t["postimage_digest"] = (
                    hashlib.sha256(post).hexdigest() if post is not None else None
                )
            manifest["stage"] = "committed"
            self._write_manifest(tx_dir, manifest)
        except Exception:
            try:
                self._rollback_tx(manifest, tx_dir)
            except Exception as rollback_error:
                cleanup_tx = False
                self._recovery_blocked = True
                raise RuntimeError(
                    "task transaction rollback failed; recovery evidence preserved"
                ) from rollback_error
            raise
        finally:
            if cleanup_tx:
                shutil.rmtree(tx_dir, ignore_errors=True)

    def _rollback_tx(self, manifest: dict[str, Any], tx_dir: Path) -> None:
        """Restore touched artifacts to their preimage (fail closed on mismatch)."""
        for t in manifest.get("touched", []):
            p = self._allowed_recovery_path(t.get("label"), t.get("rel"), manifest.get("op"))
            pre = t.get("preimage_digest")
            if pre is None:
                p.unlink(missing_ok=True)
            else:
                label = self._recovery_label(t.get("label"))
                bak = tx_dir / f"{label}.bak"
                _assert_no_symlink_components(bak)
                metadata = bak.lstat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise RuntimeError(f"recovery backup missing for {t['label']}")
                data = _read_secure_bytes(bak)
                if hashlib.sha256(data).hexdigest() != pre:
                    raise RuntimeError(f"recovery backup corrupted for {t['label']}")
                self._atomic_write_bytes(p, data)

    def _reconcile_tx(self, manifest: dict[str, Any], tx_dir: Path) -> str:
        """Classify a leftover manifest and roll back if inconsistent."""
        states: list[str] = []
        for t in manifest.get("touched", []):
            p = self._allowed_recovery_path(t.get("label"), t.get("rel"), manifest.get("op"))
            cur = _read_secure_bytes(p) if p.is_file() else None
            cur_digest = hashlib.sha256(cur).hexdigest() if cur is not None else None
            pre = t.get("preimage_digest")
            post = t.get("postimage_digest")
            if post is not None and cur_digest == post:
                states.append("post")
            elif (pre is None and cur is None) or (pre is not None and cur_digest == pre):
                states.append("pre")
            else:
                states.append("mixed")
        if states and all(s == "post" for s in states):
            return "committed"
        if states and all(s == "pre" for s in states):
            return "rolled_back"
        if manifest.get("stage") == "prepared":
            self._rollback_tx(manifest, tx_dir)
            return "reconciled_rollback"
        raise RuntimeError("committed task transaction has mixed state; operator recovery required")

    def recover(self) -> list[dict[str, Any]]:
        """Reconcile any leftover transaction manifests from a dead process.

        Safe to call repeatedly (idempotent). Returns a list of recovery records
        and appends redacted observability entries to ``recovery.log`` (Phase K).
        """
        if fcntl is None:
            return []
        _assert_no_symlink_components(self.tx_dir)
        _assert_no_symlink_components(self.recovery_log.parent)
        if self.recovery_log.exists() and self.recovery_log.is_symlink():
            raise ValueError("recovery log must not be a symlink")
        if not self.tx_dir.is_dir():
            return []
        results: list[dict[str, Any]] = []
        for entry in list(self.tx_dir.iterdir()):
            if entry.is_symlink():
                raise ValueError("transaction entry must not be a symlink")
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            _assert_no_symlink_components(manifest_path)
            if not manifest_path.is_file():
                self._recovery_blocked = True
                continue
            try:
                manifest = json.loads(_read_secure_text(manifest_path))
                manifest = self._validate_recovery_manifest(manifest, entry.name)
            except (OSError, TypeError, ValueError):
                self._recovery_blocked = True
                self._log_recovery_record(
                    {
                        "tx_id": entry.name,
                        "op": "unknown",
                        "recovered_as": "fail_closed",
                        "reason": "corrupt_manifest",
                    }
                )
                continue
            try:
                status = self._reconcile_tx(manifest, entry)
            except Exception as exc:
                self._recovery_blocked = True
                self._log_recovery_record(
                    {
                        "tx_id": manifest.get("tx_id", entry.name),
                        "op": manifest.get("op", "unknown"),
                        "recovered_as": "fail_closed",
                        "reason": f"reconcile_error:{type(exc).__name__}",
                    }
                )
                continue
            if not self._log_recovery_record(
                {
                    "tx_id": manifest.get("tx_id", entry.name),
                    "op": manifest.get("op", "unknown"),
                    "recovered_as": status,
                    "affected": [t.get("rel") for t in manifest.get("touched", [])],
                }
            ):
                self._recovery_blocked = True
                continue
            shutil.rmtree(entry, ignore_errors=True)
            results.append({"tx_id": manifest.get("tx_id"), "status": status})
        return results

    def _log_recovery_record(self, record: dict[str, Any]) -> bool:
        """Append a redacted recovery observation (no note/proposal content)."""
        record = dict(record)
        record["ts"] = datetime.now(UTC).isoformat()
        try:
            _assert_no_symlink_components(self.recovery_log)
            if self.recovery_log.exists():
                metadata = self.recovery_log.lstat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise ValueError("recovery log must be a single-link regular file")
            fd = os.open(
                self.recovery_log,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            return True
        except (OSError, ValueError):
            return False


__all__ = ["TaskStore"]
