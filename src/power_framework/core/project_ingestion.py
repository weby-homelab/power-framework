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
import logging
import re
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    PrivacyMode,
    ProjectEvent,
    RedactionRecord,
    validate_project_id,
)
from power_framework.core.project_store import (
    ProjectEventStore,
    get_project_dir,
    get_projects_dir,
    project_lock,
    recover_torn_tail,
    replay_events,
    verify_event_ledger,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret Redaction Pipeline (Defense-in-Depth)
# ---------------------------------------------------------------------------

REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
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
                elif isinstance(k, str) and SENSITIVE_KEY_PATTERN.match(k) and isinstance(v, (int, float, bool)):
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
    root = Path(vault_root).expanduser().resolve()
    evidence_dir = root / ".power" / "raw-evidence" / project_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        evidence_dir.chmod(0o700)
    return evidence_dir


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

    # Redact before storing even in full-content mode for baseline hygiene
    scrubbed_content, _ = redact_secrets(raw_content)
    raw_bytes = canonical_json_dumps(scrubbed_content).encode("utf-8")
    digest = compute_payload_digest(scrubbed_content)

    with open(evidence_file, "wb") as f:
        f.write(raw_bytes)
        f.flush()

    with contextlib.suppress(OSError):
        evidence_file.chmod(0o600)

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
    - Level 3 project locking and atomic append
    """
    store = ProjectEventStore(command.project_id, vault_root)

    # 1. Apply Redaction Pipeline
    sanitized_payload, _redaction_record = redact_secrets(command.payload)

    # 2. Apply Privacy Mode Boundaries
    final_payload: dict[str, Any]
    evidence_refs = list(command.evidence_refs)

    if privacy_mode == PrivacyMode.METADATA_ONLY:
        # Strip all content tokens, keep only structure / summary keys
        final_payload = {
            "_privacy_mode": PrivacyMode.METADATA_ONLY.value,
            "keys": sorted(sanitized_payload.keys()),
            "event_type": command.event_type,
        }
    elif privacy_mode == PrivacyMode.STRUCTURED_EVENTS:
        # Structured events: dialogue buffers are purged, only domain state retained
        final_payload = sanitized_payload
        # Remove any lingering raw dialogue fields if caller provided them
        for raw_field in ["raw_dialogue", "dialogue_buffer", "transcript", "turns", "prompt_text"]:
            final_payload.pop(raw_field, None)
    elif privacy_mode == PrivacyMode.FULL_CONTENT:
        # Full content: store evidence locally, reference by cryptographic digest
        final_payload = sanitized_payload
    target_event_id = command.event_id
    if privacy_mode == PrivacyMode.FULL_CONTENT and raw_content is not None:
        target_event_id = target_event_id or f"evt_{command.project_id}_{uuid.uuid4().hex[:12]}"
        evidence_ref = store_raw_evidence(
            vault_root=vault_root,
            project_id=command.project_id,
            event_id=target_event_id,
            raw_content=raw_content,
            ttl_days=raw_evidence_ttl_days,
        )
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
    verify_before_import: bool = True,
    timeout: float = 10.0,
) -> int:
    """Import an existing valid chain of events into the project ledger."""
    validate_project_id(project_id)
    store = ProjectEventStore(project_id, vault_root)

    parsed_events: list[ProjectEvent] = []
    for raw in events:
        if isinstance(raw, ProjectEvent):
            parsed_events.append(raw)
        else:
            parsed_events.append(ProjectEvent.model_validate(raw))

    if not parsed_events:
        return 0

    # Ensure events are ordered by sequence
    parsed_events.sort(key=lambda e: e.sequence)

    with project_lock(project_id, vault_root, timeout=timeout):
        if store.active_events_file.exists():
            recover_torn_tail(store.active_events_file)

        existing_events = list(store.replay(from_sequence=1))
        last_seq = existing_events[-1].sequence if existing_events else 0
        last_hash = existing_events[-1].event_hash if existing_events else ""

        count = 0
        with open(store.active_events_file, "a", encoding="utf-8") as f:
            for ev in parsed_events:
                # Check sequence linkage
                if ev.sequence != last_seq + 1:
                    raise ValueError(
                        f"Import sequence gap: expected {last_seq + 1}, got {ev.sequence}"
                    )
                if last_seq == 0 and ev.prev_event_hash != "":
                    raise ValueError("Genesis event must have empty prev_event_hash")
                if last_seq > 0 and ev.prev_event_hash != last_hash:
                    raise ValueError(
                        f"Import hash gap: expected '{last_hash}', got '{ev.prev_event_hash}'"
                    )

                # Verify integrity of the imported event
                if verify_before_import:
                    calc_payload_digest = compute_payload_digest(ev.payload)
                    if ev.payload_digest != calc_payload_digest:
                        raise ValueError(f"Payload digest mismatch in imported event {ev.event_id}")
                    calc_event_hash = compute_event_hash(ev.model_dump())
                    if ev.event_hash != calc_event_hash:
                        raise ValueError(f"Event hash mismatch in imported event {ev.event_id}")

                line = canonical_json_dumps(ev.model_dump()) + "\n"
                f.write(line)
                last_seq = ev.sequence
                last_hash = ev.event_hash
                count += 1

            f.flush()
            import os
            os.fsync(f.fileno())

    return count


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
    root = Path(vault_root).expanduser().resolve()
    indexes_dir = root / ".power" / "project-state" / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    return indexes_dir / "project_state.sqlite3"


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
            if event.event_type in ("task.associated", "task.association.failed", "task.association.requested"):
                task_id = event.payload.get("task_id", "")
                relation = event.payload.get("relation", "contributes_to")
                status = "associated" if event.event_type == "task.associated" else (
                    "failed" if event.event_type == "task.association.failed" else "requested"
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

            if event.event_type in ("decision.associated", "decision.association.failed", "decision.association.requested"):
                decision_id = event.payload.get("decision_id", "")
                relation = event.payload.get("relation", "governs")
                status = "associated" if event.event_type == "decision.associated" else (
                    "failed" if event.event_type == "decision.association.failed" else "requested"
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
    """
    root = Path(vault_root).expanduser().resolve()
    db_path = _get_sqlite_path(root)
    conn = init_derived_database(db_path)

    project_ids: list[str] = []
    if project_id:
        validate_project_id(project_id)
        project_ids = [project_id]
    else:
        projects_dir = get_projects_dir(root)
        for p in projects_dir.iterdir():
            if p.is_dir() and not p.is_symlink() and p.name.startswith("prj_"):
                project_ids.append(p.name)

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

    content = f"""<!-- GENERATED BY POWER PSE - DO NOT EDIT MANUALLY -->
# Project Status: {project_id}

- **Current Phase:** {last_event.event_type}
- **Last Sequence:** {last_event.sequence}
- **Last Event Hash:** `{last_event.event_hash}`
- **Last Updated:** {last_event.timestamp}
- **Actor:** {last_event.actor}
"""
    with open(status_file, "w", encoding="utf-8") as f:
        f.write(content)

    return status_file


# ---------------------------------------------------------------------------
# Cross-Subsystem Association Saga & Reconciliation (ADR-PSE-008)
# ---------------------------------------------------------------------------

def reconcile_project_subsystems(
    vault_root: Path,
    project_id: str,
    task_service: Any = None,
    decision_service: Any = None,
) -> dict[str, Any]:
    """Idempotently reconcile pending association sagas against TaskStore and DecisionService."""
    validate_project_id(project_id)
    store = ProjectEventStore(project_id, vault_root)

    pending_task_sagas: dict[str, dict[str, Any]] = {}
    pending_decision_sagas: dict[str, dict[str, Any]] = {}

    for event in store.replay(from_sequence=1):
        corr_id = event.correlation_id or event.idempotency_key or event.event_id

        # Track task sagas
        if event.event_type == "task.association.requested":
            pending_task_sagas[corr_id] = event.payload
        elif event.event_type in ("task.associated", "task.association.failed"):
            pending_task_sagas.pop(corr_id, None)

        # Track decision sagas
        if event.event_type == "decision.association.requested":
            pending_decision_sagas[corr_id] = event.payload
        elif event.event_type in ("decision.associated", "decision.association.failed"):
            pending_decision_sagas.pop(corr_id, None)

    reconciled_tasks = 0
    failed_tasks = 0
    reconciled_decisions = 0
    failed_decisions = 0

    # Resolve pending tasks
    for corr_id, payload in pending_task_sagas.items():
        task_id = payload.get("task_id", "")
        relation = payload.get("relation", "contributes_to")
        idempotency_key = f"rec_task_{task_id}_{corr_id}"

        task_exists = False
        if task_service is not None:
            try:
                task_exists = task_service.get_task(task_id) is not None
            except Exception:
                task_exists = False

        if task_exists:
            cmd = AppendCommand(
                project_id=project_id,
                event_type="task.associated",
                payload={"project_id": project_id, "task_id": task_id, "relation": relation},
                actor="system:reconciler",
                source="reconciliation",
                correlation_id=corr_id,
                idempotency_key=idempotency_key,
            )
            store.append(cmd)
            reconciled_tasks += 1
        else:
            cmd = AppendCommand(
                project_id=project_id,
                event_type="task.association.failed",
                payload={
                    "project_id": project_id,
                    "task_id": task_id,
                    "relation": relation,
                    "reason": f"Task {task_id} not found in TaskStore during reconciliation",
                },
                actor="system:reconciler",
                source="reconciliation",
                correlation_id=corr_id,
                idempotency_key=idempotency_key,
            )
            store.append(cmd)
            failed_tasks += 1

    # Resolve pending decisions
    for corr_id, payload in pending_decision_sagas.items():
        decision_id = payload.get("decision_id", "")
        relation = payload.get("relation", "governs")
        idempotency_key = f"rec_dec_{decision_id}_{corr_id}"

        dec_exists = False
        if decision_service is not None:
            try:
                dec_exists = decision_service.get_decision(decision_id) is not None
            except Exception:
                dec_exists = False

        if dec_exists:
            cmd = AppendCommand(
                project_id=project_id,
                event_type="decision.associated",
                payload={"project_id": project_id, "decision_id": decision_id, "relation": relation},
                actor="system:reconciler",
                source="reconciliation",
                correlation_id=corr_id,
                idempotency_key=idempotency_key,
            )
            store.append(cmd)
            reconciled_decisions += 1
        else:
            cmd = AppendCommand(
                project_id=project_id,
                event_type="decision.association.failed",
                payload={
                    "project_id": project_id,
                    "decision_id": decision_id,
                    "relation": relation,
                    "reason": f"Decision {decision_id} not found in DecisionService during reconciliation",
                },
                actor="system:reconciler",
                source="reconciliation",
                correlation_id=corr_id,
                idempotency_key=idempotency_key,
            )
            store.append(cmd)
            failed_decisions += 1

    return {
        "project_id": project_id,
        "reconciled_tasks": reconciled_tasks,
        "failed_tasks": failed_tasks,
        "reconciled_decisions": reconciled_decisions,
        "failed_decisions": failed_decisions,
    }
