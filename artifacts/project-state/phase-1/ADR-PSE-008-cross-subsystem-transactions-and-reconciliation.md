# ADR-PSE-008: Cross-Subsystem Transaction Semantics, Crash Recovery, and Idempotent Reconciliation

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** Operations often span multiple boundaries—for example, completing a task in `TaskStore` while simultaneously evaluating a project Definition of Done (DoD) gate in PSE.

## Context and Problem Statement
Distributed synchronous transactions (such as Two-Phase Commit / 2PC) across filesystem-based stores are notoriously brittle. If a crash, kill signal, or power cut occurs between committing a task in `TaskStore` and writing an event to PSE's `events.jsonl`, a synchronous dual-write architecture will leave the system in a corrupted or indefinite split-brain state. We must establish robust cross-subsystem transaction semantics and automatic crash reconciliation.

## Decision Drivers
- Zero-loss and zero-corruption resilience under ungraceful termination (`kill -9`, power failure).
- Rejection of fragile distributed locks and synchronous 2PC (Requirements #8 and #9).
- Subsystem autonomy: TaskStore and DecisionService must be able to operate even if PSE is undergoing maintenance or rebuilding.
- Idempotent self-healing and reconciliation.

## Decision Outcome
Chosen Solution: **Event-Driven Outbox / Reactive Linking with Idempotent Periodic Reconciliation**.

### Architectural Contract:
1. **No Synchronous Two-Phase Commit (2PC):**
   - We explicitly prohibit distributed synchronous transactions requiring atomic dual-writes across `TaskStore` and `PSE`.
   - Operations in `TaskService` and `DecisionService` commit directly to their authoritative stores under their own locks.
2. **Asynchronous / Reactive Association:**
   - When a task or decision is created or resolved in the context of a project, the calling agent or workflow coordinator emits a linking event to the PSE ledger (`task.associated`, `decision.associated`, or `evidence.attached`).
   - If the PSE event append fails or the process is killed before PSE can record the link, the primary task or decision remains safe and fully committed.
3. **Idempotent Reconciliation Protocol (`reconcile_project_subsystems`):**
   - PSE includes an idempotent reconciliation engine that can run on startup, periodic cron, or on-demand:
     1. **TaskStore Inspection:** Queries `TaskStore` for all tasks carrying `project_id == target_project_id` in their scope or metadata.
     2. **Reference Validation:** Compares discovered tasks against the project's recorded `task_refs` and dependencies.
     3. **Missing Association Healing:** If an authoritative task exists but is not yet indexed in PSE, the engine appends a synthetic idempotent `task.associated` event with `source: "reconciliation"` and `actor: "system:reconciler"`.
     4. **Terminal Status Synchronization:** When evaluating DoR/DoD gates, PSE always queries the live authoritative state of tasks directly from `TaskStore`, never relying on potentially stale cached mirror fields.
4. **Crash Recovery for Event Stream (`events.jsonl`):**
   - On startup, the ledger reader validates the cryptographic hash chain of `.power/projects/<project_id>/events.jsonl`.
   - If a partial line or unclosed JSON object is detected at the tail (caused by a crash during disk write), the recovery procedure truncates the file back to the last valid newline with a matching `event_hash`.
   - Recovery is fully logged with an operational audit record.

## Consequences
### Positive
- Subsystems remain completely decoupled; failure in PSE never prevents tasks or decisions from completing.
- The system is self-healing: any temporary drift between subsystems is automatically repaired during standard reconciliation.
- Crash recovery is mathematically deterministic and leaves zero orphaned manifests.

### Negative
- Cross-subsystem state is eventually consistent rather than instantly atomic.
