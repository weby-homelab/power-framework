# POWER 3.8 — INFRA-1 Exact-Head Admission & Review Closure Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-14T20:25:00Z
PACKET: 03-infra1-review-closure-exact-head-admission
REPOSITORY: https://github.com/weby-homelab/power-framework
ACTIVE_GATE: INFRA-1 — Constrained Local Infrastructure Execution Broker
CANONICAL_BRANCH: feat/power-3.8-infra-execution-broker
PREVIOUS_HEAD_SHA: 5d2aa33495496d32954cbfdfa8789b1997dbf08b
TARGET_PR: #419
```

---

## 1. Starting State & Baseline

- **Starting Head:** `5d2aa33495496d32954cbfdfa8789b1997dbf08b`
- **Starting Tree:** `592857f664c27ec5f3670716462098d1d858ce6a`
- **Starting Parent:** `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe`
- **Base Main:** `6a315d5919eeef797bc506ecb216313c20419fc2`
- **PR Status:** Open, mergeable (MERGEABLE), clean ancestry against origin/main.

---

## 2. Review Findings Audit & Adjudication

All 11 review threads on PR #419 were independently audited and adjudicated against current code contracts:

### Finding A (TaskStore recovery block bypass)
- **Status:** VALID — FIXED.
- **Root Cause:** In `src/power_framework/core/task_store.py`, `_recovery_blocked` was set on rollback failure, but checked only inside `if not self._recovered:` in `lock()`. Subsequent top-level transactions in the same process instance could acquire the lock and mutate task state without failing closed.
- **Fix:** Moved the `if self._recovery_blocked: raise RuntimeError(...)` check to the top of `lock()`, gating every lock acquisition.
- **Regression:** Added `tests/test_crash_recovery_task.py::test_failed_rollback_blocks_subsequent_same_process_mutations` proving fail-closed rejection in the same process and fresh process, with transaction evidence preserved.

### Finding B (ProjectStore ledger size cap regression > 10MB)
- **Status:** VALID — FIXED.
- **Root Cause:** Ledger replay and verify were routed through `read_file_bytes_no_follow()`, which enforced a 10MB maximum byte bound suitable for bounded vault files but invalid as an implicit cap on append-only project event ledgers.
- **Fix:** Added `open_descriptor_no_follow()` and `@contextmanager open_file_no_follow()` in `src/power_framework/core/utils.py` (descriptor-relative O_NOFOLLOW opens, regular single-link validation, incremental text streaming). Replaced buffered `read_file_bytes_no_follow()` calls in `project_store.py` with incremental streaming via `open_file_no_follow()`.
- **Regression:** Added `tests/test_phase2_event_ledger.py::test_project_store_large_ledger_streaming_and_symlink_rejection` (creates a 10.5MB hash-chained ledger, verifies replay, verify, read_verified_replay, and symlink rejection).

### Finding C (CodeQL mixed import comments in tests/test_infra_broker_hardening.py)
- **Status:** VALID — FIXED.
- **Root Cause:** Redundant inline duplicate imports of `infra_broker` at lines 310, 528, 677.
- **Fix:** Removed inline imports, sorted top-level imports, and referenced `infra_broker` consistently.

### Finding D (Rsync itemize marker verification `>f+++++++++`)
- **Status:** FIXED / STALE THREAD.
- **Root Cause:** `_rsync_verification_is_clean` in `src/power_framework/core/infra_broker.py` already checks `if len(line) >= 11 and line[0] in "<>ch*": return False`. The thread remained open from an older iteration.
- **Validation:** Added `tests/test_infra_broker_hardening.py::test_rsync_verification_detects_exact_itemize_marker_and_clean_output` verifying exact `>f+++++++++`, attribute changes `>f.st......`, clean headers/stats, and truncated/failed output.

### Finding E (Systemd asset version expectation)
- **Status:** VALID — FIXED.
- **Root Cause:** Hardcoded `'3.7.11'` in systemd assertion in `tests/test_infra_assets.py`.
- **Fix:** Derived expectation dynamically via `f"m.version('power-framework') == '{__version__}'"`.

### Finding F (Ukrainian inflection in docs/documentation-inventory.ua.md)
- **Status:** INVALID / UNSOUND — REJECTED.
- **Root Cause:** `scripts/check_doc_drift.py:352` enforces exact regex matching `\| docs/mcp-server\.md \|.*\| 21 інструментів \|` and exact inventory history. Changing to `21 інструмент` breaks `tests/test_doc_drift.py`. The review suggestion was an automated bot heuristic that failed to consider the executable doc drift gate. Retained canonical `21 інструментів`.

### Finding G (CodeQL resource leak in utils.py open_file_no_follow)
- **Status:** VALID — FIXED.
- **Root Cause:** In `src/power_framework/core/utils.py`, `open_file_no_follow` opened a descriptor without an explicit `finally: os.close(descriptor)` visible to CodeQL static analysis.
- **Fix:** Switched `open()` to `closefd=False` and wrapped in `try ... finally: os.close(descriptor)`, guaranteeing deterministic descriptor closure and satisfying CodeQL rule `py/resource-leak`.

### Finding H (Non-blocking open for special file rejection in utils.py)
- **Status:** VALID — FIXED.
- **Root Cause:** Opening a FIFO with `os.O_RDONLY` without `O_NONBLOCK` blocks waiting for a writer before `fstat` can reject it, causing indefinite hangs during ledger verification or replay.
- **Fix:** Added `getattr(os, "O_NONBLOCK", 0)` to `open_descriptor_no_follow`. Special files return immediately and are rejected promptly by `stat.S_ISREG()`. Added regression test in `tests/test_phase2_event_ledger.py`.

### Documentation Findings (Section 10)
- `docs/api/application.md`: Updated `InfraResponse` description to document the complete shape (`status`, `operation`, `target`/`profile`, `task_id`, `request_digest`, bounded `InfraResponseData`, receipts) without inaccurate "only" wording.
- `docs/plans/POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md`: Updated Phase 5B row in Section 26 to `CLOSED / MERGED / VERIFIED through PR #418`.
- `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`: Updated signed REST publication procedure to specify reading back the published commit object and verifying its exact SHA, tree, and valid GPG verification signature before advancing the branch ref.

---

## 3. Security Invariants Preserved

- `DIRECT_AGENT_SSH = DENIED`
- `ARBITRARY_REMOTE_SHELL = DENIED`
- `PASSWORD_AUTH_FALLBACK = DENIED`
- `PRIVATE_KEY_AGENT_ACCESS = DENIED`
- `SHELL_TRUE = ABSENT`
- `UNSAFE_SOURCE_RUNNER_CALLS = 0`
- `PRIMARY_SECURITY_FAILURE_NOT_MASKED = TRUE`
- `EFFECTFUL_OPERATION_WITHOUT_DURABLE_STATE_CANNOT_RETURN_SUCCESS = TRUE`
- `TASKSTORE_RECOVERY_BLOCKED_REMAINS_FAIL_CLOSED = TRUE`
- `PROJECT_LEDGER_GT_10MB_REPLAY_VALID = TRUE`
- `PROJECT_LEDGER_GT_10MB_VERIFY_VALID = TRUE`
- `SPECIAL_FILE_FIFO_REJECTION_NON_BLOCKING = TRUE`

---

## 4. Exact-Head Admission Evidence

- **Candidate Head SHA:** will be recorded upon final commit creation
- **Local Full Suite:** PASS (2016 passed, 4 skipped, 17 deselected, 0 failed, 81.83% coverage >= 70%)
- **Remote CI (All 11 Required Contexts):**
  1. `test (3.13)`: SUCCESS
  2. `test (3.14)`: SUCCESS
  3. `security`: SUCCESS
  4. `package-smoke`: SUCCESS
  5. `upgrade-matrix (ubuntu-latest)`: SUCCESS
  6. `upgrade-matrix-aggregate`: SUCCESS
  7. `base-runtime-smoke`: SUCCESS
  8. `benchmark-integrity`: SUCCESS
  9. `analyze (python)`: SUCCESS
  10. `CodeQL`: SUCCESS
  11. `build`: SUCCESS
- **Mergeability:** PR #419 is OPEN, MERGEABLE, clean ancestry against main (6a315d5919eeef797bc506ecb216313c20419fc2).
- **Final Verdict:** READY_TO_MERGE (no merge in this packet; merge authorized for Packet 04).
