"""POWER Project State Engine (PSE) Ingestion Boundary & Privacy Perimeter.

Implements:
- Single authoritative Ingestion API:
    - append_project_event(...)
    - import_project_events(...)
    - verify_project_ledger(...)
    - replay_project(...)
- Privacy Modes: metadata-only, structured-events, full-content
- Defense-in-depth deterministic credential and secret redaction
- Local raw-evidence management with configurable TTL (default 14 days)
- Disposable derived SQLite index projection and full reconstruction
- Materialized human-facing Markdown status projection
- Cross-subsystem association sagas (Task/Decision) and reconciliation
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from power_framework.core.canonical_json import (
    canonical_json_dumps,
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.project_models import (
    SAGA_PAYLOAD_MODELS,
    AppendCommand,
    IdempotencyConflictError,
    LedgerIntegrityError,
    LedgerVerificationResult,
    PrivacyMode,
    ProjectEvent,
    RedactionRecord,
    generate_deterministic_event_id,
    validate_event_id,
    validate_project_id,
)
from power_framework.core.project_store import (
    ProjectEventStore,
    get_project_dir,
    get_projects_dir,
    recover_torn_tail,
    replay_events,
    validate_vault_root,
    verify_event_ledger,
)

logger = logging.getLogger(__name__)

RAW_DIALOGUE_KEYS: frozenset[str] = frozenset(
    {
        "raw_dialogue",
        "dialogue_buffer",
        "transcript",
        "turns",
        "prompt_text",
        "completion_text",
        "messages",
        "reasoning",
        "thinking",
    }
)


def strip_raw_dialogue(data: Any) -> tuple[Any, dict[str, Any]]:
    """Recursively strip raw dialogue and transcript keys from data structures.

    Returns:
        tuple[cleaned_data, extracted_dialogue]
    """
    extracted: dict[str, Any] = {}

    def _traverse(item: Any, path: str = "") -> Any:
        if isinstance(item, dict):
            clean_dict: dict[str, Any] = {}
            for k, v in item.items():
                if k in RAW_DIALOGUE_KEYS:
                    key_path = f"{path}.{k}" if path else k
                    extracted[key_path] = v
                else:
                    sub_path = f"{path}.{k}" if path else k
                    clean_dict[k] = _traverse(v, sub_path)
            return clean_dict
        if isinstance(item, list):
            return [_traverse(elem, f"{path}[{i}]") for i, elem in enumerate(item)]
        if isinstance(item, tuple):
            return tuple(_traverse(elem, f"{path}[{i}]") for i, elem in enumerate(item))
        return item

    cleaned = _traverse(data)
    return cleaned, extracted


def contains_raw_dialogue(data: Any) -> bool:
    """Check whether data contains any raw dialogue / LLM transcript keys."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k in RAW_DIALOGUE_KEYS:
                return True
            if contains_raw_dialogue(v):
                return True
    elif isinstance(data, (list, tuple)):
        for elem in data:
            if contains_raw_dialogue(elem):
                return True
    return False


# ---------------------------------------------------------------------------
# Secret Redaction Pipeline (Defense-in-Depth)
# ---------------------------------------------------------------------------

REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        "bearer_token",
        re.compile(r"(?i)\bBearer\s+([A-Za-z0-9_\-\.+=/]{12,})"),
        "Bearer [REDACTED_TOKEN]",
    ),
    (
        "github_token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{16,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    (
        "env_secret",
        re.compile(
            r"(?im)^(?P<key>AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|PASSWORD|SECRET_KEY|DATABASE_URL|API_KEY|PRIVATE_KEY)\s*=\s*(?P<val>['\"]?[^\r\n'\"]+['\"]?)"
        ),
        r"\g<key>=[REDACTED]",
    ),
    (
        "credential_pair",
        re.compile(
            r"(?i)(?P<prefix>api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)[\"']?\s*[:=]\s*[\"']?(?P<secret>[A-Za-z0-9_\-\.+=]{8,})[\"']?"
        ),
        r"\g<prefix>:[REDACTED]",
    ),
]


SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)^(?:.*_)?(?:api[_-]?key|secret|token|password|auth|private[_-]?key)(?:_.*)?$"
)


def redact_secrets(data: Any) -> tuple[Any, RedactionRecord]:
    """Recursively scrub known credentials and secrets from data structures.

    Returns the sanitized structure and a RedactionRecord with detected classes
    and replacement counts, without recording any secret values.
    """
    replacements = 0
    detected_classes: set[str] = set()

    def _scrub_str(text: str) -> str:
        nonlocal replacements
        scrubbed = text
        for secret_cls, pattern, repl in REDACTION_PATTERNS:
            new_text, count = pattern.subn(repl, scrubbed)
            if count > 0:
                replacements += count
                detected_classes.add(secret_cls)
                scrubbed = new_text
        return scrubbed

    def _traverse(item: Any) -> Any:
        nonlocal replacements
        if isinstance(item, str):
            return _scrub_str(item)
        if isinstance(item, dict):
            res: dict[str, Any] = {}
            for k, v in item.items():
                if isinstance(v, str):
                    scrubbed_v = _scrub_str(v)
                    if isinstance(k, str) and SENSITIVE_KEY_PATTERN.match(k) and scrubbed_v == v:
                        replacements += 1
                        detected_classes.add("credential_pair")
                        res[k] = "[REDACTED]"
                    else:
                        res[k] = scrubbed_v
                elif (
                    isinstance(k, str)
                    and SENSITIVE_KEY_PATTERN.match(k)
                    and isinstance(v, (int, float, bool))
                ):
                    replacements += 1
                    detected_classes.add("credential_pair")
                    res[k] = "[REDACTED]"
                else:
                    res[k] = _traverse(v)
            return res
        if isinstance(item, list):
            return [_traverse(elem) for elem in item]
        if isinstance(item, tuple):
            return tuple(_traverse(elem) for elem in item)
        return item

    cleaned = _traverse(data)
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    record = RedactionRecord(
        replacements_count=replacements,
        detected_secret_classes=sorted(detected_classes),
        timestamp=timestamp,
    )
    return cleaned, record


# ---------------------------------------------------------------------------
# Raw Evidence Management (Privacy Mode: full-content)
# ---------------------------------------------------------------------------


def _get_raw_evidence_dir(vault_root: Path, project_id: str) -> Path:
    validate_project_id(project_id)
    resolved_root = validate_vault_root(vault_root)

    power_dir = resolved_root / ".power"
    if power_dir.is_symlink():
        raise ValueError(f".power directory must not be a symlink: {power_dir}")
    power_dir.mkdir(parents=True, exist_ok=True)
    if power_dir.is_symlink():
        raise ValueError(f".power directory must not be a symlink: {power_dir}")

    raw_ev_base = power_dir / "raw-evidence"
    if raw_ev_base.is_symlink():
        raise ValueError(f"raw-evidence directory must not be a symlink: {raw_ev_base}")
    raw_ev_base.mkdir(parents=True, exist_ok=True)
    if raw_ev_base.is_symlink():
        raise ValueError(f"raw-evidence directory must not be a symlink: {raw_ev_base}")

    evidence_dir = raw_ev_base / project_id
    if evidence_dir.is_symlink():
        raise ValueError(f"Project raw evidence directory must not be a symlink: {evidence_dir}")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if evidence_dir.is_symlink():
        raise ValueError(f"Project raw evidence directory must not be a symlink: {evidence_dir}")

    resolved = evidence_dir.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Evidence directory escapes vault boundary: {evidence_dir}") from exc

    with contextlib.suppress(OSError):
        resolved.chmod(0o700)
    return resolved


def prune_raw_evidence(vault_root: Path, project_id: str, ttl_days: int = 14) -> int:
    """Prune local raw evidence files older than configured TTL days (0 = disabled)."""
    if ttl_days <= 0:
        return 0

    evidence_dir = _get_raw_evidence_dir(vault_root, project_id)
    cutoff = time.time() - (ttl_days * 86400)
    pruned = 0

    for path in evidence_dir.iterdir():
        if path.is_file() and path.suffix == ".json":
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    pruned += 1
            except OSError:
                pass

    return pruned


def store_raw_evidence(
    vault_root: Path,
    project_id: str,
    event_id: str,
    raw_content: Any,
    ttl_days: int = 14,
) -> str:
    """Store local-only raw conversation / evidence under mode 0600 and return its SHA-256 digest."""
    evidence_dir = _get_raw_evidence_dir(vault_root, project_id)
    evidence_file = evidence_dir / f"{event_id}.json"
    if evidence_file.is_symlink():
        raise ValueError(f"Evidence file must not be a symlink: {evidence_file}")

    try:
        if evidence_file.resolve().is_symlink():
            raise ValueError(f"Evidence file must not be a symlink: {evidence_file}")
        evidence_file.resolve().relative_to(evidence_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Evidence file escapes evidence directory: {evidence_file}") from exc

    # Redact before storing even in full-content mode for baseline hygiene
    scrubbed_content, _ = redact_secrets(raw_content)
    raw_bytes = canonical_json_dumps(scrubbed_content).encode("utf-8")
    digest = compute_payload_digest(scrubbed_content)

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(evidence_file, flags, 0o600)
    except FileExistsError as err:
        # Protect against overwrite on retry
        with open(evidence_file, "rb") as f_existing:
            existing_bytes = f_existing.read()
        if existing_bytes != raw_bytes:
            raise IdempotencyConflictError(
                f"Evidence file '{evidence_file.name}' already exists with different content"
            ) from err
        return f"sha256:{digest}"

    try:
        os.fchmod(fd, 0o600)
        with open(fd, "wb", closefd=True) as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(fd)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise

    # Periodic pruning
    prune_raw_evidence(vault_root, project_id, ttl_days=ttl_days)

    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# High-Level Ingestion API
# ---------------------------------------------------------------------------


def append_project_event(
    vault_root: Path,
    command: AppendCommand,
    privacy_mode: PrivacyMode = PrivacyMode.STRUCTURED_EVENTS,
    raw_content: Any | None = None,
    raw_evidence_ttl_days: int = 14,
    timeout: float = 10.0,
) -> ProjectEvent:
    """Authoritative API to append an event to the project ledger.

    Enforces:
    - Privacy boundary filtering (metadata-only, structured-events, full-content)
    - Secret redaction
    - Dialogue / transcript elimination from event payload across all privacy modes
    - Local raw-evidence storage under full-content mode
    - Mandatory saga payload contract validation
    - Level 3 project locking and atomic append
    """
    store = ProjectEventStore(command.project_id, vault_root)

    # 1. Apply Redaction Pipeline
    sanitized_payload, _redaction_record = redact_secrets(command.payload)

    # 2. Recursively extract and strip raw dialogue keys across ALL privacy modes
    cleaned_payload, extracted_dialogue = strip_raw_dialogue(sanitized_payload)

    # 3. Apply Privacy Mode Boundaries
    final_payload: dict[str, Any]
    is_saga_event = command.event_type in SAGA_PAYLOAD_MODELS

    if privacy_mode == PrivacyMode.METADATA_ONLY:
        if is_saga_event:
            # Saga events contain purely structural identifiers (task_id, decision_id, relation,
            # correlation_id, idempotency_key), preserve structural fields to prevent contract breakage
            final_payload = cleaned_payload
        else:
            final_payload = {
                "_privacy_mode": PrivacyMode.METADATA_ONLY.value,
                "keys": sorted(cleaned_payload.keys()),
                "event_type": command.event_type,
            }
    elif privacy_mode == PrivacyMode.STRUCTURED_EVENTS or privacy_mode == PrivacyMode.FULL_CONTENT:
        final_payload = cleaned_payload

    # 4. Mandatory saga payload contract validation & normalization BEFORE creating any external evidence
    model_cls = SAGA_PAYLOAD_MODELS.get(command.event_type)
    if model_cls is not None:
        if not isinstance(final_payload, dict) or not final_payload:
            raise ValueError(
                f"Payload for saga event '{command.event_type}' must be a non-empty dictionary conforming to {model_cls.__name__}"
            )
        payload_data = dict(final_payload)
        if "project_id" not in payload_data:
            payload_data["project_id"] = command.project_id
        if "correlation_id" not in payload_data and command.correlation_id:
            payload_data["correlation_id"] = command.correlation_id
        if "idempotency_key" not in payload_data and command.idempotency_key:
            payload_data["idempotency_key"] = command.idempotency_key
        validated_saga = model_cls.model_validate(payload_data)
        final_payload = validated_saga.model_dump()

    # 5. Deterministic, regex-safe event_id generation
    target_event_id = command.event_id
    if not target_event_id:
        if command.idempotency_key:
            target_event_id = generate_deterministic_event_id(
                command.project_id, command.idempotency_key
            )
        else:
            target_event_id = f"evt_{command.project_id}_{uuid.uuid4().hex[:12]}"
    validate_event_id(target_event_id)

    # 6. Pre-validate prepared command contract before creating raw evidence file (zero orphan files)
    evidence_refs = list(command.evidence_refs)
    test_command = command.model_copy(
        update={
            "event_id": target_event_id,
            "payload": final_payload,
            "evidence_refs": evidence_refs,
        }
    )
    AppendCommand.model_validate(test_command.model_dump())

    # 7. Store raw evidence ONLY after all command and payload validations have succeeded
    if privacy_mode == PrivacyMode.FULL_CONTENT:
        content_to_store = (
            raw_content
            if raw_content is not None
            else (extracted_dialogue if extracted_dialogue else None)
        )
        if content_to_store is not None:
            evidence_ref = store_raw_evidence(
                vault_root=vault_root,
                project_id=command.project_id,
                event_id=target_event_id,
                raw_content=content_to_store,
                ttl_days=raw_evidence_ttl_days,
            )
            if evidence_ref not in evidence_refs:
                evidence_refs.append(evidence_ref)

    prepared_command = command.model_copy(
        update={
            "event_id": target_event_id,
            "payload": final_payload,
            "evidence_refs": evidence_refs,
        }
    )

    event = store.append(prepared_command, timeout=timeout)

    # Proactively update derived projection for this event
    with contextlib.suppress(Exception):
        update_derived_index_for_event(vault_root, event)

    return event


def import_project_events(
    vault_root: Path,
    project_id: str,
    events: list[ProjectEvent | dict[str, Any]],
    timeout: float = 10.0,
) -> int:
    """Import an existing valid chain of events into the project ledger.

    Atomicity Contract:
    Provides complete batch pre-validation with zero canonical ledger mutation on
    validation/contract failure, followed by ordered durable append and fsync;
    torn-tail recovery protects interrupted physical writes.
    Note: does not claim physical crash-atomic multi-record transaction.
    """
    validate_project_id(project_id)
    store = ProjectEventStore(project_id, vault_root)

    if not events:
        return 0

    with store.lock(timeout=timeout):
        # 1. Recover torn tail on existing active ledger if present
        if store.active_events_file.exists():
            recover_torn_tail(store.active_events_file)

        # 2. Fail-closed verification of existing ledger before writing ANY byte
        verify_res = store.verify()
        if not verify_res.valid:
            raise LedgerIntegrityError(
                f"Ledger integrity verification failed before import for project '{project_id}': {'; '.join(verify_res.errors)}"
            )

        existing_events = list(store.replay(from_sequence=1))
        seen_event_ids: set[str] = {ev.event_id for ev in existing_events}
        last_seq = existing_events[-1].sequence if existing_events else 0
        last_hash = existing_events[-1].event_hash if existing_events else ""

        # 3. Pre-validate entire batch in memory before opening file or writing any byte
        parsed_events: list[ProjectEvent] = []
        for raw in events:
            raw_dict = raw if isinstance(raw, dict) else raw.model_dump()
            if contains_raw_dialogue(raw_dict):
                raise ValueError(
                    "Import rejected: event payload contains prohibited raw dialogue / LLM transcript data"
                )

            ev = raw if isinstance(raw, ProjectEvent) else ProjectEvent.model_validate(raw)

            # Validate saga payload schema
            model_cls = SAGA_PAYLOAD_MODELS.get(ev.event_type)
            if model_cls is not None:
                if not isinstance(ev.payload, dict) or not ev.payload:
                    raise ValueError(
                        f"Payload for saga event '{ev.event_type}' must be a non-empty dictionary conforming to {model_cls.__name__}"
                    )
                model_cls.model_validate(ev.payload)

            parsed_events.append(ev)

        # Ensure events are ordered by sequence
        parsed_events.sort(key=lambda e: e.sequence)

        lines_to_write: list[str] = []
        curr_seq = last_seq
        curr_hash = last_hash

        for ev in parsed_events:
            if ev.project_id != project_id:
                raise ValueError(
                    f"Import project_id mismatch: expected '{project_id}', got '{ev.project_id}'"
                )

            if ev.event_id in seen_event_ids:
                raise ValueError(f"Duplicate event_id in import: '{ev.event_id}'")
            seen_event_ids.add(ev.event_id)

            # Check sequence linkage
            if ev.sequence != curr_seq + 1:
                raise ValueError(f"Import sequence gap: expected {curr_seq + 1}, got {ev.sequence}")
            if curr_seq == 0 and ev.prev_event_hash != "":
                raise ValueError("Genesis event must have empty prev_event_hash")
            if curr_seq > 0 and ev.prev_event_hash != curr_hash:
                raise ValueError(
                    f"Import hash gap: expected '{curr_hash}', got '{ev.prev_event_hash}'"
                )

            # Always verify integrity of the imported event
            calc_payload_digest = compute_payload_digest(ev.payload)
            if ev.payload_digest != calc_payload_digest:
                raise ValueError(f"Payload digest mismatch in imported event {ev.event_id}")
            calc_event_hash = compute_event_hash(ev.model_dump())
            if ev.event_hash != calc_event_hash:
                raise ValueError(f"Event hash mismatch in imported event {ev.event_id}")

            lines_to_write.append(canonical_json_dumps(ev.model_dump()) + "\n")
            curr_seq = ev.sequence
            curr_hash = ev.event_hash

        # 4. Ordered durable batch append with fsync
        if store.active_events_file.is_symlink():
            raise ValueError(f"Active event file must not be a symlink: {store.active_events_file}")
        try:
            store.active_events_file.resolve().relative_to(store.project_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Active event file escapes project directory: {store.active_events_file}"
            ) from exc

        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(store.active_events_file, flags, 0o600)
        with open(fd, "a", encoding="utf-8", closefd=True) as f:
            for line in lines_to_write:
                f.write(line)
            f.flush()
            os.fsync(fd)

    return len(lines_to_write)


def verify_project_ledger(vault_root: Path, project_id: str) -> LedgerVerificationResult:
    """Verify cryptographic integrity, schema adherence, and sequence continuity."""
    return verify_event_ledger(project_id, vault_root)


def replay_project(
    vault_root: Path,
    project_id: str,
    from_sequence: int = 1,
) -> Iterator[ProjectEvent]:
    """Replay project events in deterministic sequence."""
    yield from replay_events(project_id, vault_root, from_sequence=from_sequence)


# ---------------------------------------------------------------------------
# Derived Index Projection (SQLite + Markdown Status)
# ---------------------------------------------------------------------------


def _get_sqlite_path(vault_root: Path) -> Path:
    """Resolve and validate secondary SQLite database path.

    Boundary & Symlink Defense:
    Canonical event ledgers and raw evidence files strictly enforce race-free O_NOFOLLOW
    atomic opens and boundary verification. Secondary SQLite index projections are
    disposable derived caches and are protected by path resolution and symlink checks
    without kernel-level O_NOFOLLOW TOCTOU guarantees at the SQLite core layer.
    """
    resolved_root = validate_vault_root(vault_root)

    power_dir = resolved_root / ".power"
    if power_dir.is_symlink():
        raise ValueError(f".power directory must not be a symlink: {power_dir}")
    power_dir.mkdir(parents=True, exist_ok=True)
    if power_dir.is_symlink():
        raise ValueError(f".power directory must not be a symlink: {power_dir}")

    state_dir = power_dir / "project-state"
    if state_dir.is_symlink():
        raise ValueError(f"project-state directory must not be a symlink: {state_dir}")
    state_dir.mkdir(parents=True, exist_ok=True)
    if state_dir.is_symlink():
        raise ValueError(f"project-state directory must not be a symlink: {state_dir}")

    indexes_dir = state_dir / "indexes"
    if indexes_dir.is_symlink():
        raise ValueError(f"indexes directory must not be a symlink: {indexes_dir}")
    indexes_dir.mkdir(parents=True, exist_ok=True)
    if indexes_dir.is_symlink():
        raise ValueError(f"indexes directory must not be a symlink: {indexes_dir}")

    db_path = indexes_dir / "project_state.sqlite3"
    if db_path.is_symlink():
        raise ValueError(f"Database file must not be a symlink: {db_path}")

    resolved_db = db_path.resolve()
    if resolved_db.is_symlink():
        raise ValueError(f"Database file must not be a symlink: {db_path}")
    try:
        resolved_db.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Database path escapes vault boundary: {db_path}") from exc

    return resolved_db


def init_derived_database(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite tables for secondary projections."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                current_phase TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                last_sequence INTEGER,
                last_event_hash TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                prev_event_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                correlation_id TEXT,
                idempotency_key TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_phases (
                project_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                entered_at TEXT NOT NULL,
                PRIMARY KEY (project_id, phase)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raid_items (
                item_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                severity_impact TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raci_assignments (
                project_id TEXT NOT NULL,
                role TEXT NOT NULL,
                actor TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                PRIMARY KEY (project_id, role, actor)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gate_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                gate_type TEXT NOT NULL,
                phase TEXT NOT NULL,
                passed INTEGER NOT NULL,
                evaluated_at TEXT NOT NULL,
                details_json TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_associations (
                project_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                status TEXT NOT NULL,
                correlation_id TEXT,
                idempotency_key TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, task_id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_associations (
                project_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                status TEXT NOT NULL,
                correlation_id TEXT,
                idempotency_key TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, decision_id)
            );
        """)
    return conn


def update_derived_index_for_event(vault_root: Path, event: ProjectEvent) -> None:
    """Project a single event into the secondary SQLite database."""
    db_path = _get_sqlite_path(vault_root)
    conn = init_derived_database(db_path)
    try:
        with conn:
            # 1. Insert into events
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    event_id, project_id, sequence, timestamp, actor, source,
                    event_type, payload_json, payload_digest, prev_event_hash,
                    event_hash, correlation_id, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.project_id,
                    event.sequence,
                    event.timestamp,
                    event.actor,
                    event.source,
                    event.event_type,
                    canonical_json_dumps(event.payload),
                    event.payload_digest,
                    event.prev_event_hash,
                    event.event_hash,
                    event.correlation_id,
                    event.idempotency_key,
                ),
            )

            # 2. Update projects table
            cur = conn.execute(
                "SELECT project_id, name, description, current_phase, status, created_at FROM projects WHERE project_id = ?",
                (event.project_id,),
            )
            row = cur.fetchone()

            name = event.payload.get("name", row[1] if row else event.project_id)
            desc = event.payload.get("description", row[2] if row else "")
            phase = row[3] if row else "phase_0_charter"
            status = row[4] if row else "active"
            created_at = row[5] if row else event.timestamp

            if event.event_type == "project.phase.changed":
                phase = event.payload.get("new_phase", phase)
            elif event.event_type == "project.archived":
                status = "archived"
            elif event.event_type == "project.reopened":
                status = "active"

            conn.execute(
                """
                INSERT OR REPLACE INTO projects (
                    project_id, name, description, current_phase, status,
                    created_at, updated_at, last_sequence, last_event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.project_id,
                    name,
                    desc,
                    phase,
                    status,
                    created_at,
                    event.timestamp,
                    event.sequence,
                    event.event_hash,
                ),
            )

            # 3. Handle specific domain projections
            if event.event_type in (
                "task.associated",
                "task.association.failed",
                "task.association.requested",
            ):
                task_id = event.payload.get("task_id", "")
                relation = event.payload.get("relation", "contributes_to")
                status = (
                    "associated"
                    if event.event_type == "task.associated"
                    else (
                        "failed" if event.event_type == "task.association.failed" else "requested"
                    )
                )
                if task_id:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO task_associations (
                            project_id, task_id, relation, status, correlation_id, idempotency_key, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.project_id,
                            task_id,
                            relation,
                            status,
                            event.correlation_id,
                            event.idempotency_key,
                            event.timestamp,
                        ),
                    )

            if event.event_type in (
                "decision.associated",
                "decision.association.failed",
                "decision.association.requested",
            ):
                decision_id = event.payload.get("decision_id", "")
                relation = event.payload.get("relation", "governs")
                status = (
                    "associated"
                    if event.event_type == "decision.associated"
                    else (
                        "failed"
                        if event.event_type == "decision.association.failed"
                        else "requested"
                    )
                )
                if decision_id:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO decision_associations (
                            project_id, decision_id, relation, status, correlation_id, idempotency_key, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.project_id,
                            decision_id,
                            relation,
                            status,
                            event.correlation_id,
                            event.idempotency_key,
                            event.timestamp,
                        ),
                    )

            if event.event_type == "raci.assigned":
                role = event.payload.get("role", "")
                actor = event.payload.get("actor", "")
                if role and actor:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO raci_assignments (project_id, role, actor, assigned_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (event.project_id, role, actor, event.timestamp),
                    )

            if event.event_type in ("dor.evaluated", "dod.evaluated"):
                gate_type = "dor" if event.event_type == "dor.evaluated" else "dod"
                phase_val = event.payload.get("phase", phase)
                passed_val = 1 if event.payload.get("passed", False) else 0
                conn.execute(
                    """
                    INSERT INTO gate_evaluations (project_id, gate_type, phase, passed, evaluated_at, details_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.project_id,
                        gate_type,
                        phase_val,
                        passed_val,
                        event.timestamp,
                        canonical_json_dumps(event.payload),
                    ),
                )
    finally:
        conn.close()


def rebuild_derived_index(vault_root: Path, project_id: str | None = None) -> int:
    """100% deterministic reconstruction of the secondary SQLite database and status markdown.

    If project_id is None, rebuilds all projects found in .power/projects.
    Fails closed if any project ledger is corrupted or invalid.
    """
    root = validate_vault_root(vault_root)
    db_path = _get_sqlite_path(root)

    project_ids: list[str] = []
    if project_id:
        validate_project_id(project_id)
        project_ids = [project_id]
    else:
        projects_dir = get_projects_dir(root)
        for p in projects_dir.iterdir():
            if p.is_dir() and not p.is_symlink() and p.name.startswith("prj_"):
                project_ids.append(p.name)

    # Fail-closed verification before modifying or rebuilding anything
    for pid in project_ids:
        verify_res = verify_project_ledger(root, pid)
        if not verify_res.valid:
            raise LedgerIntegrityError(
                f"Cannot rebuild derived index for project {pid}: ledger verification failed with errors: {'; '.join(verify_res.errors)}"
            )

    conn = init_derived_database(db_path)
    total_rebuilt_events = 0
    try:
        with conn:
            for pid in project_ids:
                # Clear existing project records from index
                conn.execute("DELETE FROM events WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM projects WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM project_phases WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM raid_items WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM raci_assignments WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM gate_evaluations WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM task_associations WHERE project_id = ?", (pid,))
                conn.execute("DELETE FROM decision_associations WHERE project_id = ?", (pid,))

        conn.close()

        for pid in project_ids:
            store = ProjectEventStore(pid, root)
            last_event: ProjectEvent | None = None
            for event in store.replay(from_sequence=1):
                update_derived_index_for_event(root, event)
                last_event = event
                total_rebuilt_events += 1

            if last_event:
                materialize_status_markdown(root, pid, last_event)

    except Exception:
        if not conn.in_transaction:
            with contextlib.suppress(Exception):
                conn.close()
        raise

    return total_rebuilt_events


def materialize_status_markdown(
    vault_root: Path,
    project_id: str,
    last_event: ProjectEvent,
) -> Path:
    """Materialize human-facing Markdown status summary under project directory or vault path."""
    project_dir = get_project_dir(project_id, vault_root)
    status_file = project_dir / "status.md"
    if status_file.is_symlink():
        raise ValueError(f"Status file must not be a symlink: {status_file}")

    try:
        if status_file.resolve().is_symlink():
            raise ValueError(f"Status file must not be a symlink: {status_file}")
        status_file.resolve().relative_to(project_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Status file escapes project directory: {status_file}") from exc

    content = f"""<!-- GENERATED BY POWER PSE - DO NOT EDIT MANUALLY -->
# Diagnostic Ledger Summary: {project_id}

> [!NOTE]
> This is a low-level Phase 2 Diagnostic Ledger Summary. Semantic state projection and lifecycle phase evaluation are deferred to Phase 4 (State Engine).

- **Last Event Type:** {last_event.event_type}
- **Last Sequence:** {last_event.sequence}
- **Last Event Hash:** `{last_event.event_hash}`
- **Last Updated:** {last_event.timestamp}
- **Last Actor:** {last_event.actor}
"""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(status_file, flags, 0o600)
    with open(fd, "w", encoding="utf-8", closefd=True) as f:
        f.write(content)
        f.flush()
        os.fsync(fd)

    return status_file


# ---------------------------------------------------------------------------
# Cross-Subsystem Association Saga & Reconciliation (ADR-PSE-008)
# ---------------------------------------------------------------------------

_reconciliation_attempts: dict[Any, int] = {}
_reconciliation_attempts_guard = threading.Lock()


def _get_reconcile_attempt(
    tracker: dict[Any, int],
    key: tuple[str, str, str, str],
    base_attempt: int,
) -> int:
    if key in tracker:
        return tracker[key]
    str_key = f"{key[0]}:{key[1]}:{key[2]}:{key[3]}"
    if str_key in tracker:
        return tracker[str_key]
    corr_id = key[3]
    if corr_id in tracker:
        return tracker[corr_id]
    return base_attempt


def _set_reconcile_attempt(
    tracker: dict[Any, int],
    key: tuple[str, str, str, str],
    attempt: int,
) -> None:
    tracker[key] = attempt
    str_key = f"{key[0]}:{key[1]}:{key[2]}:{key[3]}"
    tracker[str_key] = attempt


def _pop_reconcile_attempt(
    tracker: dict[Any, int],
    key: tuple[str, str, str, str],
) -> None:
    tracker.pop(key, None)
    str_key = f"{key[0]}:{key[1]}:{key[2]}:{key[3]}"
    tracker.pop(str_key, None)
    tracker.pop(key[3], None)


def reconcile_project_subsystems(
    vault_root: Path,
    project_id: str,
    task_service: Any = None,
    decision_service: Any = None,
    max_attempts: int = 3,
    attempt_tracker: dict[str, int] | dict[Any, int] | None = None,
) -> dict[str, Any]:
    """Idempotently reconcile pending association sagas against TaskStore and DecisionService.

    Applies retry policy before marking an association as failed:
    - attempt < max_attempts (default 3): saga remains pending, no failed event appended.
    - entity exists: records .associated event and clears pending attempt.
    - attempt >= max_attempts: records .association.failed event and clears pending attempt.
    """
    validate_project_id(project_id)
    store = ProjectEventStore(project_id, vault_root)

    requested_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    pending_task_sagas: dict[tuple[str, str, str, str], tuple[str, dict[str, Any]]] = {}
    pending_decision_sagas: dict[tuple[str, str, str, str], tuple[str, dict[str, Any]]] = {}

    for event in store.replay(from_sequence=1):
        corr_id = (
            event.correlation_id
            or (event.payload.get("correlation_id") if isinstance(event.payload, dict) else None)
            or event.idempotency_key
            or event.event_id
        )

        # Track task sagas
        if event.event_type == "task.association.requested":
            task_id = event.payload.get("task_id", "") if isinstance(event.payload, dict) else ""
            key = (project_id, "task", task_id, corr_id)
            requested_counts[key] += 1
            pending_task_sagas[key] = (corr_id, event.payload)
        elif event.event_type in ("task.associated", "task.association.failed"):
            task_id = event.payload.get("task_id", "") if isinstance(event.payload, dict) else ""
            key = (project_id, "task", task_id, corr_id)
            pending_task_sagas.pop(key, None)

        # Track decision sagas
        if event.event_type == "decision.association.requested":
            decision_id = (
                event.payload.get("decision_id", "") if isinstance(event.payload, dict) else ""
            )
            key = (project_id, "decision", decision_id, corr_id)
            requested_counts[key] += 1
            pending_decision_sagas[key] = (corr_id, event.payload)
        elif event.event_type in ("decision.associated", "decision.association.failed"):
            decision_id = (
                event.payload.get("decision_id", "") if isinstance(event.payload, dict) else ""
            )
            key = (project_id, "decision", decision_id, corr_id)
            pending_decision_sagas.pop(key, None)

    reconciled_tasks = 0
    failed_tasks = 0
    pending_tasks = 0
    reconciled_decisions = 0
    failed_decisions = 0
    pending_decisions = 0

    tracker: dict[Any, int] = (
        attempt_tracker if attempt_tracker is not None else _reconciliation_attempts
    )

    with _reconciliation_attempts_guard:
        # Resolve pending tasks
        for key, (corr_id, payload) in list(pending_task_sagas.items()):
            task_id = payload.get("task_id", "")
            relation = payload.get("relation", "contributes_to")
            limit = min(payload.get("max_attempts", max_attempts), max_attempts)
            history_attempts = requested_counts.get(key, 0)
            past_attempts = max(history_attempts, payload.get("attempt", 1))

            task_exists = False
            if task_service is not None:
                try:
                    task_exists = task_service.get_task(task_id) is not None
                except Exception:
                    task_exists = False

            if task_exists:
                idempotency_key = f"rec_task_{task_id}_{corr_id}"
                if len(idempotency_key) > 128:
                    idempotency_key = f"rec_task_{hashlib.sha256(f'{task_id}:{corr_id}'.encode()).hexdigest()[:32]}"
                cmd = AppendCommand(
                    project_id=project_id,
                    event_type="task.associated",
                    payload={
                        "project_id": project_id,
                        "task_id": task_id,
                        "relation": relation,
                        "correlation_id": corr_id,
                        "idempotency_key": idempotency_key,
                    },
                    actor="system:reconciler",
                    source="reconciliation",
                    correlation_id=corr_id,
                    idempotency_key=idempotency_key,
                )
                store.append(cmd)
                reconciled_tasks += 1
                _pop_reconcile_attempt(tracker, key)
            else:
                if past_attempts < limit:
                    next_attempt = past_attempts + 1
                    retry_idem = f"reconcile:{corr_id}:attempt:{next_attempt}"
                    if len(retry_idem) > 128:
                        retry_idem = f"reconcile:{hashlib.sha256(corr_id.encode()).hexdigest()[:24]}:attempt:{next_attempt}"
                    cmd = AppendCommand(
                        project_id=project_id,
                        event_type="task.association.requested",
                        payload={
                            "project_id": project_id,
                            "task_id": task_id,
                            "relation": relation,
                            "correlation_id": corr_id,
                            "idempotency_key": retry_idem,
                            "attempt": next_attempt,
                            "max_attempts": limit,
                        },
                        actor="system:reconciler",
                        source="reconciliation",
                        correlation_id=corr_id,
                        idempotency_key=retry_idem,
                    )
                    store.append(cmd)
                    _set_reconcile_attempt(tracker, key, next_attempt)
                    pending_tasks += 1
                else:
                    idempotency_key = f"rec_task_fail_{task_id}_{corr_id}"
                    if len(idempotency_key) > 128:
                        idempotency_key = f"rec_task_fail_{hashlib.sha256(f'{task_id}:{corr_id}'.encode()).hexdigest()[:32]}"
                    cmd = AppendCommand(
                        project_id=project_id,
                        event_type="task.association.failed",
                        payload={
                            "project_id": project_id,
                            "task_id": task_id,
                            "relation": relation,
                            "reason": f"Task {task_id} not found in TaskStore after {past_attempts} attempts",
                            "correlation_id": corr_id,
                            "idempotency_key": idempotency_key,
                        },
                        actor="system:reconciler",
                        source="reconciliation",
                        correlation_id=corr_id,
                        idempotency_key=idempotency_key,
                    )
                    store.append(cmd)
                    failed_tasks += 1
                    _pop_reconcile_attempt(tracker, key)

        # Resolve pending decisions
        for key, (corr_id, payload) in list(pending_decision_sagas.items()):
            decision_id = payload.get("decision_id", "")
            relation = payload.get("relation", "governs")
            limit = min(payload.get("max_attempts", max_attempts), max_attempts)
            history_attempts = requested_counts.get(key, 0)
            past_attempts = max(history_attempts, payload.get("attempt", 1))

            dec_exists = False
            if decision_service is not None:
                try:
                    dec_exists = decision_service.get_decision(decision_id) is not None
                except Exception:
                    dec_exists = False

            if dec_exists:
                idempotency_key = f"rec_dec_{decision_id}_{corr_id}"
                if len(idempotency_key) > 128:
                    idempotency_key = f"rec_dec_{hashlib.sha256(f'{decision_id}:{corr_id}'.encode()).hexdigest()[:32]}"
                cmd = AppendCommand(
                    project_id=project_id,
                    event_type="decision.associated",
                    payload={
                        "project_id": project_id,
                        "decision_id": decision_id,
                        "relation": relation,
                        "correlation_id": corr_id,
                        "idempotency_key": idempotency_key,
                    },
                    actor="system:reconciler",
                    source="reconciliation",
                    correlation_id=corr_id,
                    idempotency_key=idempotency_key,
                )
                store.append(cmd)
                reconciled_decisions += 1
                _pop_reconcile_attempt(tracker, key)
            else:
                if past_attempts < limit:
                    next_attempt = past_attempts + 1
                    retry_idem = f"reconcile:{corr_id}:attempt:{next_attempt}"
                    if len(retry_idem) > 128:
                        retry_idem = f"reconcile:{hashlib.sha256(corr_id.encode()).hexdigest()[:24]}:attempt:{next_attempt}"
                    cmd = AppendCommand(
                        project_id=project_id,
                        event_type="decision.association.requested",
                        payload={
                            "project_id": project_id,
                            "decision_id": decision_id,
                            "relation": relation,
                            "correlation_id": corr_id,
                            "idempotency_key": retry_idem,
                            "attempt": next_attempt,
                            "max_attempts": limit,
                        },
                        actor="system:reconciler",
                        source="reconciliation",
                        correlation_id=corr_id,
                        idempotency_key=retry_idem,
                    )
                    store.append(cmd)
                    _set_reconcile_attempt(tracker, key, next_attempt)
                    pending_decisions += 1
                else:
                    idempotency_key = f"rec_dec_fail_{decision_id}_{corr_id}"
                    if len(idempotency_key) > 128:
                        idempotency_key = f"rec_dec_fail_{hashlib.sha256(f'{decision_id}:{corr_id}'.encode()).hexdigest()[:32]}"
                    cmd = AppendCommand(
                        project_id=project_id,
                        event_type="decision.association.failed",
                        payload={
                            "project_id": project_id,
                            "decision_id": decision_id,
                            "relation": relation,
                            "reason": f"Decision {decision_id} not found in DecisionService after {past_attempts} attempts",
                            "correlation_id": corr_id,
                            "idempotency_key": idempotency_key,
                        },
                        actor="system:reconciler",
                        source="reconciliation",
                        correlation_id=corr_id,
                        idempotency_key=idempotency_key,
                    )
                    store.append(cmd)
                    failed_decisions += 1
                    _pop_reconcile_attempt(tracker, key)

    return {
        "project_id": project_id,
        "reconciled_tasks": reconciled_tasks,
        "failed_tasks": failed_tasks,
        "pending_tasks": pending_tasks,
        "reconciled_decisions": reconciled_decisions,
        "failed_decisions": failed_decisions,
        "pending_decisions": pending_decisions,
    }
