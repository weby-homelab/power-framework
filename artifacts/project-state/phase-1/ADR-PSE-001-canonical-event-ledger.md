# ADR-PSE-001: Canonical Append-Only Event Ledger as Primary Source of Truth

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** POWER Project State Engine (PSE) requires a durable, crash-resilient, verifiable representation of project state across the lifecycle.

## Context and Problem Statement
In existing systems, project state is often kept in mutable database rows or mutable markdown files. This introduces risks of lost update anomalies, race conditions, silent data corruption, and inability to audit the historical evolution or provenance of decisions and phase transitions. We need a primary source of truth that guarantees strict immutability, complete audit trails, and zero ambiguity about current and past states.

## Decision Drivers
- Total audibility and temporal provenance of all project mutations.
- Crash resilience and zero-loss guarantees in homelab and agentic environments.
- Simplicity and transparent inspectability via standard POSIX and CLI tools.
- Clean separation between primary authoritative state and disposable query projections.

## Considered Options
1. **Direct SQLite Database as Authoritative Store:** Keep project entities in mutable SQLite tables with triggers or transaction logs.
2. **Append-Only JSONL Event Ledger per Project (`events.jsonl`):** Store every state transition and mutation as an immutable canonical JSON line, deriving current state and secondary indexes purely from replaying this ledger.
3. **Git-backed Markdown Files as Canonical Store:** Commit frontmatter updates to markdown files in Obsidian vault directly for every state change.

## Decision Outcome
Chosen Option: **Option 2: Append-Only JSONL Event Ledger per Project**.

Each project managed by PSE maintains its authoritative event stream at:
```text
.power/projects/<project_id>/events.jsonl
```

### Key Architectural Rules:
1. **Single Source of Truth:** The file `.power/projects/<project_id>/events.jsonl` is the *sole* canonical authority for the project's state, RAID logs, RACI assignments, and gate evaluations.
2. **Append-Only Mutation:** Records are strictly appended line-by-line (`O_APPEND | O_CREAT`). In-place edits, overwrites, or deletions of previous lines are strictly prohibited.
3. **Atomic Flush and Fsync:** Every event write must execute `flush()` and `os.fsync()` under the project lock before releasing control.
4. **Disposable Projections:** Any database (SQLite), cache, or markdown dashboard (`status.md`) is strictly a derived view. If any secondary storage is corrupted or deleted, the full state is 100% deterministically reconstructible by replaying `events.jsonl`.
5. **Tail Recovery:** In the event of a power outage or process kill mid-write, any unsealed, partially written line at EOF is detected during recovery and safely truncated back to the last valid cryptographic hash boundary.

## Consequences
### Positive
- Zero ambiguity: state at any point in time $T$ can be reproduced by replaying events up to timestamp $T$.
- Immutability protects against subtle bugs where state variables are overwritten without audit trail.
- Straightforward backup and diff inspection via standard Unix text utilities.

### Negative
- Read performance requires maintaining an up-to-date secondary projection (SQLite cache) to prevent full replay on every read.
- Event schema evolutions must be backward-compatible or handled via explicit schema migration upcasters.
