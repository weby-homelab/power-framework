from __future__ import annotations

import contextlib
import json
import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING

from .task_models import PowerTask, TaskEvent
from .utils import atomic_write

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
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._lock_fd: IO[str] | None = None
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self) -> Generator[None, None, None]:
        """Acquire a per-vault writer lock with thread reentrancy."""
        with self._thread_lock:
            lock_file = self.tasks_dir / ".lock"
            if self._lock_depth == 0:
                try:
                    import fcntl

                    f = open(lock_file, "a+", encoding="utf-8")  # noqa: SIM115
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    self._lock_fd = f
                except Exception:
                    self._lock_fd = None
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if self._lock_depth == 0 and self._lock_fd is not None:
                    with contextlib.suppress(Exception):
                        import fcntl

                        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                        self._lock_fd.close()
                    self._lock_fd = None

    def _task_file(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def _events_file(self, task_id: str) -> Path:
        return self.events_dir / f"{task_id}.jsonl"

    def save_task(self, task: PowerTask, event: TaskEvent | None = None) -> None:
        """Persist a task snapshot atomically and journal its event."""
        with self.lock():
            data = task.model_dump()
            raw_json = json.dumps(data, indent=2, ensure_ascii=False)
            atomic_write(self._task_file(task.task_id), raw_json)

            if event is not None:
                self.append_event(event)

    def append_event(self, event: TaskEvent) -> None:
        """Append an immutable event to the task event journal."""
        ev_file = self._events_file(event.task_id)
        ev_data = event.model_dump()
        line = json.dumps(ev_data, ensure_ascii=False) + "\n"
        with open(ev_file, "a", encoding="utf-8") as f:
            f.write(line)

        # Checkpoint snapshot every 5 sequences
        if event.sequence % 5 == 0:
            cp_file = self.checkpoints_dir / f"{event.task_id}_seq_{event.sequence}.json"
            task = self.get_task(event.task_id)
            if task:
                atomic_write(cp_file, json.dumps(task.model_dump(), indent=2, ensure_ascii=False))

    def get_task(self, task_id: str) -> PowerTask | None:
        """Load a task by ID."""
        tf = self._task_file(task_id)
        if not tf.is_file():
            return None
        try:
            raw = json.loads(tf.read_text(encoding="utf-8"))
            return PowerTask.model_validate(raw)
        except Exception as exc:
            logger.warning("Failed to load task %s: %s", task_id, exc)
            return None

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
            for line in f:
                if not line.strip():
                    continue
                try:
                    ev_dict = json.loads(line)
                    ev = TaskEvent.model_validate(ev_dict)
                    if ev.sequence > since_sequence:
                        events.append(ev)
                except Exception:  # noqa: S112
                    continue
        events.sort(key=lambda e: e.sequence)
        return events

    def get_last_event_digest(self, task_id: str) -> str:
        """Get the payload digest of the last recorded event for hash chaining."""
        events = self.get_task_events(task_id)
        if not events:
            return ""
        return events[-1].payload_digest


__all__ = ["TaskStore"]
