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
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from power_framework.core.canonical_json import (
    canonical_json_dumps,
    compute_command_fingerprint,
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.lock_tracker import (
    LockHierarchyTracker,
)
from power_framework.core.project_models import (
    AppendCommand,
    IdempotencyConflictError,
    LedgerIntegrityError,
    LedgerVerificationResult,
    ProjectEvent,
    generate_deterministic_event_id,
    validate_project_id,
)

logger = logging.getLogger(__name__)


class LockAcquisitionTimeoutError(TimeoutError):
    """Raised when lock acquisition exceeds the configured timeout."""


ROTATION_FILE_PATTERN = re.compile(r"^events_[0-9]{6}\.jsonl$")

_project_thread_locks: dict[str, threading.RLock] = {}
_project_thread_locks_guard = threading.Lock()
_local_project_locks = threading.local()


def _get_project_thread_lock(project_dir: Path) -> threading.RLock:
    key = str(project_dir.resolve())
    with _project_thread_locks_guard:
        if key not in _project_thread_locks:
            _project_thread_locks[key] = threading.RLock()
        return _project_thread_locks[key]


def validate_vault_root(vault_root: Path) -> Path:
    """Validate that vault root exists, is not a symlink, and return resolved path."""
    raw_root = Path(vault_root).expanduser()
    if raw_root.is_symlink():
        raise ValueError(f"Vault root must not be a symlink: {vault_root}")
    resolved = raw_root.resolve()
    if resolved.is_symlink():
        raise ValueError(f"Vault root must not be a symlink: {vault_root}")
    return resolved


def get_projects_dir(vault_root: Path) -> Path:
    """Resolve and validate the root projects directory."""
    resolved_root = validate_vault_root(vault_root)

    power_dir = resolved_root / ".power"
    if power_dir.is_symlink():
        raise ValueError(f".power directory must not be a symlink: {power_dir}")
    power_dir.mkdir(parents=True, exist_ok=True)
    if power_dir.is_symlink():
        raise ValueError(f".power directory must not be a symlink: {power_dir}")

    projects_dir = power_dir / "projects"
    if projects_dir.is_symlink():
        raise ValueError(f"Projects directory must not be a symlink: {projects_dir}")
    projects_dir.mkdir(parents=True, exist_ok=True)
    if projects_dir.is_symlink():
        raise ValueError(f"Projects directory must not be a symlink: {projects_dir}")

    resolved_projects = projects_dir.resolve()
    try:
        resolved_projects.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Projects directory escapes vault boundary: {projects_dir}") from exc
    return resolved_projects


def get_project_dir(project_id: str, vault_root: Path) -> Path:
    """Validate project ID and safely resolve its directory, preventing traversal and symlink escapes."""
    validate_project_id(project_id)
    projects_dir = get_projects_dir(vault_root)
    project_dir = projects_dir / project_id
    if project_dir.is_symlink():
        raise ValueError(f"Project directory must not be a symlink: {project_dir}")

    project_dir.mkdir(parents=True, exist_ok=True)
    if project_dir.is_symlink():
        raise ValueError(f"Project directory must not be a symlink: {project_dir}")

    resolved = project_dir.resolve()
    try:
        resolved.relative_to(projects_dir)
    except ValueError as exc:
        raise ValueError(f"Project path escapes vault boundary: {project_id}") from exc

    return resolved


@contextlib.contextmanager
def project_lock(
    project_id: str,
    vault_root: Path,
    timeout: float = 10.0,
) -> Iterator[Path]:
    """Level 3 fine-grained project lock context manager (ADR-PSE-007)."""
    with LockHierarchyTracker.hold_level(LockHierarchyTracker.LEVEL_PROJECT, project_id=project_id):
        project_dir = get_project_dir(project_id, vault_root)

        if not hasattr(_local_project_locks, "held"):
            _local_project_locks.held = {}

        lock_key = (project_id, str(vault_root.resolve()))
        if _local_project_locks.held.get(lock_key, 0) > 0:
            _local_project_locks.held[lock_key] += 1
            try:
                yield project_dir
            finally:
                _local_project_locks.held[lock_key] -= 1
                if _local_project_locks.held[lock_key] == 0:
                    del _local_project_locks.held[lock_key]
            return

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
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(lock_file, flags, 0o600)
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
                _local_project_locks.held[lock_key] = 1
                try:
                    yield project_dir
                finally:
                    _local_project_locks.held.pop(lock_key, None)
            finally:
                with contextlib.suppress(OSError):
                    fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        finally:
            thread_lock.release()


def recover_torn_tail(file_path: Path) -> int:
    """Detect and truncate incomplete trailing bytes without newline at EOF.

    Torn tail definition:
    - If a file ends with bytes not terminated by '\\n', those trailing bytes represent
      an incomplete atomic append (e.g. abrupt crash or power loss during write) and
      are safely truncated back to the last valid '\\n'.
    - If a file ends with '\\n', every record line is complete. Any malformed JSON,
      schema invalidity, payload tampering, or broken hash chain is CORRUPTION,
      NOT a torn tail! Automatic truncation is strictly forbidden: the file remains
      untouched and LedgerIntegrityError is raised.

    Returns the number of bytes truncated (0 if no truncation was performed).
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        return 0

    if file_path.is_symlink():
        raise ValueError(f"Ledger file must not be a symlink: {file_path}")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(file_path, flags)
    with open(fd, "rb", closefd=True) as f:
        content = f.read()

    if not content:
        return 0

    # 1. Check if file ends with '\n' (complete records) or has an unterminated tail
    if not content.endswith(b"\n"):
        last_nl_idx = content.rfind(b"\n")
        valid_len = last_nl_idx + 1 if last_nl_idx >= 0 else 0
        truncated_bytes = len(content) - valid_len
        logger.warning(
            f"Truncating unterminated torn tail in {file_path}: discarded {truncated_bytes} bytes from EOF"
        )
        flags_out = os.O_WRONLY | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags_out |= os.O_NOFOLLOW
        fd_out = os.open(file_path, flags_out)
        with open(fd_out, "wb", closefd=True) as f_out:
            if valid_len > 0:
                f_out.write(content[:valid_len])
            f_out.flush()
            os.fsync(fd_out)
        return truncated_bytes

    # 2. File ends with '\n': records are complete. Check for corruption.
    lines = [ln for ln in content.splitlines(keepends=True) if ln.strip()]
    if not lines:
        return 0

    last_line = lines[-1].decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(last_line)
    except Exception as exc:
        raise LedgerIntegrityError(f"Corruption detected in complete record (malformed JSON): {exc}") from exc

    try:
        event = ProjectEvent.model_validate(data)
    except Exception as exc:
        raise LedgerIntegrityError(f"Corruption detected in complete record (schema violation): {exc}") from exc

    calc_payload_digest = compute_payload_digest(event.payload)
    if event.payload_digest != calc_payload_digest:
        raise LedgerIntegrityError(
            f"Corruption detected in complete record (payload digest mismatch): {event.payload_digest} != {calc_payload_digest}"
        )

    calc_event_hash = compute_event_hash(event.model_dump())
    if event.event_hash != calc_event_hash:
        raise LedgerIntegrityError(
            f"Corruption detected in complete record (event hash mismatch): {event.event_hash} != {calc_event_hash}"
        )

    if len(lines) > 1:
        prev_line = lines[-2].decode("utf-8", errors="replace").strip()
        try:
            prev_data = json.loads(prev_line)
            prev_event = ProjectEvent.model_validate(prev_data)
            if event.sequence != prev_event.sequence + 1:
                raise LedgerIntegrityError(
                    f"Corruption detected in complete record (broken sequence: {event.sequence} != {prev_event.sequence + 1})"
                )
            if event.prev_event_hash != prev_event.event_hash:
                raise LedgerIntegrityError(
                    "Corruption detected in complete record (broken prev_event_hash)"
                )
        except LedgerIntegrityError:
            raise
        except Exception as exc:
            raise LedgerIntegrityError(f"Corruption detected in preceding complete record: {exc}") from exc

    return 0



class ProjectEventStore:
    """Durable append-only event store for a single project."""

    def __init__(self, project_id: str, vault_root: Path) -> None:
        self.project_id = validate_project_id(project_id)
        self.vault_root = validate_vault_root(vault_root)
        self.project_dir = get_project_dir(self.project_id, vault_root)
        self.active_events_file = self.project_dir / "events.jsonl"

    def list_event_files(self) -> list[Path]:
        """Return all event files for this project in deterministic replay order."""
        if not self.project_dir.exists():
            return []

        rotated: list[Path] = []
        for p in self.project_dir.iterdir():
            if p.is_file() and ROTATION_FILE_PATTERN.match(p.name):
                if p.is_symlink():
                    raise ValueError(f"Rotated event file must not be a symlink: {p}")
                rotated.append(p)

        rotated.sort(key=lambda p: int(p.name[7:13]))
        result = list(rotated)
        if self.active_events_file.exists():
            if self.active_events_file.is_symlink():
                raise ValueError(f"Active event file must not be a symlink: {self.active_events_file}")
            result.append(self.active_events_file)
        return result

    @contextlib.contextmanager
    def lock(self, timeout: float = 10.0) -> Iterator[Path]:
        """Context manager for holding Level 3 project lock."""
        with project_lock(self.project_id, self.vault_root, timeout=timeout) as p:
            yield p

    def append(self, command: AppendCommand, timeout: float = 10.0) -> ProjectEvent:
        """Append an event under Level 3 project lock with atomic fsync and idempotency deduplication."""
        if command.project_id != self.project_id:
            raise ValueError(
                f"Command project_id '{command.project_id}' does not match store '{self.project_id}'"
            )

        with self.lock(timeout=timeout):
            # 1. Crash recovery on active file if present (truncates only unterminated tail)
            if self.active_events_file.exists():
                recover_torn_tail(self.active_events_file)

            # 2. Full ledger integrity verification before append
            verify_res = self.verify()
            if not verify_res.valid:
                raise LedgerIntegrityError(
                    f"Ledger integrity verification failed for project {self.project_id}: {'; '.join(verify_res.errors)}"
                )

            # 3. Idempotency resolution with command fingerprint conflict checking
            cmd_fingerprint = compute_command_fingerprint(
                actor=command.actor,
                event_type=command.event_type,
                payload=command.payload,
                artifact_refs=command.artifact_refs,
                evidence_refs=command.evidence_refs,
                source=command.source,
                session_id=command.session_id,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
            )

            for event in self.replay(from_sequence=1):
                if command.idempotency_key and event.idempotency_key == command.idempotency_key:
                    ev_fingerprint = compute_command_fingerprint(
                        actor=event.actor,
                        event_type=event.event_type,
                        payload=event.payload,
                        artifact_refs=event.artifact_refs,
                        evidence_refs=event.evidence_refs,
                        source=event.source,
                        session_id=event.session_id,
                        correlation_id=event.correlation_id,
                        causation_id=event.causation_id,
                    )
                    if cmd_fingerprint != ev_fingerprint:
                        raise IdempotencyConflictError(
                            f"Idempotency conflict for key '{command.idempotency_key}': command fingerprint mismatch"
                        )
                    logger.info(
                        f"Idempotent match for key {command.idempotency_key} on project {self.project_id}"
                    )
                    return event

                if command.event_id and event.event_id == command.event_id:
                    ev_fingerprint = compute_command_fingerprint(
                        actor=event.actor,
                        event_type=event.event_type,
                        payload=event.payload,
                        artifact_refs=event.artifact_refs,
                        evidence_refs=event.evidence_refs,
                        source=event.source,
                        session_id=event.session_id,
                        correlation_id=event.correlation_id,
                        causation_id=event.causation_id,
                    )
                    if cmd_fingerprint != ev_fingerprint:
                        raise IdempotencyConflictError(
                            f"Idempotency conflict for event_id '{command.event_id}': command fingerprint mismatch"
                        )
                    logger.info(
                        f"Idempotent match for event_id {command.event_id} on project {self.project_id}"
                    )
                    return event

            # 4. Monotonic sequence and hash from verified state
            new_sequence = verify_res.last_sequence + 1
            prev_event_hash = "" if new_sequence == 1 else verify_res.last_event_hash

            # 5. Build event
            timestamp = command.timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z")
            if command.event_id:
                event_id = command.event_id
            elif command.idempotency_key:
                event_id = generate_deterministic_event_id(self.project_id, command.idempotency_key)
            else:
                event_id = f"evt_{self.project_id}_{new_sequence}_{uuid.uuid4().hex[:12]}"
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

            # 6. Durable write with atomic fsync
            if self.active_events_file.is_symlink():
                raise ValueError(f"Active event file must not be a symlink: {self.active_events_file}")
            try:
                self.active_events_file.resolve().relative_to(self.project_dir.resolve())
            except ValueError as exc:
                raise ValueError(f"Active event file escapes project directory: {self.active_events_file}") from exc

            line = canonical_json_dumps(event.model_dump()) + "\n"
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(self.active_events_file, flags, 0o600)
            with open(fd, "a", encoding="utf-8", closefd=True) as f:
                f.write(line)
                f.flush()
                os.fsync(fd)

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
        with self.lock(timeout=timeout):
            if not self.active_events_file.exists() or self.active_events_file.stat().st_size == 0:
                return None

            if archive_name is not None:
                candidate_archive = self.project_dir / archive_name
                if candidate_archive.is_symlink():
                    raise ValueError(f"Archive path must not be a symlink: {candidate_archive}")

            existing_indices: list[int] = []
            for p in self.project_dir.iterdir():
                if ROTATION_FILE_PATTERN.match(p.name):
                    if p.is_symlink():
                        raise ValueError(f"Partition file must not be a symlink: {p}")
                    if p.is_file():
                        existing_indices.append(int(p.name[7:13]))

            sorted_indices = sorted(existing_indices)
            for expected_idx, actual_idx in enumerate(sorted_indices, start=1):
                if actual_idx != expected_idx:
                    raise ValueError(
                        f"Existing rotated partitions are gapped or non-sequential: found {actual_idx}, expected {expected_idx}"
                    )

            next_index = max(existing_indices, default=0) + 1
            expected_archive_name = f"events_{next_index:06d}.jsonl"

            if archive_name is None:
                archive_name = expected_archive_name
            else:
                if not ROTATION_FILE_PATTERN.match(archive_name):
                    raise ValueError(
                        f"Invalid archive_name '{archive_name}'. Only store-generated format 'events_XXXXXX.jsonl' is allowed."
                    )
                if archive_name != expected_archive_name:
                    raise ValueError(
                        f"Invalid archive_name '{archive_name}': partition index must be sequential without gaps. Expected '{expected_archive_name}'."
                    )

            archive_path = self.project_dir / archive_name
            if archive_path.is_symlink():
                raise ValueError(f"Archive path must not be a symlink: {archive_path}")

            try:
                if archive_path.resolve().is_symlink():
                    raise ValueError(f"Archive path must not be a symlink: {archive_path}")
                archive_path.resolve().relative_to(self.project_dir.resolve())
            except ValueError as exc:
                raise ValueError(f"Archive path escapes project directory: {archive_name}") from exc

            if archive_path.exists():
                raise FileExistsError(f"Target archive file already exists: {archive_path}")

            if self.active_events_file.is_symlink():
                raise ValueError(f"Active event file must not be a symlink: {self.active_events_file}")

            os.rename(self.active_events_file, archive_path)
            # Create a new empty active ledger with mode 0600
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(self.active_events_file, flags, 0o600)
            os.close(fd)
            return archive_path


def verify_event_ledger(project_id: str, vault_root: Path) -> LedgerVerificationResult:
    """Convenience function to verify a project event ledger."""
    store = ProjectEventStore(project_id, vault_root)
    return store.verify()


def verify_ledger_integrity(project_id: str, vault_root: Path) -> LedgerVerificationResult:
    """Convenience function to verify a project event ledger and raise on corruption."""
    store = ProjectEventStore(project_id, vault_root)
    res = store.verify()
    if not res.valid:
        raise LedgerIntegrityError(
            f"Ledger integrity verification failed for project {project_id}: {'; '.join(res.errors)}"
        )
    return res


def replay_events(
    project_id: str,
    vault_root: Path,
    from_sequence: int = 1,
) -> Iterator[ProjectEvent]:
    """Convenience generator to replay events from a project ledger."""
    store = ProjectEventStore(project_id, vault_root)
    yield from store.replay(from_sequence=from_sequence)

