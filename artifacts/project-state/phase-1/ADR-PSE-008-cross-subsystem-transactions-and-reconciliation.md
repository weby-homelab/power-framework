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
2. **Durable Association-Intent Saga (No 2PC):**
   - We eliminate any assumption that `PowerTask` possesses a `metadata.project_id` or text scope field (`PowerTask` has no `metadata` container).
   - Cross-subsystem association is driven exclusively via a durable, PSE-managed association-intent Saga:
     - **Task Association Saga:**
       `task.association.requested` -> operation / validation against `TaskService` -> `task.associated` (or `task.association.failed` on terminal failure).
       *Mandatory fields for `task.association.requested` payload:* `project_id`, `task_id`, `relation`, `correlation_id`, `idempotency_key`.
     - **Decision Association Saga:**
       `decision.association.requested` -> operation / validation against `DecisionService` -> `decision.associated` (or `decision.association.failed` on terminal failure).
       *Mandatory fields for `decision.association.requested` payload:* `project_id`, `decision_id`, `relation`, `correlation_id`, `idempotency_key`.
3. **Idempotent Reconciliation Protocol (`reconcile_project_subsystems`):**
   - PSE includes an idempotent reconciliation engine running on startup, periodic cron, or on-demand:
     1. **Saga Intent Recovery:** Scans the project event ledger for pending `*.association.requested` events that lack a corresponding terminal event (`*.associated` or `*.association.failed`) matching their `correlation_id` / `idempotency_key`.
     2. **Subsystem Inquiry:** Queries `TaskStore.get_task(task_id)` or `DecisionService.get_decision(decision_id)`.
     3. **Deterministic Resolution:**
        - If the authoritative entity exists in `TaskStore` or `DecisionService`, PSE appends an idempotent `task.associated` or `decision.associated` event (`source: "reconciliation"`, `actor: "system:reconciler"`).
        - If the entity does not exist and retry timeout policy has elapsed, PSE appends a `task.association.failed` or `decision.association.failed` event recording the failure reason.
     4. **Terminal Status Observation:** When evaluating DoR/DoD gates, PSE queries the live authoritative state directly from `TaskStore` and `DecisionService`, optionally recording a `task.lifecycle.observed` or `decision.lifecycle.observed` event if status auditing is configured.
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
