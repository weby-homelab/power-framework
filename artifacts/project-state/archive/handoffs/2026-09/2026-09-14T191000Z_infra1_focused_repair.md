# POWER 3.8 — INFRA-1 Focused Repair Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-14T19:10:00Z
PACKET: 02-infra1-implementation-completion
REPOSITORY: https://github.com/weby-homelab/power-framework
ACTIVE_GATE: INFRA-1 — Constrained Local Infrastructure Execution Broker
CANONICAL_BRANCH: feat/power-3.8-infra-execution-broker
PREVIOUS_HEAD_SHA: dbb7d0b3b6bb627282f25bc86dca6d069e4064fe
PREVIOUS_TREE_SHA: 700e7e20a299db2e3fd1509344158926bd44d32c
```

---

## 1. Starting Head & Baseline

- **Starting Head:** `dbb7d0b3b6bb627282f25bc86dca6d069e4064fe`
- **Starting Tree:** `700e7e20a299db2e3fd1509344158926bd44d32c`
- **Parent Commit:** `742d0fb431d78fde5d698ae1aa55589ef0e75c1b`
- **Active Branch:** `feat/power-3.8-infra-execution-broker`
- **Target PR:** #419

---

## 2. Root Cause Analysis

### Exact Exception Path
1. In `tests/test_infra_broker.py::test_source_symlink_is_blocked_before_runner`, `InfraBrokerServer` was instantiated without an explicit `state_dir`, defaulting to `DEFAULT_STATE_DIR = Path("/var/lib/power-infra")`.
2. In non-root execution environments (such as GitHub Actions runner `uid=1001`), `_ensure_state_capacity()` attempted to create `/var/lib/power-infra`, raising `PermissionError` (Errno 13, subclass of `OSError`).
3. `_process_request` caught `OSError` at lines 1369-1376 and mapped it to `MISSING_EXECUTION_CAPABILITY` with `broker_status="broker-state-unavailable"`.
4. Then `_persist_receipt_or_degrade` ran:
   - `self._record_receipt(response)` failed due to `/var/lib/power-infra` being unwritable, catching `OSError` at line 5411 and logging `WARNING power_framework.core.infra_broker:infra_broker.py:5412 INFRA-1 receipt persistence unavailable` (Warning attempt 1).
   - `_persist_receipt_or_degrade` constructed `degraded = _block_response(..., MISSING_EXECUTION_CAPABILITY, broker_status="receipt-state-unavailable")`.
   - `self._record_receipt(degraded)` was called in line 5399 as an accidental duplicate fallback, which failed again and logged the second warning: `INFRA-1 receipt persistence unavailable` (Warning attempt 2).
   - The method returned `degraded` with reason code `MISSING_EXECUTION_CAPABILITY`.
5. The test asserted `response.receipt.reason_code == "RESOURCE_LIMIT"`, which failed with:
   `AssertionError: assert <InfraReasonCode.MISSING_EXECUTION_CAPABILITY: 'MISSING_EXECUTION_CAPABILITY'> == 'RESOURCE_LIMIT'`.

### Why Local Environment (Python 3.13) Differed from Remote CI (Python 3.14)
- On the local host (PRXMX-01), the environment runs as `root` (`uid=0`), where `/var/lib/power-infra` existed and was fully writable by root. Thus `_ensure_state_capacity()` succeeded, `_snapshot_source_root()` detected the symlink and raised `RESOURCE_LIMIT`, and `_record_receipt()` succeeded.
- On GitHub Actions CI, tests run as unprivileged user `runner` (`uid=1001`), where `/var/lib/power-infra` is not writable.
- In GitHub Actions CI matrix, `test (3.14)` executed before `test (3.13)`. When `test (3.14)` failed on this test, `fail-fast: true` cancelled `test (3.13)`. The difference was environmental/permission-based, not an incompatibility in Python 3.14 itself.

---

## 3. Failure-Precedence Rule

The canonical rule is enforced in `_persist_receipt_or_degrade`:

```text
PRIMARY OPERATION / SECURITY FAILURE > SECONDARY AUDIT-PERSISTENCE FAILURE
```

When an operation was blocked before becoming externally effectful (Case A):
- `response.status is InfraResponseStatus.BLOCKED and not is_committed_operation`:
  The primary operational/security failure reason (e.g. `RESOURCE_LIMIT`, `POLICY_INVALID`, `PATH_TRAVERSAL`, `APPROVAL_REQUIRED`) is strictly preserved.
- Secondary receipt-persistence failure logs boundedly via `_record_receipt`, but does NOT overwrite the primary reason with `MISSING_EXECUTION_CAPABILITY`.
- Accidental duplicate fallback persistence (`self._record_receipt(degraded)`) has been eliminated.

When an operation reported success or committed state, but durable receipt cannot be persisted (Case B):
- Replicate runs degrade to `UNKNOWN_COMPLETION` (fail-closed, never reporting clean success without durable receipt).
- Non-effectful successful operations degrade to `MISSING_EXECUTION_CAPABILITY`.
- In both cases, redundant duplicate persistence attempts are eliminated.

---

## 4. CodeRabbit Finding Disposition

- **Finding:** `tests/test_infra_broker_hardening.py:1824` referenced `deploy/systemd/` assets relative to current working directory (`Path("deploy/systemd/...")`), causing potential `FileNotFoundError` if pytest is invoked from a different directory.
- **Validation:** Confirmed valid.
- **Repair:** Defined `_REPO_ROOT = Path(__file__).resolve().parents[1]` and updated asset reads to `_REPO_ROOT / "deploy" / "systemd"`.
- **Regression Proof:** Added `monkeypatch.chdir(tmp_path)` to `test_broker_entrypoint_and_systemd_boundary_are_non_root` to prove deterministic resolution when CWD is not repository root.

---

## 5. Files Changed

1. `src/power_framework/core/infra_broker.py`:
   - Updated `_persist_receipt_or_degrade` to preserve primary blocked responses upon receipt persistence failure (Case A) and removed duplicate fallback write attempt.
2. `tests/test_infra_broker.py`:
   - Added `"max_bytes": 100_000` to `_write_test_profile` to prevent snapshot disk capacity ceilings in low-disk test runners.
   - Added `state_dir=tmp_path / "state"` to `test_source_symlink_is_blocked_before_runner`.
   - Added new regression test `test_unsafe_source_symlink_preserves_primary_rejection_when_receipt_persistence_fails` verifying primary rejection preservation under forced persistence failure, runner calls = 0, no SSH/rsync execution, single persistence attempt, and no credential exposure.
3. `tests/test_infra_broker_hardening.py`:
   - Defined `_REPO_ROOT` anchored to repository root.
   - Resolved `deploy/systemd/` asset paths from `_REPO_ROOT` and verified CWD independence via `monkeypatch.chdir(tmp_path)`.
4. `artifacts/project-state/handoffs/2026-09-14T191000Z_infra1_focused_repair.md`:
   - Durable handoff for Work Packet 02.

---

## 6. Focused Validation Results

- **`tests/test_infra_broker.py`:** 19/19 passed
- **`tests/test_infra_broker_hardening.py`:** 61/61 passed
- **`tests/test_infra_assets.py`:** 4/4 passed
- **Total Focused INFRA-1 Suite:** 84/84 passed (6.37s)
- **`ruff check`:** All checks passed
- **`ruff format --check`:** All files formatted cleanly
- **`mypy src/power_framework/core/infra_broker.py`:** Success (no issues found)
- **`./verify.sh`:** Completed successfully (syntax, secrets, branch inspection passed)

---

## 7. Security Invariants Confirmed

- `DIRECT_AGENT_SSH = DENIED`
- `ARBITRARY_REMOTE_SHELL = DENIED`
- `PASSWORD_AUTH_FALLBACK = DENIED`
- `PRIVATE_KEY_AGENT_ACCESS = DENIED`
- `SHELL_TRUE = ABSENT`
- `UNSAFE_SOURCE_RUNNER_CALLS = 0`
- `PRIMARY_SECURITY_FAILURE_NOT_MASKED = TRUE`
- `EFFECTFUL_OPERATION_WITHOUT_DURABLE_STATE_CANNOT_RETURN_SUCCESS = TRUE`

---

## 8. Remaining Work

- **Work Packet 03:** Exact-head admission on PR #419 across all 11 required GitHub Actions checks.
- **Phase 5C:** NOT STARTED.
- **Power 3.8.0 Release:** NO-GO until exact-head admission and subsequent milestone phases complete.
