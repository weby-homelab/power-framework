# ADR-PSE-004: Integration with Existing TaskStore and DecisionService Subsystems

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** POWER 3.7.11 already possesses production-grade `TaskService`/`TaskStore` (Task v2) and `DecisionService` (Decision v1) engines. PSE must coordinate with these services without usurping authority or creating duplicate stores.

## Context and Problem Statement
When designing a Project State Engine, a common anti-pattern is re-implementing task tracking and decision logs inside the project engine. This creates duplicate data models, dual-write corruption, synchronization lag, and split-brain states where `TaskStore` reports a task as completed while PSE reports it as in-progress. We must strictly delineate subsystem authority.

## Decision Drivers
- Zero duplication of canonical data models (Gate G1.3).
- Strict adherence to the Phase 0 Authority Matrix.
- Loose coupling: PSE should consume tasks and decisions by reference, not by containment.
- Preservation of existing crash-recovery and transaction semantics in `TaskStore`.

## Decision Outcome
Chosen Solution: **Referential Binding via Authoritative Subsystem Delegations**.

### Subsystem Authority Boundaries:
1. **Task Subsystem (`TaskStore` / `TaskService`):**
   - **Sole Authority:** `PowerTask v2`, task lifecycle state machine (`backlog -> ready -> working -> completed`), execution leases, retry policies, and `TaskCompletionReceipt`.
   - **Canonical Storage:** `.power/tasks/<task_id>.json` and append-only `.power/tasks/events.jsonl`.
2. **Decision Subsystem (`DecisionService`):**
   - **Sole Authority:** `Decision` entities, proposal validation, vote/resolution processing, and `DecisionReceipt`.
   - **Canonical Storage:** `.power/decisions/<decision_id>.json`.
3. **Project State Engine (`PSE`):**
   - **Sole Authority:** `Project` lifecycle aggregates, project-level RAID entities, RACI assignments, quality gates (DoR/DoD), and *typed relationship graphs*.
   - **Canonical Storage:** `.power/projects/<project_id>/events.jsonl`.

### Contract for Cross-Subsystem Relationships:
- **Reference by ID Only:** PSE events and snapshots store only the foreign identifiers `task_id` and `decision_id` (e.g. within `task_refs`, `decision_refs`, and `dependencies`).
- **No Shadow Task Stores:** PSE will NEVER create a table or file claiming authoritative ownership of a task's title, assignee, or execution state.
- **Dynamic Join and Projection:** When PSE displays a project dashboard or computes DoD predicates (e.g. `all_tasks_terminal`), the PSE projection engine dynamically inspects the authoritative `TaskStore` snapshot or queries the synchronized SQLite projection table populated from `TaskStore`.
- **Event-Driven Linking:** When a task is created or linked to a project, PSE emits `task.associated` with `{"task_id": "...", "relation": "deliverable"}`. It does not re-emit `task.created` with full task attributes.

## Consequences
### Positive
- Strict single source of truth across the entire POWER framework.
- Zero risk of split-brain or divergent task/decision state.
- Task management upgrades or schema additions can proceed independently in `TaskStore` without breaking PSE.

### Negative
- Computing project status requires cross-subsystem queries or a unified query projection layer.
