# POWER Project State Engine (PSE) — Canonical Event Ledger Specification v1

- **Document Version:** 1.0.0
- **Status:** APPROVED & FROZEN (Phase 2 Deliverable)
- **Authoritative Modules:**
  - `power_framework.core.canonical_json`
  - `power_framework.core.project_models`
  - `power_framework.core.project_store`
  - `power_framework.core.project_ingestion`
- **Specification References:** ADR-PSE-001, ADR-PSE-002, ADR-PSE-005, ADR-PSE-006, ADR-PSE-007, ADR-PSE-008

---

## 1. Architectural Overview & Storage Layout

The canonical source of truth for all project governance state (lifecycle transitions, RAID logs, RACI assignments, quality gates, and cross-subsystem sagas) is an append-only, cryptographically chained JSONL event stream located within the vault control hierarchy:

```text
<vault_root>/
└── .power/
    ├── projects/
    │   └── <project_id>/
    │       ├── .lock                  # Level 3 project lock (0600)
    │       ├── events.jsonl           # Active canonical append-only ledger
    │       ├── events_000001.jsonl    # Rotated immutable partition (optional)
    │       ├── events_000002.jsonl    # Rotated immutable partition (optional)
    │       └── status.md              # Materialized markdown projection
    ├── project-state/
    │   └── indexes/
    │       └── project_state.sqlite3  # Disposable secondary relational index
    └── raw-evidence/                  # Local-only evidence (PrivacyMode: full-content)
        └── <project_id>/
            └── <event_id>.json        # POSIX 0600, pruned by TTL (default 14 days)
```

### Boundary & Security Invariants
1. **Identifier Bounds:** `project_id` must match `^prj_[a-z0-9][a-z0-9_-]{2,63}$`. Path traversal characters (`..`, `/`, `\`) are strictly forbidden and fail-closed with `ValueError`.
2. **Symlink Prohibition:** Project directories, `.lock` files, and `.jsonl` files must never be symlinks. Any symlink dereference attempt raises `ValueError` before acquiring locks or reading files.
3. **Immutability:** Existing event lines in `events.jsonl` are strictly write-once. Modifications or deletions are prohibited. Corrections are appended as new events.

---

## 2. Canonical Serialization: POWER Canonical JSON v1

All cryptographic hashes and file records are computed using **POWER Canonical JSON v1** via `power_framework.core.canonical_json`:

```python
json.dumps(
    data,
    sort_keys=True,
    ensure_ascii=False,
    separators=(",", ":"),
    allow_nan=False,
)
```

- **Encoding:** UTF-8 without BOM.
- **Fail-Closed Numbers:** Non-finite floats (`NaN`, `Infinity`, `-Infinity`) are rejected with `ValueError`.
- **Frozen Byte Vector:**
  - Input: `{"z": 1, "a": "Україна", "nested": {"b": False, "a": None}}`
  - Output Text: `{"a":"Україна","nested":{"a":null,"b":false},"z":1}`
  - UTF-8 Bytes: `b'{"a":"\xd0\xa3\xd0\xba\xd1\x80\xd0\xb0\xd1\x97\xd0\xbd\xd0\xb0","nested":{"a":null,"b":false},"z":1}'`
  - SHA-256 Digest: `9cfb88b8b7087e11cd405596bc4b988dc2c49164d1ccbe21a35e25c0bd971a98`

---

## 3. Two-Tier Envelope Hash Chain (ADR-PSE-006)

Every event is cryptographically sealed in two tiers:

### Tier 1 — Inner Payload Digest (`payload_digest`)
```python
payload_digest = hashlib.sha256(canonical_json_bytes(event.payload)).hexdigest()
```
Ensures content immutability independently of envelope headers.

### Tier 2 — Envelope Hash (`event_hash`)
```python
integrity_record = {k: v for k, v in event.items() if k != "event_hash"}
event_hash = hashlib.sha256(canonical_json_bytes(integrity_record)).hexdigest()
```
Seals the complete event envelope:
- `event_id`
- `schema_version` (`"power.project-event.v1"`)
- `project_id`
- `sequence`
- `timestamp` (RFC 3339 UTC)
- `actor`
- `source`
- `session_id`
- `event_type`
- `payload`
- `payload_digest`
- `prev_event_hash`
- `artifact_refs`
- `evidence_refs`
- `correlation_id`
- `causation_id`
- `idempotency_key`

### Chain Linkage Invariants
- **Genesis Event (`sequence == 1`):** `prev_event_hash` must be the empty string `""`.
- **Subsequent Events (`sequence > 1`):** `prev_event_hash` must equal the exact `event_hash` of the preceding record (`sequence - 1`).
- **Monotonicity:** Sequences strictly increment: $S_{i} = S_{i-1} + 1$.

---

## 4. Multi-Subsystem Lock Hierarchy (ADR-PSE-007)

To prevent cross-process deadlocks when combining Vault mutations, TaskStore, and PSE, operations strictly observe a **3-level ascending lock hierarchy**:

```text
Level 1: Vault Mutation Lock (.power/mutation.lock)
   │
   ▼ (acquired first)
Level 2: TaskStore Process Lock (.power/tasks/.lock)
   │
   ▼ (acquired second)
Level 3: PSE Project Process Lock (.power/projects/<project_id>/.lock)
```

- **Rule:** A thread or process holding lock Level $K$ may only acquire Level $M$ if $M > K$. Acquiring Level 1 or 2 while holding Level 3 triggers an immediate `RuntimeError`.
- **Isolation:** Level 3 locks are fine-grained per `project_id`. Modifying `prj_alpha` does not block `prj_beta`.
- **Bounded Timeout:** Default 10.0s timeout. Failure raises `LockAcquisitionTimeoutError`.

---

## 5. Crash Resilience & Torn-Tail Recovery

### Torn-Tail Recovery Algorithm
When `events.jsonl` is opened for read or append:
1. File lines are scanned sequentially.
2. If the trailing line at EOF is incomplete (no `\n`, unclosed JSON, or truncated hash caused by power outage or `kill -9`), `recover_torn_tail()` truncates the file back to the last valid cryptographic boundary.
3. Truncation is logged with the count of discarded bytes.
4. If corruption occurs in a non-trailing line, it is preserved so `verify_event_ledger()` flags it as an integrity violation rather than silently discarding historical mutations.

---

## 6. Safe Ledger Rotation

- Ledgers may be rotated using `ProjectEventStore.rotate()`.
- Active `events.jsonl` is atomically renamed to `events_000001.jsonl`, and a new `events.jsonl` is initialized.
- Subsequent appends link `sequence` and `prev_event_hash` continuously against the archived tail.
- `replay_events()` and `verify_event_ledger()` automatically discover and traverse all partitions in sequential order.

---

## 7. Privacy Modes & Redaction Boundary (ADR-PSE-005)

### Operational Privacy Modes
1. **`metadata-only`**: Payload content is stripped; only field names and event metadata are retained.
2. **`structured-events` (Default)**: In-memory dialogue buffers and prompts are purged; only structured domain entities (RAID, RACI, gate evaluations) are stored.
3. **`full-content` (Explicit Opt-In)**: Raw dialogue is stored locally in `.power/raw-evidence/<project_id>/<event_id>.json` (mode `0600`), and referenced in the event by its SHA-256 digest (`evidence_refs: ["sha256:..."]`). Automated TTL pruning purges files older than 14 days (or user-defined policy).

### Deterministic Secret Redaction
Before persistence, all payloads pass through the regex-based scrubbing pipeline targeting:
- RSA / OpenSSH Private Keys (`[REDACTED_PRIVATE_KEY]`)
- Bearer Tokens (`Bearer [REDACTED_TOKEN]`)
- GitHub Personal Access Tokens (`[REDACTED_GITHUB_TOKEN]`)
- AWS Access Keys (`[REDACTED_AWS_KEY]`)
- `.env` Key-Value Assignments (`KEY=[REDACTED]`)
- Sensitive Dict Keys (`password`, `api_key`, `secret`, `auth` values -> `[REDACTED]`)

Execution emits a `RedactionRecord` logging replacement counts and detected classes without leaking secrets.

---

## 8. Disposable Derived Projections (ADR-PSE-002)

1. **Secondary SQLite Database:** `.power/project-state/indexes/project_state.sqlite3`
   Provides relational querying over projects, events, RAID items, RACI matrices, and gate evaluations.
2. **Markdown Status Projection:** `.power/projects/<project_id>/status.md`
   Rendered Markdown dashboard bearing comment `<!-- GENERATED BY POWER PSE - DO NOT EDIT MANUALLY -->`.
3. **100% Rebuild Guarantee:** Deleting `project_state.sqlite3` or any projection file causes zero data loss. Running `rebuild_derived_index()` deterministically reconstructs the entire relational database by replaying canonical `events.jsonl`.
