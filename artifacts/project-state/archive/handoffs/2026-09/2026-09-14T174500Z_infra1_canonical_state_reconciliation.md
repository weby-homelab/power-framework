# POWER 3.8 — INFRA-1 Canonical State Reconciliation Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-14T17:45:00Z
PACKET: 01-canonical-state-reconciliation
REPOSITORY: https://github.com/weby-homelab/power-framework
ACTIVE_GATE: INFRA-1 — Constrained Local Infrastructure Execution Broker
CANONICAL_BRANCH: feat/power-3.8-infra-execution-broker
CANONICAL_HEAD_SHA: dbb7d0b3b6bb627282f25bc86dca6d069e4064fe
CANONICAL_HEAD_TREE: 700e7e20a299db2e3fd1509344158926bd44d32c
```

---

## 1. Live Main

- **Commit SHA:** `6a315d5919eeef797bc506ecb216313c20419fc2`
- **Tree SHA:** `a03b90648e1e57c5a579e5834988015192027cb0`
- **Parents:**
  - `dde1e1369c2d79d8f01b9fce21ae1fb55834a814` (Phase 5A.1 main)
  - `887f8319b70c4e7be98d503d53924a70ad211c38` (PR #418 candidate head)
- **Commit Message:** `Merge Phase 5B Domain Policy v2 and deterministic router`
- **GPG Verification:** `verified=true` / `reason=valid` (GitHub Web-Flow signature)
- **Branch Protection:**
  - `protected: true`
  - `enforce_admins: true`
  - `allow_force_pushes: false`
  - `allow_deletions: false`
  - `required_signatures: true`
- **Strict Required Status Checks (11 contexts):**
  - `test (3.13)`
  - `test (3.14)`
  - `security`
  - `package-smoke`
  - `upgrade-matrix (ubuntu-latest)`
  - `upgrade-matrix-aggregate`
  - `base-runtime-smoke`
  - `benchmark-integrity`
  - `analyze (python)`
  - `CodeQL`
  - `build`

---

## 2. PR #419 Checkpoint

- **PR URL:** https://github.com/weby-homelab/power-framework/pull/419
- **State:** `open`
- **Merged:** `false`
- **Target Base:** `main` (`6a315d5919eeef797bc506ecb216313c20419fc2`)
- **Head Branch:** `feat/power-3.8-infra-execution-broker`
- **Head SHA:** `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe`
- **Head Tree:** `700e7e20a299db2e3fd1509344158926bd44d32c`
- **Head Parent:** `742d0fb431d78fde5d698ae1aa55589ef0e75c1b`
- **Total Commits on PR:** 5 commits
  1. `dcf27b55e3e5bfeb285fc93ed73a485ce0f707fb` (`verified=true`)
  2. `62323a930189c7afea497a984bdf6858011dfa09` (`verified=true`) — CPU-only agent checkpoint
  3. `4dc2db46885ab81e337f398f16ea6a7aac585839` (`verified=true`) — WS hardening commit
  4. `742d0fb431d78fde5d698ae1aa55589ef0e75c1b` (`verified=true`) — WS state reconciliation
  5. `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe` (`verified=true`) — WS CI result record
- **GPG Verification:** All 5 commits are GPG-verified (`verified=true`, `reason=valid`).
- **Review Threads:**
  - CodeRabbit review on `tests/test_infra_broker_hardening.py:1824` recommending repo-root resolution for `deploy/systemd/` assets.
- **Remote CI Run Status (Run ID: 34872312420 on `dbb7d0b`):**
  - `CodeQL`: success
  - `upgrade-matrix-aggregate`: success
  - `analyze (python)`: success
  - `security`: success
  - `build`: success
  - `benchmark-integrity`: success
  - `base-runtime-smoke`: success
  - `package-smoke`: success
  - `upgrade-matrix (ubuntu-latest)`: success
  - `test (3.13)`: cancelled (fail-fast triggered by 3.14 failure)
  - `test (3.14)`: failure (`tests/test_infra_broker.py::test_source_symlink_is_blocked_before_runner`)
  - `deploy`: skipped

---

## 3. WS Continuation State

- **Published Head:** `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe`
- **Published Tree:** `700e7e20a299db2e3fd1509344158926bd44d32c`
- **WS Origin Push Status:** Completed prior to WS shutdown (WS node last seen 38m ago).
- **Local PRXMX-01 Working Tree:** Fast-forwarded to `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe`.
- **Uncommitted Implementation Work:** None (`git status` was clean; zero uncommitted diff lines).

---

## 4. Ancestry & Divergence Analysis

```text
6a315d5 (origin/main)
   │
   ▼
dcf27b5 (feat: add constrained infrastructure execution broker)
   │
   ▼
62323a9 (CPU Checkpoint: docs: record INFRA-1 transfer epoch)
   │
   ▼
4dc2db4 (WS Continuation: feat: harden INFRA-1 broker and governance evidence)
   │
   ▼
742d0fb (WS Continuation: docs: reconcile INFRA-1 candidate state)
   │
   ▼
dbb7d0b (WS Continuation: docs: record INFRA-1 remote CI result) [PR #419 HEAD / CANONICAL]
```

- **Merge Base (main, dbb7d0b):** `6a315d5919eeef797bc506ecb216313c20419fc2`
- **Merge Base (CPU 62323a9, WS dbb7d0b):** `62323a930189c7afea497a984bdf6858011dfa09`
- **Rev-list count (62323a9...dbb7d0b):** `0 3` (strictly linear descendant, 0 divergence).
- **Diff Stat (62323a9..dbb7d0b):** 56 files changed, 10867 insertions(+), 1541 deletions(-).
- **Divergence Classification:** Case A (WS continuation is a strict linear descendant of the CPU checkpoint; no branch fork or divergence).

---

## 5. Surviving INFRA-1 Implementation Matrix

| Requirement | Status | Evidence |
| :--- | :--- | :--- |
| Typed request/response contracts | COMPLETE | `InfraRequest`, `InfraResponse`, `InfraOperation`, `InfraReceipt` in `infra_models.py` |
| Local broker boundary | COMPLETE | `InfraBrokerServer` and `InfraBrokerClient` in `infra_broker.py` |
| Unix socket transport | COMPLETE | Framed AF_UNIX socket protocol (`/run/power-infra/broker.sock`) |
| SO_PEERCRED-derived principal | COMPLETE | `_peer_identity` via `socket.SO_PEERCRED`, verified against allowed UIDs |
| Operator-owned profile/policy | COMPLETE | Schema in `infra_models.py`, loaded from `/etc/power/infra/profiles.d` |
| Strict host key verification | COMPLETE | Fixed `StrictHostKeyChecking=yes`, `UserKnownHostsFile` binding |
| Fixed SSH/rsync templates | COMPLETE | Pinned binaries (`/usr/bin/ssh`, `/usr/bin/rsync`), no shell execution |
| No arbitrary command surface | COMPLETE | Closed operation enum: STATUS, PROBE, RSYNC_DRY_RUN, REPLICATE, VERIFY |
| No direct SSH fallback | COMPLETE | Fail-closed if broker unavailable; direct SSH categorically denied |
| Credential isolation | COMPLETE | Keys stored in operator directory; never exposed to context/agent |
| Dry-run gate | COMPLETE | Policy enforces dry-run requirement and receipt validation before replication |
| Replication idempotency | COMPLETE | Content hash + receipt derivation prevents duplicate replication runs |
| Crash/restart replay semantics | COMPLETE | In-flight tracking and persisted receipt reload across broker restarts |
| Receipt persistence | COMPLETE | State directory stores immutable JSON receipts with fsync |
| Failure reason preservation | COMPLETE | Typed `InfraReasonCode` preserves fine-grained diagnostic reasons |
| Resource limits | COMPLETE | Strict bounds on frame bytes, policy bytes, receipt bytes, concurrent conns |
| Timeout handling | COMPLETE | Explicit connect, frame I/O, and subprocess execution timeouts |
| Source snapshot semantics | COMPLETE | Source tree snapshotting and manifest generation before replication |
| Symlink/path safety | COMPLETE | Traversal prevention, escaping symlink rejection, path bounds |
| Task capability semantics | COMPLETE | Integrated with `ApplicationService` and `task_service.py` capabilities |
| CLI adapter | COMPLETE | `power infra {status,probe,dry-run,replicate,verify}` in `cli.py` |
| MCP adapter | COMPLETE | `infra_action` tool registered in `power_server.py` |
| systemd unit/profile | COMPLETE | `.service`, `.socket`, `.tmpfiles`, allowlist conf in `deploy/systemd/` |
| Security documentation | COMPLETE | `SECURITY.md`, `docs/threat-model.md`, `deploy/infra/receiver.md` |
| ADR/API documentation | COMPLETE | `docs/adr/0006-infra-1-constrained-execution-broker.md`, `docs/api/infra_broker.md` |
| Tests | PARTIAL | 2011 tests pass locally & remotely; 1 unit test failure in Python 3.14 CI |

---

## 6. Python 3.14 Failure Status

- **Failing Test:** `tests/test_infra_broker.py::test_source_symlink_is_blocked_before_runner`
- **Failure Detail:**
  ```text
  AssertionError: assert <InfraReasonCode.MISSING_EXECUTION_CAPABILITY: 'MISSING_EXECUTION_CAPABILITY'> == 'RESOURCE_LIMIT'
  - RESOURCE_LIMIT
  + MISSING_EXECUTION_CAPABILITY
  ```
- **Classification:** **`STILL PRESENT`**
- **Analysis:**
  On Python 3.13 local runtime, the test passes. On Python 3.14 remote CI (job 104070955310, run 34872312420), `server.handle_request()` returns `MISSING_EXECUTION_CAPABILITY` instead of `RESOURCE_LIMIT`. This is caused by an `OSError`/`ValueError` caught in `handle_request` lines 1369-1376 mapping to `MISSING_EXECUTION_CAPABILITY`. The exact reason must be resolved in Work Packet 02.

---

## 7. Canonical Continuation Decision

- **CANONICAL_CONTINUATION_HEAD:** `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe`
- **CANONICAL_CONTINUATION_TREE:** `700e7e20a299db2e3fd1509344158926bd44d32c`
- **CANONICAL_BRANCH:** `feat/power-3.8-infra-execution-broker`
- **Justification:**
  1. `dbb7d0b` is a verified direct linear descendant of both `main` (`6a315d5`) and the initial CPU checkpoint (`62323a9`).
  2. It includes the complete implementation of the broker, models, systemd assets, docs, and 1845 lines of hardening tests.
  3. Passes 2011/2012 hermetic tests, CodeQL, security audit, and packaging smoke checks.
  4. Contains no branch divergence or merge conflict.

---

## 8. PR #419 Disposition

- **Classification:** **`CANONICAL CONTINUATION PR`**
- **Action for Packet 02:**
  Keep PR #419 open. Work Packet 02 will address the single failing test under Python 3.14 and CodeRabbit asset path resolution, then push the resulting commit to `feat/power-3.8-infra-execution-broker`. This will refresh PR #419 to achieve all 11 required green checks for protected admission.

---

## 9. Next Packet Scope & Invariants

### Files that Next Packet MAY Modify:
- `tests/test_infra_broker.py` (address `test_source_symlink_is_blocked_before_runner` error mapping/assertion)
- `src/power_framework/core/infra_broker.py` (ensure consistent reason code return under Python 3.14)
- `tests/test_infra_broker_hardening.py` (CodeRabbit review recommendation: repository-root relative paths)
- `docs/plans/POWER_3.8_CURRENT_STATE.md` (record post-fix candidate epoch)
- `artifacts/project-state/handoffs/` (append-only Packet 02 handoff)

### Files Next Packet MUST NOT Modify:
- Any Phase 5C files (`searcher.py`, `semantic_compiler.py`, etc.)
- `pyproject.toml` dependency versions
- `uv.lock`
- `.github/workflows/*`
- Version/release numbers (remain at 3.7.11)
- Receiver deployment infrastructure

### Exact Next Objective:
Execute **Work Packet 02**: resolve the Python 3.14 `test_source_symlink_is_blocked_before_runner` mismatch and CodeRabbit path resolution, verify local gates, and produce the clean candidate commit for PR #419.
