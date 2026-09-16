# POWER 3.8 — INFRA-1 Governance Contract Reconciliation Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-15T09:06:37Z
PACKET: 05-infra1-governance-reconciliation
REPOSITORY: https://github.com/weby-homelab/power-framework
ACTIVE_GATE: INFRA-1 Governance Reconciliation
CANONICAL_BRANCH: docs/power-3.8-infra1-governance-reconciliation
BASE_SHA: bfb968846c0fc41582c2367782a28540498715b4
BASE_TREE: 70dbfd0f9c980672a757be601b72b138e4e3d744
TARGET_PR: #420
```

---

## 1. Original Contradiction

INFRA-1 implementation was merged and verified on live `main`:
- PR: #419
- MERGE_SHA: `bfb968846c0fc41582c2367782a28540498715b4`
- MERGE_TREE: `70dbfd0f9c980672a757be601b72b138e4e3d744`
- Closure comment: `5671031312` explicitly stating:
  ```text
  REAL_RECEIVER_DEPLOYMENT:
  OPERATOR FOLLOW-UP / NOT FRAMEWORK MERGE BLOCKER
  ```

However, `artifacts/project-state/planning/phase5-9-acceptance-gates.md` still stated:
- INFRA-1 requires operator evidence for actual receiver account, forced `rrsync`, source/destination permissions, and real replicate exercise against PRXMX.
- Missing real receiver evidence was classified as `FAIL / BLOCKED`.

These two statements could not both be canonical.

---

## 2. Why the Contradiction Existed

Earlier planning draft language conflated:
1. Framework-level architectural capability and security contracts (broker peer credentials, argv restriction, receiver lockdown scripts, hermetic tests).
2. Host-specific physical deployment validation on a single homelab host (`PRXMX-01`).

This accidentally promoted a host-specific deployment fact into a mandatory framework merge invariant.

---

## 3. Architectural Decision: Host Deployment != Framework Invariant

Binding architectural invariant:

```text
HOST-SPECIFIC DEPLOYMENT FACT != FRAMEWORK INVARIANT
```

The generic POWER Framework cannot depend on the availability, credentials, IP addresses, or private keys of one specific homelab host (`PRXMX-01`).

The framework gate proves:
- Typed request/response/receipt models and strict AF_UNIX peer-principal boundary.
- Hardened reference receiver configuration (`power-receiver.authorized_keys`, `sshd_config.d/power-receiver.conf`).
- Forced `rrsync` contract with directory restriction (`-ro` / `-wo`) and `restrict` directive.
- Non-root receiver model with destination containment.
- Fixed SSH/rsync argv execution model with no remote deletion by default.
- Pinned host-key identity model with no password/agent/private-key fallback.
- Secret-free client/agent boundary where credentials never enter agent context.
- Full hermetic and adversarial test coverage.
- Diagnostic CLI tooling (`receiver-check`, `status`).

Real receiver deployment validation is an **operator deployment validation follow-up**. It is recommended/required for a specific production rollout, but does not block generic framework phase advancement.

---

## 4. Security Requirements Retained (Zero Weakening)

Zero security controls were removed or weakened:
- `DIRECT_AGENT_SSH = DENIED`
- `ARBITRARY_REMOTE_SHELL = DENIED`
- `PASSWORD_AUTH_FALLBACK = DENIED`
- `PRIVATE_KEY_AGENT_ACCESS = DENIED`
- `SHELL_TRUE = ABSENT`
- `UNSAFE_SOURCE_RUNNER_CALLS = 0`
- `EFFECTFUL_OPERATION_WITHOUT_DURABLE_STATE_CANNOT_RETURN_SUCCESS = TRUE`
- `TASKSTORE_RECOVERY_BLOCKED_REMAINS_FAIL_CLOSED = TRUE`
- `PROJECT_LEDGER_GT_10MB_REPLAY_VALID = TRUE`
- `SPECIAL_FILE_FIFO_REJECTION_NON_BLOCKING = TRUE`

This reconciliation is NOT: "tests failed, therefore lower the bar." All 11 required status checks passed, all hermetic and security tests passed, and post-merge CI/Docs/CodeQL passed on `main`. The correction strictly clarifies the boundary between framework capability and operator deployment.

---

## 5. Files Changed

1. `artifacts/project-state/planning/phase5-9-acceptance-gates.md`:
   - Separated required framework evidence from operator deployment validation.
   - Removed single-host blocker requirement from framework PASS/FAIL conditions.
   - Recorded closure evidence for INFRA-1 (PR #419, commit `bfb968846c0fc41582c2367782a28540498715b4`, comment `5671031312`).
   - Added explicit rationale for non-retroactive gate weakening.

2. `docs/plans/POWER_3.8_CURRENT_STATE.md`:
   - Updated header and status: `PHASE_5B: CLOSED / MERGED / VERIFIED`, `INFRA_1: CLOSED / MERGED / VERIFIED`, `LAST_CLOSED_GATE: INFRA-1`, `PHASE_5C: READY FOR SEPARATE ADMISSION / NOT STARTED`.
   - Reconciled INFRA-1 merged evidence and architectural decision.

3. `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`:
   - Updated execution sequence and status table to reflect INFRA-1 closed/merged and Phase 5C ready but unstarted.
   - Reconciled INFRA-1 section with governance decision.

4. `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`:
   - Updated status block and evidence boundary to reflect merged INFRA-1 and operator follow-up classification.

5. `docs/api/infra_broker.md`:
   - Updated status header from provisional candidate to `CLOSED / MERGED / VERIFIED (PR #419)`.

6. `artifacts/project-state/planning/README.md`:
   - Updated section to reflect closed INFRA-1 gate and operator deployment follow-up classification.

7. `artifacts/project-state/handoffs/2026-09-15T090637Z_infra1_governance_reconciliation.md`:
   - Durable handoff recording this reconciliation packet.

---

## 6. Candidate & Merge Tuples

- **Base SHA:** `bfb968846c0fc41582c2367782a28540498715b4`
- **Base Tree:** `70dbfd0f9c980672a757be601b72b138e4e3d744`
- **Candidate Head SHA:** `8b96eba1dfcadd94e501f7fa5d4a420321dc3c4c`
- **Candidate Tree:** `738d7342da65a25ec5666e68fbe19c6543ac0e94`
- **Candidate Parent:** `bfb968846c0fc41582c2367782a28540498715b4`
- **PR:** #420
- **Merge SHA:** `5e65efa59288cd84aac3d416e4611e19d23ea7b7`
- **Merge Tree:** `738d7342da65a25ec5666e68fbe19c6543ac0e94`
- **Merge Parents:** `bfb968846c0fc41582c2367782a28540498715b4`, `8b96eba1dfcadd94e501f7fa5d4a420321dc3c4c`

---

## 7. Final State

- `INFRA_1`: CLOSED / MERGED / VERIFIED
- `INFRA_1_DEPLOYMENT_VALIDATION`: SEPARATE OPERATOR FOLLOW-UP
- `PHASE_5C`: READY FOR SEPARATE ADMISSION / NOT STARTED
- `POWER_3_8_0`: NO-GO

---

## 8. Next Packet

`06-phase5c-preflight-contract-freeze`
- Inventory candidate-generation paths.
- Map SearchScope dimensions.
- Define pushdown semantics.
- Define baseline and metrics.
- Freeze implementation contract.
- NO Phase 5C runtime implementation in that packet.
