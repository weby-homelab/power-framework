from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING

from .task_models import PowerTask, TaskCompletionReceipt, TaskEvent, ensure_valid_task_id
from .utils import atomic_write

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows requires a separate lock adapter.
    fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


class TaskStore:
    """Filesystem-backed durable store for tasks, checkpoints, and event journals."""

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self.tasks_dir = self.vault_dir / ".power" / "tasks"
        self.events_dir = self.tasks_dir / "events"
        self.checkpoints_dir = self.tasks_dir / "checkpoints"
        self.receipts_dir = self.tasks_dir / "receipts"
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._lock_fd: IO[str] | None = None

    def _ensure_dirs(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self) -> Generator[None, None, None]:
        """Acquire a per-vault writer lock with thread reentrancy."""
        with self._thread_lock:
            self._ensure_dirs()
            lock_file = self.tasks_dir / ".lock"
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
    ) -> None:
        """Persist a task snapshot atomically and journal its event."""
        with self.lock():
            snapshot_file = self._task_file(task.task_id)
            previous_snapshot = self._read_text(snapshot_file)
            if event is not None and event.task_id != task.task_id:
                raise ValueError("Task snapshot and event task IDs must match")
            event_file = self._events_file(task.task_id)
            previous_events = self._read_text(event_file)
            checkpoint_file = self._checkpoint_file(event) if event is not None else None
            previous_checkpoint = (
                self._read_text(checkpoint_file) if checkpoint_file is not None else None
            )
            receipt_file = (
                self._completion_receipt_file(completion_receipt.receipt_id)
                if completion_receipt is not None
                else None
            )
            previous_receipt = self._read_text(receipt_file)
            if completion_receipt is not None:
                if completion_receipt.task_id != task.task_id:
                    raise ValueError("Completion receipt task ID does not match snapshot")
                if completion_receipt.task_revision != task.revision:
                    raise ValueError("Completion receipt revision does not match snapshot")
            try:
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
            except Exception:
                self._restore_text(snapshot_file, previous_snapshot)
                if event is not None:
                    self._restore_text(event_file, previous_events)
                    self._restore_text(checkpoint_file, previous_checkpoint)
                self._restore_text(receipt_file, previous_receipt)
                raise

    def append_event(self, event: TaskEvent) -> None:
        """Append an immutable event to the task event journal."""
        with self.lock():
            self._append_event_unlocked(event)

    def _append_event_unlocked(self, event: TaskEvent) -> None:
        ev_file = self._events_file(event.task_id)
        previous_events = self._read_text(ev_file)
        checkpoint_file = self._checkpoint_file(event)
        previous_checkpoint = self._read_text(checkpoint_file)
        try:
            existing = self.get_task_events(event.task_id)
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
        return path.read_text(encoding="utf-8")

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
            raw = json.loads(tf.read_text(encoding="utf-8"))
            return PowerTask.model_validate(raw)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed task snapshot {task_id}") from exc

    def get_completion_receipt(self, receipt_id: str) -> TaskCompletionReceipt | None:
        """Load one verified task completion receipt without creating storage."""
        receipt_file = self._completion_receipt_file(receipt_id)
        if not receipt_file.is_file():
            return None
        try:
            raw = json.loads(receipt_file.read_text(encoding="utf-8"))
            return TaskCompletionReceipt.model_validate(raw)
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

    def get_task_events(self, task_id: str, since_sequence: int = 0) -> list[TaskEvent]:
        """Retrieve events for a given task starting from since_sequence."""
        ev_file = self._events_file(task_id)
        if not ev_file.is_file():
            return []
        events: list[TaskEvent] = []
        with open(ev_file, encoding="utf-8") as f:
            expected_sequence = 1
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    ev_dict = json.loads(line)
                    ev = TaskEvent.model_validate(ev_dict)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"Malformed task event journal {ev_file.name} at line {line_number}"
                    ) from exc
                if ev.task_id != task_id:
                    raise ValueError("Task event task ID does not match its journal")
                if ev.sequence != expected_sequence:
                    raise ValueError("Task event journal sequence is not monotonic")
                expected_sequence += 1
                if ev.sequence > since_sequence:
                    events.append(ev)
        return events

    def get_last_event_digest(self, task_id: str) -> str:
        """Get the payload digest of the last recorded event for hash chaining."""
        events = self.get_task_events(task_id)
        if not events:
            return ""
        return events[-1].payload_digest


__all__ = ["TaskStore"]
