# ADR-PSE-007: Strict Multi-Subsystem Lock Hierarchy and Deadlock Prevention

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** POWER combines file vault mutations, TaskStore transactions, and now Project State Engine event streams. Multiple concurrent processes (FastAPI, MCP servers, CLI commands, background daemons) write to these subsystems simultaneously.

## Context and Problem Statement
In Phase 0, an investigation revealed that `mutation.py` uses `.power/mutation.lock`, and `task_store.py` uses `.power/tasks/.lock`. If PSE introduces an independent lock (e.g. `.power/projects/<project_id>/.lock`) without a strictly enforced global acquisition hierarchy, cross-subsystem operations will inevitably deadlock when process A holds the task lock and requests the project lock, while process B holds the project lock and requests the task lock.

## Decision Drivers
- Absolute mathematical deadlock prevention via total lock ordering.
- Concurrency isolation: modifications to Project A must not block modifications to Project B.
- Strict consistency across multi-subsystem workflows.
- Alignment with Requirement #7.

## Decision Outcome
Chosen Solution: **Strict 3-Level Ascending Lock Acquisition Hierarchy**.

### Lock Ordering Hierarchy:
Locks must ALWAYS be acquired in ascending numerical order, and released in descending order (LIFO):

```text
┌────────────────────────────────────────────────────────┐
│ LEVEL 1: Vault Mutation Lock                           │
│ Path: .power/mutation.lock                             │
│ Scope: Vault-wide markdown file mutations              │
└──────────────────────────┬─────────────────────────────┘
                           │ (Acquired 1st)
                           ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 2: TaskStore Process Lock                        │
│ Path: .power/tasks/.lock                               │
│ Scope: TaskStore mutations, manifests, task events     │
└──────────────────────────┬─────────────────────────────┘
                           │ (Acquired 2nd)
                           ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 3: PSE Project Process Lock                      │
│ Path: .power/projects/<project_id>/.lock               │
│ Scope: Fine-grained per-project event stream append    │
└────────────────────────────────────────────────────────┘
```

### Hierarchy Rules:
1. **Total Order Invariant:**
   A thread or process holding a lock at Level $K$ may ONLY acquire a lock at Level $M$ if $M > K$. Acquiring a lower-level lock while holding a higher-level lock (e.g. acquiring Level 2 while holding Level 3) is **categorically illegal** and will trigger an immediate runtime error.
2. **Fine-Grained Project Locks:**
   Level 3 locks are scoped per `project_id`. Process 1 appending to `prj_alpha` and Process 2 appending to `prj_beta` acquire `.power/projects/prj_alpha/.lock` and `.power/projects/prj_beta/.lock` respectively, running in full parallel concurrency without contention.
3. **Bounded Lock Wait Time:**
   All lock acquisitions must employ a deterministic timeout (default 10.0 seconds). If a lock cannot be acquired within the timeout, the acquisition raises `LockAcquisitionTimeoutError` and releases all previously held locks before unwinding the stack.
4. **Context Manager Enforcement:**
   Locks must always be used via Python context managers (`with project_lock(project_id):`) to guarantee cleanup and descriptor release even on unhandled exceptions or crashes.

## Consequences
### Positive
- Deadlocks are mathematically impossible when all processes follow the ascending acquisition order.
- High write concurrency for independent projects across agentic workers.
- Complete compatibility with existing `execute_vault_mutation()` and `TaskStore.lock()` patterns.

### Negative
- Developers must be disciplined never to invert the acquisition order in cross-cutting scripts.
