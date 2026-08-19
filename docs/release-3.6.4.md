# P.O.W.E.R. 3.6.4 release notes

P.O.W.E.R. 3.6.4 hardens the canonical state machines (Task v2, Decision, Memory
apply) with **crash-consistent multi-artifact transactions**. A hard process kill
between writes no longer leaves an unrecoverable orphan/hybrid state: a transaction
manifest (WAL) is written first and reconciled automatically on the next process
start.

## What changed

- **Crash-consistent transaction manifest (`TaskStore`)**: snapshot, event,
  checkpoint (every 5th sequence), completion receipt, decision, decision receipt,
  and memory-history writes are wrapped in a recoverable manifest under the
  per-vault writer lock. The manifest records `stage` (`prepared` → `committed`),
  touched artifacts with preimage/postimage digests, and preimage backups.
- **Deterministic recovery (`recover()`)**: runs once per process on first
  `lock()`. All-post → `committed` (cleanup); all-pre → `rolled_back`; mixed →
  `_rollback_tx` → `reconciled_rollback`; corrupt manifest → `fail_closed` +
  cleanup. No duplicate event/receipt is ever produced for a `committed` intent.
- **Fault-injection harness** (`power_framework.core.fault_injection`): opt-in,
  inert by default. Tests arm named crash points (`task.create`,
  `task.transition`, `task.migrate`, `decision.create`, `decision.resolve`,
  `memory.apply`) to deterministically reproduce the hard-kill scenarios.
- **Reversible v1 → v2 migration**: `migrate_v1_work_packets` writes a content-free
  manifest, retains original v1 bytes in `.power/migration/v1-backup/`, is
  idempotent and interrupt-safe, and ships `rollback_v1_migration()`.
- **Observability**: `recover()` appends redacted recovery records to
  `.power/tasks/recovery.log`.
- **GUI idempotency wiring** (ai-second-brain-gui): routes now derive a stable
  `idempotency_key` per logical action (`clients/idempotency.py`) and forward it
  via `RequestContext`, so a double-clicked form reuses the same key and the core
  replays the prior result instead of erroring.

## Atomic vs crash-consistent (terminology)

- **Atomic single-file write** (pre-3.6.4 guarantee): each artifact is replaced
  via temp-file + rename, with exception-time rollback *inside* one `with lock()`.
  A hard kill *between* artifacts still left a hybrid state with no reconciliation
  path.
- **Crash-consistent multi-artifact transaction** (3.6.4 guarantee): the manifest
  makes the whole operation recoverable across a hard kill. This is the bar the
  3.6.4 durability prompt required.

## Evidence boundary

Linux remains the supported release platform for `v3.6.4`. The durability contract
is verified by the focused crash-recovery, migration, and fault-injection test
suites (Task/Decision/Memory/Proposals). The GUI idempotency wiring is verified by
static/import smoke checks and redeployed against the live POWER-GUI server on
LXC200; the full GUI e2e contract suite requires that server.

A complete previous-runtime upgrade certification (running an installed older
binary) is not claimed by this release. macOS and Windows remain outside the
supported release boundary.

## Release gates

```bash
uv sync --locked --group dev --extra semantic --extra rerank --extra gpu
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/power_framework
uv run pytest
uv run mkdocs build --strict
```

The tag workflow additionally requires a clean signed `v3.6.4` tag, verifies the
version-bound release contract and upgrade aggregate, builds the wheel and source
archive, emits the SPDX SBOM and release receipt, and publishes this file as the
GitHub Release body.
