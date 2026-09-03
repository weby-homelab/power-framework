"""POWER Project State Engine (PSE) Canonical Event Store.

Implements:
- Append-only event ledger at .power/projects/<project_id>/events.jsonl
- Level 3 Lock: .power/projects/<project_id>/.lock (fcntl.flock + threading.RLock)
- ADR-PSE-007 Lock Hierarchy enforcement (Mutation L1 -> Task L2 -> Project L3)
- Bounded timeout with LockAcquisitionTimeoutError
- Monotonic sequence assignment & SHA-256 two-tier hash chain
- Crash recovery / torn-tail truncation to last valid cryptographic record
- Safe ledger rotation without breaking global replay order
- Strict project boundary isolation & symlink rejection
- Idempotent deduplication by idempotency_key or deterministic event_id
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

from power_framework.core.canonical_json import (
    canonical_json_dumps,
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.project_models import (
    AppendCommand,
    LedgerVerificationResult,
    ProjectEvent,
    validate_project_id,
)

logger = logging.getLogger(__name__)


class LockAcquisitionTimeoutError(TimeoutError):
    """Raised when lock acquisition exceeds the configured timeout."""


class LockHierarchyTracker:
    """Thread-local tracker for the strict 3-level lock acquisition hierarchy (ADR-PSE-007).

    Level 1: Vault Mutation Lock (.power/mutation.lock)
    Level 2: TaskStore Process Lock (.power/tasks/.lock)
    Level 3: PSE Project Process Lock (.power/projects/<project_id>/.lock)
    """

    LEVEL_MUTATION = 1
    LEVEL_TASK = 2
    LEVEL_PROJECT = 3

    _local = threading.local()

    @classmethod
    def get_held_levels(cls) -> list[int]:
        if not hasattr(cls._local, "levels"):
            cls._local.levels = []
        return cast("list[int]", cls._local.levels)

    @classmethod
    def push_level(cls, level: int) -> None:
        held = cls.get_held_levels()
        if held and max(held) > level:
            raise RuntimeError(
                f"Lock hierarchy violation: cannot acquire Level {level} while holding Level {max(held)}. "
                "Locks must strictly be acquired in ascending order (Level 1: Mutation -> Level 2: Task -> Level 3: Project)."
            )
        held.append(level)

    @classmethod
    def pop_level(cls, level: int) -> None:
        held = cls.get_held_levels()
        if held and held[-1] == level:
            held.pop()
        elif level in held:
            held.remove(level)


_project_thread_locks: dict[str, threading.RLock] = {}
_project_thread_locks_guard = threading.Lock()


def _get_project_thread_lock(project_dir: Path) -> threading.RLock:
    key = str(project_dir.resolve())
    with _project_thread_locks_guard:
        if key not in _project_thread_locks:
            _project_thread_locks[key] = threading.RLock()
        return _project_thread_locks[key]


def get_projects_dir(vault_root: Path) -> Path:
    """Resolve and validate the root projects directory."""
    root = Path(vault_root).expanduser().resolve()
    if root.is_symlink():
        raise ValueError(f"Vault root must not be a symlink: {vault_root}")
    projects_dir = root / ".power" / "projects"
    if projects_dir.is_symlink():
        raise ValueError(f"Projects directory must not be a symlink: {projects_dir}")
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir.resolve()


def get_project_dir(project_id: str, vault_root: Path) -> Path:
    """Validate project ID and safely resolve its directory, preventing traversal and symlink escapes."""
    validate_project_id(project_id)
    projects_dir = get_projects_dir(vault_root)
    project_dir = projects_dir / project_id
    if project_dir.is_symlink():
        raise ValueError(f"Project directory must not be a symlink: {project_dir}")

    resolved = project_dir.resolve()
    try:
        resolved.relative_to(projects_dir)
    except ValueError as exc:
        raise ValueError(f"Project path escapes vault boundary: {project_id}") from exc

    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


@contextlib.contextmanager
def project_lock(
    project_id: str,
    vault_root: Path,
    timeout: float = 10.0,
) -> Iterator[Path]:
    """Level 3 fine-grained project lock context manager (ADR-PSE-007)."""
    project_dir = get_project_dir(project_id, vault_root)
    lock_file = project_dir / ".lock"
    if lock_file.is_symlink():
        raise ValueError(f"Project lock must not be a symlink: {lock_file}")

    thread_lock = _get_project_thread_lock(project_dir)
    acquired_thread = thread_lock.acquire(timeout=timeout)
    if not acquired_thread:
        raise LockAcquisitionTimeoutError(
            f"Intra-process thread lock timeout for {project_id} after {timeout}s"
        )

    try:
        LockHierarchyTracker.push_level(LockHierarchyTracker.LEVEL_PROJECT)
        try:
            fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                deadline = time.monotonic() + timeout
                locked = False
                while time.monotonic() < deadline:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        break
                    except (BlockingIOError, OSError):
                        time.sleep(0.01)

                if not locked:
                    raise LockAcquisitionTimeoutError(
                        f"Inter-process lock acquisition timed out after {timeout}s for project {project_id}"
                    )
                try:
                    yield project_dir
                finally:
                    with contextlib.suppress(OSError):
                        fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        finally:
            LockHierarchyTracker.pop_level(LockHierarchyTracker.LEVEL_PROJECT)
    finally:
        thread_lock.release()


def recover_torn_tail(file_path: Path) -> int:
    """Detect and truncate incomplete or corrupted trailing line at EOF.

    Returns the number of bytes truncated (0 if no truncation was performed).
    Non-trailing corruptions are preserved so integrity verification can detect them.
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        return 0

    if file_path.is_symlink():
        raise ValueError(f"Ledger file must not be a symlink: {file_path}")

    with open(file_path, "rb") as f:
        content = f.read()

    if not content:
        return 0

    lines = content.splitlines(keepends=True)
    if not lines:
        return 0

    valid_up_to = 0
    for i, line in enumerate(lines):
        is_last = i == len(lines) - 1
        line_valid = False

        if line.endswith(b"\n"):
            try:
                line_str = line.decode("utf-8")
                data = json.loads(line_str)
                if isinstance(data, dict) and "event_hash" in data and "payload_digest" in data:
                    calc_hash = compute_event_hash(data)
                    if calc_hash == data["event_hash"]:
                        line_valid = True
            except Exception:
                line_valid = False

        if line_valid:
            valid_up_to += len(line)
        else:
            if is_last:
                # Torn tail at EOF!
                truncated_bytes = len(content) - valid_up_to
                logger.warning(
                    f"Truncating torn tail in {file_path}: discarded {truncated_bytes} bytes from EOF"
                )
                with open(file_path, "wb") as f_out:
                    f_out.write(content[:valid_up_to])
                    f_out.flush()
                    os.fsync(f_out.fileno())
                return truncated_bytes
            # Non-trailing corruption; keep intact for integrity detection
            break

    return 0


class ProjectEventStore:
    """Durable append-only event store for a single project."""

    def __init__(self, project_id: str, vault_root: Path) -> None:
        self.project_id = validate_project_id(project_id)
        self.vault_root = Path(vault_root).expanduser().resolve()
        self.project_dir = get_project_dir(self.project_id, self.vault_root)
        self.active_events_file = self.project_dir / "events.jsonl"

    def list_event_files(self) -> list[Path]:
        """Return all event files for this project in deterministic replay order."""
        if not self.project_dir.exists():
            return []

        rotated: list[Path] = []
        for p in self.project_dir.iterdir():
            if p.is_file() and p.name.startswith("events_") and p.name.endswith(".jsonl"):
                if p.is_symlink():
                    raise ValueError(f"Rotated event file must not be a symlink: {p}")
                rotated.append(p)

        rotated.sort(key=lambda p: p.name)
        result = list(rotated)
        if self.active_events_file.exists():
            if self.active_events_file.is_symlink():
                raise ValueError(f"Active event file must not be a symlink: {self.active_events_file}")
            result.append(self.active_events_file)
        return result

    def append(self, command: AppendCommand, timeout: float = 10.0) -> ProjectEvent:
        """Append an event under Level 3 project lock with atomic fsync and idempotency deduplication."""
        if command.project_id != self.project_id:
            raise ValueError(
                f"Command project_id '{command.project_id}' does not match store '{self.project_id}'"
            )

        with project_lock(self.project_id, self.vault_root, timeout=timeout):
            # 1. Crash recovery on active file if present
            if self.active_events_file.exists():
                recover_torn_tail(self.active_events_file)

            # 2. Idempotency and tail inspection
            last_sequence = 0
            last_event_hash = ""

            for event in self.replay(from_sequence=1):
                if command.idempotency_key and event.idempotency_key == command.idempotency_key:
                    logger.info(
                        f"Idempotent match for key {command.idempotency_key} on project {self.project_id}"
                    )
                    return event
                if command.event_id and event.event_id == command.event_id:
                    logger.info(
                        f"Idempotent match for event_id {command.event_id} on project {self.project_id}"
                    )
                    return event

                last_sequence = event.sequence
                last_event_hash = event.event_hash

            new_sequence = last_sequence + 1
            prev_event_hash = "" if new_sequence == 1 else last_event_hash

            timestamp = command.timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z")
            event_id = command.event_id or f"evt_{self.project_id}_{new_sequence}_{uuid.uuid4().hex[:12]}"
            payload_digest = compute_payload_digest(command.payload)

            raw_envelope: dict[str, Any] = {
                "event_id": event_id,
                "schema_version": "power.project-event.v1",
                "project_id": self.project_id,
                "sequence": new_sequence,
                "timestamp": timestamp,
                "actor": command.actor,
                "source": command.source,
                "session_id": command.session_id,
                "event_type": command.event_type,
                "payload": command.payload,
                "payload_digest": payload_digest,
                "prev_event_hash": prev_event_hash,
                "artifact_refs": command.artifact_refs,
                "evidence_refs": command.evidence_refs,
                "correlation_id": command.correlation_id,
                "causation_id": command.causation_id,
                "idempotency_key": command.idempotency_key,
            }

            event_hash = compute_event_hash(raw_envelope)
            raw_envelope["event_hash"] = event_hash

            event = ProjectEvent.model_validate(raw_envelope)

            # 3. Durable write with atomic fsync
            line = canonical_json_dumps(event.model_dump()) + "\n"
            with open(self.active_events_file, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

            return event

    def replay(self, from_sequence: int = 1) -> Iterator[ProjectEvent]:
        """Deterministically read and yield ProjectEvents starting from sequence."""
        for file_path in self.list_event_files():
            if not file_path.exists():
                continue
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    event = ProjectEvent.model_validate(data)
                    if event.sequence >= from_sequence:
                        yield event

    def verify(self) -> LedgerVerificationResult:
        """Verify the full cryptographic hash chain and schema compliance across all event files."""
        errors: list[str] = []
        event_count = 0
        expected_sequence = 1
        expected_prev_hash = ""
        seen_event_ids: set[str] = set()
        last_event_hash = ""
        last_sequence = 0

        files = self.list_event_files()
        if not files:
            return LedgerVerificationResult(
                valid=True,
                event_count=0,
                last_sequence=0,
                last_event_hash="",
                errors=[],
            )

        for file_path in files:
            with open(file_path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    raw = line.strip()
                    if not raw:
                        continue

                    event_count += 1

                    # 1. JSON parsing
                    try:
                        data = json.loads(raw)
                    except Exception as exc:
                        errors.append(
                            f"{file_path.name}:{line_num}: Malformed JSON: {exc}"
                        )
                        continue

                    # 2. Schema validation
                    try:
                        event = ProjectEvent.model_validate(data)
                    except Exception as exc:
                        errors.append(
                            f"{file_path.name}:{line_num}: Schema validation error: {exc}"
                        )
                        continue

                    # 3. Project ID match
                    if event.project_id != self.project_id:
                        errors.append(
                            f"{file_path.name}:{line_num}: Project ID mismatch: expected '{self.project_id}', got '{event.project_id}'"
                        )

                    # 4. Duplicate event ID
                    if event.event_id in seen_event_ids:
                        errors.append(
                            f"{file_path.name}:{line_num}: Duplicate event_id '{event.event_id}'"
                        )
                    seen_event_ids.add(event.event_id)

                    # 5. Strict sequence monotonicity
                    if event.sequence != expected_sequence:
                        errors.append(
                            f"{file_path.name}:{line_num}: Broken sequence: expected {expected_sequence}, got {event.sequence}"
                        )

                    # 6. Prev event hash continuity
                    if event.prev_event_hash != expected_prev_hash:
                        errors.append(
                            f"{file_path.name}:{line_num}: Broken prev_event_hash: expected '{expected_prev_hash}', got '{event.prev_event_hash}'"
                        )

                    # 7. Payload digest verification
                    expected_payload_digest = compute_payload_digest(event.payload)
                    if event.payload_digest != expected_payload_digest:
                        errors.append(
                            f"{file_path.name}:{line_num}: Payload digest mismatch for {event.event_id}: expected '{expected_payload_digest}', got '{event.payload_digest}'"
                        )

                    # 8. Envelope hash verification
                    expected_event_hash = compute_event_hash(event.model_dump())
                    if event.event_hash != expected_event_hash:
                        errors.append(
                            f"{file_path.name}:{line_num}: Event hash mismatch for {event.event_id}: expected '{expected_event_hash}', got '{event.event_hash}'"
                        )

                    expected_sequence = event.sequence + 1
                    expected_prev_hash = event.event_hash
                    last_sequence = event.sequence
                    last_event_hash = event.event_hash

        valid = len(errors) == 0
        return LedgerVerificationResult(
            valid=valid,
            event_count=event_count,
            last_sequence=last_sequence,
            last_event_hash=last_event_hash,
            errors=errors,
        )

    def rotate(self, archive_name: str | None = None, timeout: float = 10.0) -> Path | None:
        """Rotate the active events.jsonl into an archive partition under Level 3 lock."""
        with project_lock(self.project_id, self.vault_root, timeout=timeout):
            if not self.active_events_file.exists() or self.active_events_file.stat().st_size == 0:
                return None

            if archive_name is None:
                existing_rotated = [
                    p for p in self.project_dir.iterdir()
                    if p.name.startswith("events_") and p.name.endswith(".jsonl")
                ]
                next_index = len(existing_rotated) + 1
                archive_name = f"events_{next_index:06d}.jsonl"

            archive_path = self.project_dir / archive_name
            if archive_path.exists():
                raise FileExistsError(f"Target archive file already exists: {archive_path}")

            os.rename(self.active_events_file, archive_path)
            # Create a new empty active ledger
            self.active_events_file.touch(mode=0o600)
            return archive_path


def verify_event_ledger(project_id: str, vault_root: Path) -> LedgerVerificationResult:
    """Convenience function to verify a project event ledger."""
    store = ProjectEventStore(project_id, vault_root)
    return store.verify()


def replay_events(
    project_id: str,
    vault_root: Path,
    from_sequence: int = 1,
) -> Iterator[ProjectEvent]:
    """Convenience generator to replay events from a project ledger."""
    store = ProjectEventStore(project_id, vault_root)
    yield from store.replay(from_sequence=from_sequence)
