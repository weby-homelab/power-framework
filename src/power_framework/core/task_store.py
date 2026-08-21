from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import uuid
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from .fault_injection import fault_injector
from .task_models import (
    PowerTask,
    TaskCompletionReceipt,
    TaskEvent,
    canonical_payload_digest,
    ensure_valid_task_id,
)
from .utils import atomic_write

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows requires a separate lock adapter.
    fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

logger = logging.getLogger(__name__)


class TaskStore:
    """Filesystem-backed durable store for tasks, checkpoints, and event journals."""

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self.tasks_dir = self.vault_dir / ".power" / "tasks"
        self.events_dir = self.tasks_dir / "events"
        self.checkpoints_dir = self.tasks_dir / "checkpoints"
        self.receipts_dir = self.tasks_dir / "receipts"
        self.tx_dir = self.tasks_dir / ".tx"
        self.recovery_log = self.tasks_dir / "recovery.log"
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._lock_fd: IO[str] | None = None
        self._recovered = False

    def _ensure_dirs(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.tx_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self) -> Generator[None]:
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
                if not self._recovered:
                    self._recovered = True
                    self.recover()
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
            previous_digest = ""
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
                expected_previous = previous_digest
                if ev.prev_event_digest != expected_previous:
                    raise ValueError("Task event journal hash chain is invalid")
                if ev.payload_digest != canonical_payload_digest(ev.payload):
                    raise ValueError("Task event payload digest is invalid")
                previous_digest = ev.payload_digest
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
        import os
        import tempfile

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def _write_manifest(tx_dir: Path, manifest: dict[str, Any]) -> None:
        TaskStore._atomic_write_bytes(
            tx_dir / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )

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
        tx_dir.mkdir(parents=True, exist_ok=True)
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
            pre = path.read_bytes() if path.is_file() else None
            pre_digest = hashlib.sha256(pre).hexdigest() if pre is not None else None
            if pre is not None:
                with suppress(OSError):
                    (tx_dir / f"{label}.bak").write_bytes(pre)
            manifest["touched"].append(
                {
                    "label": label,
                    "rel": Path(path).relative_to(self.vault_dir).as_posix(),
                    "preimage_digest": pre_digest,
                }
            )
        self._write_manifest(tx_dir, manifest)
        fault_injector.maybe_raise(crash_point or op)
        try:
            yield
            for t in manifest["touched"]:
                p = self.vault_dir / t["rel"]
                post = p.read_bytes() if p.is_file() else None
                t["postimage_digest"] = (
                    hashlib.sha256(post).hexdigest() if post is not None else None
                )
            manifest["stage"] = "committed"
            self._write_manifest(tx_dir, manifest)
        except Exception:
            with suppress(Exception):
                self._rollback_tx(manifest, tx_dir)
            raise
        finally:
            shutil.rmtree(tx_dir, ignore_errors=True)

    def _rollback_tx(self, manifest: dict[str, Any], tx_dir: Path) -> None:
        """Restore touched artifacts to their preimage (fail closed on mismatch)."""
        for t in manifest.get("touched", []):
            p = self.vault_dir / t["rel"]
            pre = t.get("preimage_digest")
            if pre is None:
                p.unlink(missing_ok=True)
            else:
                bak = tx_dir / f"{t['label']}.bak"
                if not bak.is_file():
                    raise RuntimeError(f"recovery backup missing for {t['label']}")
                data = bak.read_bytes()
                if hashlib.sha256(data).hexdigest() != pre:
                    raise RuntimeError(f"recovery backup corrupted for {t['label']}")
                self._atomic_write_bytes(p, data)

    def _reconcile_tx(self, manifest: dict[str, Any], tx_dir: Path) -> str:
        """Classify a leftover manifest and roll back if inconsistent."""
        states: list[str] = []
        for t in manifest.get("touched", []):
            p = self.vault_dir / t["rel"]
            cur = p.read_bytes() if p.is_file() else None
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
        # Mixed / inconsistent -> deterministically roll back to preimages.
        self._rollback_tx(manifest, tx_dir)
        return "reconciled_rollback"

    def recover(self) -> list[dict[str, Any]]:
        """Reconcile any leftover transaction manifests from a dead process.

        Safe to call repeatedly (idempotent). Returns a list of recovery records
        and appends redacted observability entries to ``recovery.log`` (Phase K).
        """
        if fcntl is None:
            return []
        if not self.tx_dir.is_dir():
            return []
        results: list[dict[str, Any]] = []
        for entry in list(self.tx_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.is_file():
                shutil.rmtree(entry, ignore_errors=True)
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._log_recovery_record(
                    {
                        "tx_id": entry.name,
                        "op": "unknown",
                        "recovered_as": "fail_closed",
                        "reason": "corrupt_manifest",
                    }
                )
                shutil.rmtree(entry, ignore_errors=True)
                continue
            try:
                status = self._reconcile_tx(manifest, entry)
            except Exception as exc:
                self._log_recovery_record(
                    {
                        "tx_id": manifest.get("tx_id", entry.name),
                        "op": manifest.get("op", "unknown"),
                        "recovered_as": "fail_closed",
                        "reason": f"reconcile_error:{type(exc).__name__}",
                    }
                )
                shutil.rmtree(entry, ignore_errors=True)
                continue
            self._log_recovery_record(
                {
                    "tx_id": manifest.get("tx_id", entry.name),
                    "op": manifest.get("op", "unknown"),
                    "recovered_as": status,
                    "affected": [t.get("rel") for t in manifest.get("touched", [])],
                }
            )
            shutil.rmtree(entry, ignore_errors=True)
            results.append({"tx_id": manifest.get("tx_id"), "status": status})
        return results

    def _log_recovery_record(self, record: dict[str, Any]) -> None:
        """Append a redacted recovery observation (no note/proposal content)."""
        record = dict(record)
        record["ts"] = datetime.now(UTC).isoformat()
        try:
            with self.recovery_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            pass


__all__ = ["TaskStore"]
