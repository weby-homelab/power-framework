# POWER 3.7.11 Canonical Authority Matrix & Coordination Architecture

**Date:** 2026-09-03  
**Repository:** `https://github.com/weby-homelab/power-framework`  
**Baseline Commit:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`  
**Status:** BINDING ARCHITECTURAL MANDATE (Phase 0 Closure Artifact)

---

## 1. Executive Summary

This document establishes the binding canonical authority boundaries, coordination protocols, and data ownership rules between the existing POWER 3.7.11 core subsystems and the upcoming Project State Engine (PSE) in POWER 3.8.

**Core Mandate:** PSE is STRICTLY PROHIBITED from becoming a second canonical Task store or Decision store. All domain entities, lifecycle mutations, and state representations must have exactly one authoritative subsystem as defined below.

---

## 2. Canonical Authority Matrix

| Domain Entity / Artifact | Authoritative Subsystem / Store | Authority Type | Nature & Persistence |
|---|---|:---:|---|
| **Task** | `TaskService` / `TaskStore` | **Canonical** | Source of truth in `.power/tasks/*.json`. |
| **Task lifecycle events** | `TaskStore` TaskEvent journal | **Canonical** | Source of truth in `.power/tasks/events/<task_id>.jsonl`. |
| **Decision approval/workflow** | `DecisionService` | **Canonical** | Source of truth in `.power/tasks/decisions/<decision_id>.json`. |
| **Decision receipts** | `DecisionService` | **Canonical** | Source of truth in `.power/tasks/decisions/receipts/<receipt_id>.json`. |
| **Project lifecycle** | `PSE` (Project State Engine) | **Canonical** | Source of truth in PSE Event Ledger (`.power/project-state/events/`). |
| **Risk** | `PSE` (Project State Engine) | **Canonical** | Domain entity owned by PSE event ledger. |
| **Assumption** | `PSE` (Project State Engine) | **Canonical** | Domain entity owned by PSE event ledger. |
| **Project Issue** | `PSE` (Project State Engine) | **Canonical** | Domain entity owned by PSE event ledger. |
| **Project Dependency** | `PSE` (Project State Engine) | **Canonical** | Domain entity owned by PSE event ledger. |
| **Observation** | `PSE` (Project State Engine) | **Canonical** | Raw or classified observation owned by PSE. |
| **Lesson** | `PSE` (Project State Engine) | **Canonical** | Validated retrospective insight owned by PSE. |
| **Project↔Task relation** | `PSE` (Project State Engine) | **Canonical** | Typed sidecar relation/event owned by PSE, referencing canonical `task_id`. |
| **Project↔Decision relation** | `PSE` (Project State Engine) | **Canonical** | Typed sidecar relation/event owned by PSE, referencing canonical `decision_id`. |
| **ContextPack** | Derived / Rebuildable | **Derived** | Ephemeral or cached bundle compiled deterministically from canonical sources. |
| **SQLite projection** | Derived / Rebuildable | **Derived** | Secondary read/query index in `.power/project-state/indexes/project_state.sqlite3`. Rebuildable via `rebuild_from_events()`. |
| **FTS/vector/graph index** | Derived / Rebuildable | **Derived** | Managed by `core.generation_index` / `core.searcher`. 100% rebuildable from vault and ledger. |
| **Materialized project views** | Derived / Rebuildable | **Derived** | Human-readable views (`meta.json`, `ADR-*.md`, `raid_log.json`, `current-sprint.md`, `lessons-*.md`) derived from ledger unless explicitly governed otherwise. |

### Architectural Prohibition: No Second Core
- PSE must **NEVER** instantiate a parallel task repository, task table in SQLite, or independent task JSON files.
- PSE must **NEVER** instantiate a parallel decision repository or approval mechanism.
- Any attempt by PSE to claim canonical ownership of Task or Decision domain models is a blocking architectural violation.

---

## 3. Task v2 Integration Contract & Phase 1 Direction

### Forensic Baseline Reality
At baseline commit `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`, the `PowerTask` model (`src/power_framework/core/task_models.py:87-126`) adheres strictly to:
- `model_config = ConfigDict(extra="forbid")`
- Explicit typed fields: `task_id`, `vault_id`, `tenant_id`, `kind`, `title`, `objective`, `owner`, `assignee`, `state`, `priority`, `scope`, `authority`, `dependencies`, `source_revision`, `next_action`, `open_gates`, `required_input`, `artifact_refs`, `receipt_ids`, `external_refs`, `attempt`, `max_attempts`, `retry_at`, `lease_owner`, `lease_expires_at`, `heartbeat_at`, `execution_state`, `error_ref`, `dead_letter_reason`, `revision`, `created_at`, `updated_at`, `due_at`, `completion_policy`.
- **NO `metadata` field exists on `PowerTask`.**
- Passing arbitrary fields (such as `metadata["project_id"]` or `sprint`) raises a Pydantic `ValidationError`.

### Default Phase 1 Direction
```text
TaskService / TaskStore remain canonical for Task v2.

Project↔Task membership is owned by PSE through a typed relation/event or equivalent sidecar relation, referencing canonical task_id.

Adding project_id directly to PowerTask requires a separate ADR and is NOT assumed.
```

- In Phase 0, `PowerTask` remains completely unmodified.
- PSE relates tasks to projects, sprints, phases, and RAID entities via its own typed event ledger (e.g., `TASK_ATTACHED_TO_PROJECT`, `TASK_ASSOCIATED_WITH_RAID`) or sidecar relational projections.

---

## 4. TaskEvent Hash-Chain Baseline Contract vs. ProjectEvent v1 ADR Mandate

### TaskEvent Baseline Reality
In POWER 3.7.11 (`src/power_framework/core/task_models.py:162-209`, `src/power_framework/core/task_store.py:291-318`), the existing event verification contract is strictly:
```text
payload_digest = SHA256(canonical payload)
prev_event_digest = previous TaskEvent.payload_digest
```
During replay / validation, `TaskStore.get_task_events()` verifies:
1. `ev.task_id == task_id`
2. `ev.sequence == expected_sequence` (monotonic increment from 1)
3. `ev.prev_event_digest == expected_previous` (matches previous event's `payload_digest`)
4. `ev.payload_digest == canonical_payload_digest(ev.payload)`

It does **not** hash the full event envelope (actor, event_type, created_at, event_id).

### Phase 1 ADR Mandate for ProjectEvent v1
For `ProjectEvent` v1, Phase 1 must **explicitly decide via an ADR** whether to:
- **Option A:** Reuse equivalent payload-chain semantics (`payload_digest` + `prev_event_digest = prev.payload_digest`); OR
- **Option B:** Implement a stronger full-event envelope hash:
  ```text
  event_hash = SHA256(
      canonical event envelope
      including previous_event_hash
  )
  ```

**Mandate:** No hash-chain design decision is to be silently inherited from `TaskEvent`. The cryptographic integrity level for the PSE ledger must be an intentional architectural decision documented in Phase 1.

---

## 5. Coordination Layers, Locking Hierarchy & Transaction Risks

### Current Coordination Layers in POWER 3.7.11
The system currently operates two distinct, critical synchronization mechanisms:
1. **Vault Mutation Lock** (`src/power_framework/core/mutation.py:69-99`):
   - In-process `threading.RLock` + cross-process advisory file lock (`.power/mutation.lock`).
   - Serializes vault-wide write mutations (`execute_vault_mutation`).
2. **TaskStore Lock & Crash-Recovery Transaction** (`src/power_framework/core/task_store.py:72-108, 366-432`):
   - In-process `threading.RLock` + cross-process file lock (`.power/tasks/.lock`).
   - Two-phase crash-recovery transaction manifest (`.power/tasks/.tx/<tx_id>/manifest.json`) supporting atomic multi-artifact writes (task snapshot, event append, checkpoint, receipt) with automatic rollback and crash reconciliation (`recover()`).

### Identified Concurrency & Deadlock Risks
- If PSE introduces a third independent lock (e.g. `project_state.lock`) without a defined acquisition order, any cross-subsystem workflow (e.g. updating task and recording PSE event) can deadlock if caller A acquires `mutation.lock` then `tasks/.lock` then `pse.lock`, while caller B acquires `pse.lock` then `tasks/.lock`.
- If PSE attempts distributed 2-phase commits or synchronous dual-writes with `TaskStore` or `DecisionService`, network or process crashes can cause dual-write corruption, orphan manifests, or inconsistent split-brain states.

### Phase 1 ADR Mandate
Phase 1 must produce an ADR defining:
1. **Lock hierarchy:** Strict acquisition order across all subsystems (e.g., `vault mutation lock` -> `TaskStore lock` -> `PSE lock`).
2. **Cross-subsystem transaction semantics:** Rules governing multi-service operations.
3. **Failure recovery:** Recovery behavior when crashes occur mid-operation.
4. **Idempotent reconciliation:** Healing protocol for secondary projections and references.

### Default Design Direction
```text
Do not require atomic mirrored PSE events for canonical Task/Decision operations.

TaskService and DecisionService remain authoritative.

PSE projections/references must be idempotently reconcilable from their authoritative stores.
```
This design deliberately avoids dual-write corruption, eliminates distributed transaction overhead, and ensures each authoritative subsystem can function reliably under partition or restart.

---

## 6. AuditReceipt & Semantic Ingestion Boundary

### Baseline Reality
`AuditReceipt` (`src/power_framework/core/application.py:85-106`) is emitted by `ApplicationService._run`:
- Attributes: `operation`, `status`, `request_id`, `idempotency_key`, `sha256`, `duration_ms`.
- Content-free design: deliberately captures operation metadata and payload hash, not the semantic body.

### Architectural Ingestion Rule
```text
AuditReceipt/audit_hook is an operation-level capture signal.

It is NOT sufficient as the primary semantic-content ingestion mechanism because the receipt intentionally carries operation metadata/digests rather than full semantic input/output.
```

- PSE may consume `AuditReceipt` via `audit_hook` strictly for operational telemetry, execution tracking, and audit correlation.
- Semantic domain content (decisions, risks, assumptions, task relationships, notes) must be ingested via explicit typed application APIs, ContextPack compilations, or governed domain events.
