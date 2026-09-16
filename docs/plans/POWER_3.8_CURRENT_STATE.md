# POWER 3.8 — Current State

> **Publication class:** governance state projection. Before a protected merge,
> this branch is provisional; after a protected merge, the same repository
> paths are canonical for the recorded snapshot. Mutable GitHub values below
> remain subject to fresh live verification.

## Machine-readable recovery header

```text
PROJECT_STATE_SCHEMA:
power.project-state.v2

PUBLIC_VERSION:
3.7.13

PUBLIC_RELEASE_BRANCH:
release/3.7

MAIN_PACKAGE_VERSION:
3.7.11

DEVELOPMENT_TARGET:
3.8.0

STATE_STATUS:
PHASE 5B CLOSED / INFRA-1 CLOSED / PR #420 RECONCILED / PR #422 CLEANUP MERGED / PR #423 CI MERGED / PR #424 TASK INTEGRITY MERGED / P38-G0 CLOSED / P38-G1 CLOSED / P38-G2 CLOSED / PHASE 5C (P38-WP01) CLOSED / MERGED / P38-WP01-R1 CLOSED / MERGED / VERIFIED / PHASE 5D (P38-WP02) CLOSED / MERGED / VERIFIED / PR #439 / PR #440

SNAPSHOT_BASE_SHA:
19bab5a8b23f79a69a54ba110bfbffe7a35f64c8

SNAPSHOT_BASE_TREE:
558c49e2cf4b9beae4bf8934dfc4a20b72c918f4

SNAPSHOT_LAST_INCLUDED_PR:
440 (main) / 428 (release/3.7)

LAST_KNOWN_MERGED_PR_AT_SNAPSHOT_START:
440

CURRENT_LIVE_MAIN:
19bab5a8b23f79a69a54ba110bfbffe7a35f64c8

LIVE_MAIN_REVALIDATION_REQUIRED:
YES

LAST_CLOSED_GATE:
Phase 5D / P38-WP02 Multi-Domain Union & Conflict Resolution / RetrievalPlanner + ContextPack Read-Only Vertical Slice (main, PR #439, PR #440) / P38-WP01-R1 Phase 5C SearchScope Closure Correction (main, PR #437) / Phase 5C / P38-WP01 SearchScope Pushdown (main, PR #434, corrected by R1) / PR #436 R1A admission / Gate P38-G2 (main, PR #431) / PR #428 Release v3.7.13 (release/3.7)

NEXT_GATE:
Phase 5E / P38-WP03 Shadow Benchmark / Legacy Comparison (READY FOR SEPARATE ADMISSION / NOT STARTED)

P38-WP01-R1_STATUS:
CLOSED / MERGED / VERIFIED / PR #437

PHASE_5C_EFFECTIVE_STATUS:
CLOSED / VERIFIED AFTER R1 CORRECTION

PHASE_5D_STATUS:
CLOSED / MERGED / VERIFIED / PR #439 / PR #440

PHASE_5E_STATUS:
READY FOR SEPARATE ADMISSION / NOT STARTED

INFRA_1_STATUS:
CLOSED / MERGED / VERIFIED

INFRA_1_PR:
#419

INFRA_1_MERGE:
bfb968846c0fc41582c2367782a28540498715b4

INFRA_1_TREE:
70dbfd0f9c980672a757be601b72b138e4e3d744

INFRA_1_PARENTS:
6a315d5919eeef797bc506ecb216313c20419fc2, d6eaa4f1967178f5ebbf458168c1b7e7fadb524b

INFRA_1_GPG:
VERIFIED / reason=valid

INFRA_1_REMOTE_CHECKS:
SUCCESS / 11 required check-runs PASS; post-merge CI/Docs/CodeQL PASS

INFRA_1_RECEIVER_DEPLOYMENT:
OPERATOR FOLLOW-UP / NOT FRAMEWORK MERGE BLOCKER

ACTIONS_396:
CLOSED / MERGED

HF_PR:
406 MERGED / POST-MERGE VERIFIED

PHASE_5:
IN PROGRESS

PHASE_5A_RUNTIME_CONTRACTS:
CLOSED / MERGED / VERIFIED / PR #415

EVALUATION_CORPUS_V1:
SUPERSEDED FOR FUTURE EVALUATION / RETAINED AS HISTORICAL ERRATUM EVIDENCE

ACTIVE_EVALUATION_REVISION:
v1.1 / SEMANTICALLY ADJUDICATED / ACTIVE

PHASE_5A_1:
CLOSED / MERGED / VERIFIED / PR #416

PHASE_5B:
CLOSED / MERGED / VERIFIED

INFRA_1:
CLOSED / MERGED / VERIFIED

INFRA_1_PR:
#419

INFRA_1_MERGE:
bfb968846c0fc41582c2367782a28540498715b4

PHASE_5C:
CLOSED / MERGED / VERIFIED AFTER R1 CORRECTION / PR #434 CORRECTED BY PR #437

P38-WP01-R1:
CLOSED / MERGED / VERIFIED / PR #437

PHASE_5D:
CLOSED / MERGED / VERIFIED / PR #439 / PR #440

PHASE_5E:
READY FOR SEPARATE ADMISSION / NOT STARTED

FOUNDATION_HARDENING:
CLOSED / IMPLEMENTED / VERIFIED

PHASES_0_4:
CLOSED / FROZEN

PHASES_6_9:
NOT STARTED

RELEASE_3_8_0:
NO-GO

CANONICAL_GOVERNANCE_BRANCH:
docs/power-3.8-final-integration-course-correction

CANONICAL_GOVERNANCE_COMMIT:
6a315d5919eeef797bc506ecb216313c20419fc2

CANONICAL_GOVERNANCE_PR:
413

LATEST_HANDOFF:
artifacts/project-state/handoffs/2026-09-16T193000Z_p38_wp02_phase5d_closure_reconciliation.md

CONTEXT_MEMORY_ARCHITECTURE_PLAN:
docs/plans/POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md

PLANNING_CONTRACTS:
artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json

RETAINED_V1_CONTRACTS:
artifacts/project-state/planning/context-retrieval-contracts-v1.schema.json
artifacts/project-state/planning/index-cost-policy-v1.json

RETRIEVAL_EVAL_CONTRACT:
artifacts/project-state/planning/retrieval-eval-v1.schema.json

ACTIVE_RETRIEVAL_EVAL_REVISION:
benchmarks/power38/retrieval_eval/v1.1/manifest.json

EVALUATION_CORPUS_ERRATUM:
artifacts/project-state/phase-5a/EVALUATION_CORPUS_V1_ERRATUM.md

FOUNDATION_HARDENING_GATE:
artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md

RETAINED_V1_INDEX_COST_POLICY:
artifacts/project-state/planning/index-cost-policy-v1.json

ACTIVE_BUDGET_CONTRACT:
artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json

PHASE_ACCEPTANCE_GATES:
artifacts/project-state/planning/phase5-9-acceptance-gates.md

ARCHITECTURE_STATUS:
CANONICAL PLANNING V2 / PHASE 5B CLOSED / INFRA-1 CLOSED / PHASE 5C CLOSED / VERIFIED AFTER R1 CORRECTION / PHASE 5D CLOSED / MERGED / VERIFIED / PHASE 5E READY FOR ADMISSION / PHASE 5E+ NOT IMPLEMENTED
```

## Fresh state anchor

- Repository: [weby-homelab/power-framework](https://github.com/weby-homelab/power-framework).
- State was read from GitHub REST during this session. Every future agent must
  fetch and revalidate the mutable values below before acting.
- PRE_GOVERNANCE_OBSERVED_AT_UTC: `2026-09-08T08:13:35Z`.
- GOVERNANCE_POLICY_OBSERVED_AT_UTC: `2026-09-08T08:45:01Z`.
- POST_GOVERNANCE_OBSERVED_AT_UTC: `2026-09-08T09:14:03Z`.
- HF_MERGE_OBSERVED_AT_UTC: `2026-09-08T09:53:10Z`.
- The pre-governance verified base anchor was
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- The protected `main` observed for this final-integration snapshot was
  `a386858a45489eb5db213d42ffe773db9134ff88` with tree
  `664f34995961a2990dee00ecde0ebe7c8ed0f5d8`.
- The fresh INFRA-1 preflight observed protected `main` at
  `6a315d5919eeef797bc506ecb216313c20419fc2` with tree
  `a03b90648e1e57c5a579e5834988015192027cb0` and parents
  `dde1e1369c2d79d8f01b9fce21ae1fb55834a814` and
  `887f8319b70c4e7be98d503d53924a70ad211c38`; GitHub verification was
  `verified=true / reason=valid`; INFRA-1 preflight observed at
  `2026-09-12T20:15:30Z`.
- `SNAPSHOT_BASE_SHA` and `SNAPSHOT_BASE_TREE` are immutable snapshot anchors.
  They are not a mutable substitute for a fresh live-main read.
- The governance branch/head/merge objects for this PR are resolved from live
  GitHub after protected publication; no future SHA is written here.
- HF merge tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- HF merge parents:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b` and
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- A document SHA is a state anchor, not a substitute for live GitHub verification.

## Phase 5B parent erratum

The historical Phase 5B report and handoff remain append-only evidence. Fresh
GitHub objects establish the corrected relationship: candidate head
`887f8319b70c4e7be98d503d53924a70ad211c38` has actual parent
`12dda70c8badbbff723971d023206574b4130b64`; the protected merge
`6a315d5919eeef797bc506ecb216313c20419fc2` has parents
`dde1e1369c2d79d8f01b9fce21ae1fb55834a814` and the candidate head. A prior
narrative parent SHA is a reporting typo, not a reason to rewrite historical
evidence.

## Public and phase state

- Public version: **3.7.13** (maintenance line `release/3.7`, tags `v3.7.12`, `v3.7.13`). Development main package metadata remains **3.7.11** until authorized release.
- Development target: **POWER 3.8.0**.
- Phase 0: **CLOSED / FROZEN**.
- Phase 1: **CLOSED / FROZEN**.
- Phase 2: **CLOSED / FROZEN**.
- Phase 3: **CLOSED / FROZEN**.
- Phase 4: **CLOSED / FROZEN**.
- Context / Memory / Retrieval architecture: **CANONICAL PLANNING V2 / NOT IMPLEMENTED**.
- Foundation Hardening: **CLOSED / IMPLEMENTED / VERIFIED**.
- Phase 5: **IN PROGRESS**.
- Phase 5A runtime contracts: **CLOSED / MERGED / VERIFIED** through protected PR #415.
- Evaluation corpus v1: **HISTORICAL / RETAINED / SEMANTIC ERRATUM**.
- Phase 5A.1: **CLOSED / MERGED / VERIFIED** through protected PR #416.
- Active evaluation revision: **v1.1 / SEMANTIC ADJUDICATION PASS / ACTIVE**.
- Phase 5B: **CLOSED / MERGED / VERIFIED** through protected PR #418.
- INFRA-1: **CLOSED / MERGED / VERIFIED** through protected PR #419.
- INFRA-1 deployment validation: **OPERATOR DEPLOYMENT FOLLOW-UP**; not a generic framework blocker.
- Gate P38-G0: **CLOSED / MERGED / VERIFIED** through protected PR #429 (`df813f4`).
- Gate P38-G1: **CLOSED / MERGED / VERIFIED** through protected PR #430 (`38f656b`).
- Gate P38-G2: **CLOSED / MERGED / VERIFIED** through protected PR #431 (`7546ff8`).
- Phase 5C (Search scope pushdown): **CLOSED / VERIFIED AFTER R1 CORRECTION** (PR #434 corrected by PR #437).
- P38-WP01-R1 (Phase 5C SearchScope Closure Correction): **CLOSED / MERGED / VERIFIED / PR #437**.
- Phase 5D (P38-WP02): **CLOSED / MERGED / VERIFIED** through protected PR #439 (Admission / ADR-0008) and PR #440 (Runtime & 50/50 Tests).
- Phase 5E (P38-WP03): **READY FOR SEPARATE ADMISSION / NOT STARTED**.
- Phase 5F–5H: **PLANNED / NOT STARTED**.
- Phases 6–9: **NOT STARTED**.
- POWER 3.8.0: **NO-GO**.

## Controlled Dependency Refresh

| Surface | State | Evidence |
|---|---|---|
| Python admission | CLOSED | Prior merged repository evidence |
| WEB-01 / WEB-05 | CLOSED | Security PR #405 and merge on `main` |
| Pre-HF governance snapshot | CLOSED | PR #408 protected merge on `main` |
| CI admission repair | CLOSED | PR #410 protected merge on `main` |
| HF admission | CLOSED | PR #406 protected merge and post-merge checks |
| Actions #396 | CLOSED / MERGED | Exact head/tree/parent and protected merge are retained below |
| PR #402 | DEFERRED / CLOSED WITHOUT MERGE | Broad maintenance bundle; split future admissions required |
| PR #407 | SUPERSEDED / CLOSED WITHOUT MERGE | Historical pre-HF evidence retained for auditability |
| Final integration | CLOSED / FINAL INTEGRATION VERIFIED | Current main graph, locks/exports, tests, security, package, upgrade, Docs, and CodeQL passed |
| Foundation Hardening | CLOSED / IMPLEMENTED / VERIFIED | PR #414 protected normal merge and post-merge checks are on `main` |
| Phase 5A runtime contracts | CLOSED / MERGED / VERIFIED | PR #415 protected merge and post-merge checks |
| Evaluation corpus v1 | HISTORICAL / RETAINED / SEMANTIC ERRATUM | Immutable original revision; superseded for future evaluation |
| Phase 5A.1 | CLOSED / MERGED / VERIFIED | PR #416 protected merge and post-merge checks |
| Phase 5B | CLOSED / MERGED / VERIFIED | PR #418; merge `6a315d5`; live parent erratum retained above |
| INFRA-1 | CLOSED / MERGED / VERIFIED | PR #419; merge `bfb9688`; constrained local broker merged; receiver deployment is operator follow-up |
| INFRA-1 governance reconciliation | CLOSED / MERGED / VERIFIED | PR #420; merge `5e65efa5`; reconciled framework gate vs operator receiver deployment |
| PR #421 (finding repairs) | SUPERSEDED / CLOSED WITHOUT MERGE | Historical candidate epoch; superseded by P38-G0 governance rebaseline |
| Repository cleanup | CLOSED / MERGED / VERIFIED | PR #422; merge `cf017f3`; removed confirmed obsolete repository artifacts |
| CI required docs build | CLOSED / MERGED / VERIFIED | PR #423; merge `906986c`; always emit required docs build for PRs |
| Task journal integrity fail-closed | CLOSED / MERGED / VERIFIED | PR #424; merge `3cb94ff`; fail closed on corrupt journals, degraded read-only view |
| Maintenance line 3.7 bootstrap | CLOSED / MERGED / VERIFIED | PR #425 on `release/3.7`; CI triggers and backport workflow |
| Backport task journal integrity (3.7.12) | CLOSED / MERGED / VERIFIED | PR #426 on `release/3.7`; released as `v3.7.12` |
| Release notes 3.7.12 | CLOSED / MERGED / VERIFIED | PR #427 on `release/3.7`; patch release notes |
| Bump version 3.7.13 | CLOSED / MERGED / VERIFIED | PR #428 on `release/3.7`; skill mirror sync, released as `v3.7.13` |
| Gate P38-G0 (governance rebaseline) | CLOSED / MERGED / VERIFIED | PR #429; merge `df813f4`; rebaselined governance and progression sequence |
| Gate P38-G1 (north-star architecture) | CLOSED / MERGED / VERIFIED | PR #430; merge `38f656b`; aligned control-plane architecture with ADR-0007 |
| Gate P38-G2 (product identity & docs) | CLOSED / MERGED / VERIFIED | PR #431; merge `7546ff8`; rebaselined product identity, docs, and feature matrix |
| Phase 5C (SearchScope pushdown) | CLOSED / MERGED / VERIFIED | PR #434; merge `294b483`; search scope pushdown across retrieval pipelines |

## INFRA-1 merged evidence and governance reconciliation

INFRA-1 implementation was admitted, reviewed, and merged on `main`:

- PR: [#419](https://github.com/weby-homelab/power-framework/pull/419)
- Candidate Head: `d6eaa4f1967178f5ebbf458168c1b7e7fadb524b`
- Merge Commit: `bfb968846c0fc41582c2367782a28540498715b4`
- Merge Tree: `70dbfd0f9c980672a757be601b72b138e4e3d744`
- Merge Parents: `6a315d5919eeef797bc506ecb216313c20419fc2` and `d6eaa4f1967178f5ebbf458168c1b7e7fadb524b`
- Merge GPG: `verified=true / valid`
- Pre-Merge Required Checks: 11/11 PASS
- Post-Merge Checks: CI = PASS, Docs = PASS, CodeQL = PASS
- Closure Comment: [5671031312](https://github.com/weby-homelab/power-framework/pull/419#issuecomment-5671031312)

### Architectural decision: framework capability vs operator deployment

The framework contract must NOT depend on one specific homelab host.

Binding architectural invariant:

```text
HOST-SPECIFIC DEPLOYMENT FACT != FRAMEWORK INVARIANT
```

PRXMX-01, specific IP addresses, individual receiver accounts, host-specific SSH
keys, and concrete storage mount availability must never be required to merge or
advance generic POWER Framework phases. The framework gate proves:

- receiver security contract;
- broker behavior and AF_UNIX principal boundary;
- transport restrictions and fixed argv;
- hermetic and adversarial test suites;
- reference deployment configuration.

### Deployment validation (Operator follow-up)

Real receiver validation remains an essential operator operational step:

- non-root receiver account;
- forced `rrsync` execution;
- `restrict` mode and SSH subsystem lockdowns;
- stable source allowlist where configured;
- host-key pinning;
- credential isolation;
- probe and dry-run execution;
- bounded replicate execution;
- exact verification;
- restore test where separately authorized.

Absence of a specific physical host or operator deployment credential is an
operator follow-up, not a generic framework admission failure.

### Governance reconciliation rationale (Not retroactive gate weakening)

This correction is NOT: tests failed, therefore lower the bar.

Evidence:

- The INFRA-1 exact-head implementation passed all required framework checks.
- Protected normal merge completed on `main` without bypass or force.
- Post-merge CI, Docs, and CodeQL passed on the merged tree.
- Security invariants remain unchanged: zero arbitrary command surface, zero
  credential exposure, zero password fallback, zero direct agent SSH, strict
  receiver lockdown, and secret-free client/agent boundary.
- The earlier acceptance wording accidentally promoted a host-specific deployment
  fact into a framework invariant.
- This correction restores the clean architectural boundary between generic
  framework capability and operator deployment validation.

> Historical note (INFRA-1 era): Phase 5C was then unstarted. Phase 5C was
> subsequently CLOSED via PR #434, corrected via P38-WP01-R1 (PR #437 / PR #438),
> and is CLOSED / VERIFIED AFTER R1 CORRECTION. Phase 5D is CLOSED / MERGED / VERIFIED (PR #439 / PR #440). Phase 5E is READY FOR SEPARATE ADMISSION / NOT STARTED.

## Actions #396 exact objects

- PR: [#396](https://github.com/weby-homelab/power-framework/pull/396),
  `CLOSED / MERGED`.
- Candidate head: `147afac8f4b43a967207309d69ccad78c6d16739`.
- Candidate tree: `664f34995961a2990dee00ecde0ebe7c8ed0f5d8`.
- Candidate parents: `a715df08b34a0c561e487199ff56a2853279d951` and
  `64178e9d2791fc8a291ac647374efc566f201f0e`.
- Candidate GitHub verification: `verified=true`, `reason=valid`.
- Protected merge: `a386858a45489eb5db213d42ffe773db9134ff88`.
- Merge parents: `64178e9d2791fc8a291ac647374efc566f201f0e` and
  `147afac8f4b43a967207309d69ccad78c6d16739`.
- Merge tree equals candidate tree exactly; the four intended workflow files
  are the complete Actions diff.
- No admin bypass, protection bypass, force merge, or auto-merge was used.

## Final integration evidence

- Live protected `main`: `a386858a45489eb5db213d42ffe773db9134ff88`, tree
  `664f34995961a2990dee00ecde0ebe7c8ed0f5d8`, GitHub `verified=true`.
- Required protected contexts were freshly enumerated from REST: `test (3.13)`,
  `test (3.14)`, `security`, `package-smoke`, `upgrade-matrix (ubuntu-latest)`,
  `upgrade-matrix-aggregate`, `base-runtime-smoke`, `benchmark-integrity`,
  `analyze (python)`, `CodeQL`, and `build`.
- Exact-main local validation: `uv lock --check`, `uv sync --locked`, pip check,
  Ruff, format, MyPy, strict MkDocs, and pip-audit passed.
- Frozen regression: 346 targeted PSE/Task/Decision/crash tests passed; full
  hermetic suite passed with `1775 passed, 4 skipped, 17 deselected`, coverage
  `83.06%`.
- Security subset: `147 passed`; package smoke, neural contract, base runtime,
  upgrade matrix/aggregate, benchmark integrity, outcome, and continuity gates
  passed. No model was downloaded.
- Remote CI, Docs, and CodeQL workflow runs for current main were successful.
- `artifact-metadata: write` is not a current POWER requirement; existing
  attestation permissions remain unchanged.

## Stale PR dispositions

| PR | Exact head | Exact base | Disposition |
|---|---|---|---|
| #402 | `555748e07f4ef2d61dc08dc0b3cb4c8d92b913d0` | `2d8058854ffbfae8526095af9809ab2c6f9c04f6` | `CLOSED WITHOUT MERGE / DEFERRED`; failed package-smoke, broad incompatible bundle |
| #407 | `a3f8cb5f0cfd7e5b37ea316146a4e761a99a46e2` | `119d5c39aa2c22734ca72c351f8a70790371678f` | `CLOSED WITHOUT MERGE / SUPERSEDED HISTORICAL EVIDENCE`; unsigned stale pre-HF snapshot |

## HF #406 exact objects

- PR: [#406](https://github.com/weby-homelab/power-framework/pull/406),
  `MERGED`, `merged=true`.
- Base at final admission:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- Final head:
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- Final head tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- Final head parents:
  `75f3d7dad242566887fe77b5c64cd5b64aaa0576` and
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- GitHub commit verification: `verified=true`, `reason=valid`.
- Protected merge SHA:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Protected merge parents:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b` and
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- Protected merge tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- The final normal merge used exact-head guard `c385073…`; no bypass or force
  operation was used.
- Intended target: `huggingface-hub 1.30.0`.
- Maintained specifier: `>=1.30.0,<1.31.0`.
- PR #406 dependency diff is limited to `pyproject.toml`,
  `release/web-runtime.requirements.txt`, and `uv.lock`.
- `uv.lock` SHA-256:
  `d8a7456d53bdfc79090f4b3a3b9279664e2662c4f7343100a68db734c167485a`.
- Web export SHA-256:
  `4001e0b073acb7c6eb40bab6047bcb13adedbca3d2a6ebdf23e1b28687b435c3`.

## HF merge #406

- PR: [#406](https://github.com/weby-homelab/power-framework/pull/406),
  `MERGED`, `merged=true`.
- Final HF head:
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- Final HF head tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- GitHub head verification: `verified=true`, `reason=valid` at
  `2026-09-08T09:49:03Z`.
- Protected merge SHA:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Protected merge parents are
  `7ed70766904e394d9717fe3fb7e18ed079e1887b` and
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- The merged tree preserves the three-file HF dependency diff and the CI
  trigger repair already present on `main`.

## Governance and CI merge history

- Prior governance bootstrap PR #408 merge:
  `4b49e00c75866fa57f71e7bef61547915f7e01db`.
- Post-governance state PR #409 merge:
  `0400aea20776715d801339de325ba0cba65fab10`.
- CI admission repair PR #410 merge:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- HF PR #406 merge:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Post-HF governance publication PR #411 merge:
  `d8b704f6125347ff9f9c39981193807d2160b135`.

## Gate decision and blockers

```text
CONTROLLED DEPENDENCY REFRESH = CLOSED / FINAL INTEGRATION VERIFIED
PR #402 = CLOSED WITHOUT MERGE / DEFERRED
PR #407 = CLOSED WITHOUT MERGE / SUPERSEDED HISTORICAL EVIDENCE
ACTIONS #396 = CLOSED / MERGED
FOUNDATION HARDENING = CLOSED / IMPLEMENTED / VERIFIED
PHASE 5 = IN PROGRESS
PHASE 5A RUNTIME CONTRACTS = CLOSED / MERGED / VERIFIED
PHASE 5A.1 EVALUATION CORRECTION = CLOSED / MERGED / VERIFIED
PHASE 5B = CLOSED / MERGED / VERIFIED / PR #418
INFRA-1 = CLOSED / MERGED / VERIFIED / PR #419 / merge bfb9688
INFRA-1 GOVERNANCE RECONCILIATION = CLOSED / MERGED / VERIFIED / PR #420 / merge 5e65efa
PR #421 FINDING REPAIRS = SUPERSEDED / CLOSED WITHOUT MERGE
REPOSITORY CLEANUP = CLOSED / MERGED / VERIFIED / PR #422 / merge cf017f3
CI REQUIRED DOCS BUILD = CLOSED / MERGED / VERIFIED / PR #423 / merge 906986c
TASK JOURNAL INTEGRITY FAIL-CLOSED = CLOSED / MERGED / VERIFIED / PR #424 / merge 3cb94ff
MAINTENANCE RELEASES = CLOSED / MERGED / VERIFIED / v3.7.12 & v3.7.13 on release/3.7
GATE P38-G0 (GOVERNANCE REBASELINE) = CLOSED / MERGED / VERIFIED / PR #429 / merge df813f4
GATE P38-G1 (NORTH-STAR ARCHITECTURE) = CLOSED / MERGED / VERIFIED / PR #430 / merge 38f656b
GATE P38-G2 (PRODUCT IDENTITY & DOCS) = CLOSED / MERGED / VERIFIED / PR #431 / merge 7546ff8
PHASE 5C (SEARCH SCOPE PUSHDOWN) = CLOSED / VERIFIED AFTER R1 CORRECTION / PR #434 CORRECTED BY PR #437
P38-WP01-R1 (PHASE 5C CLOSURE CORRECTION) = CLOSED / MERGED / VERIFIED / PR #437
PHASE 5D (P38-WP02) = CLOSED / MERGED / VERIFIED / PR #439 / PR #440 / merge 19bab5a
PHASE 5E (P38-WP03) = READY FOR SEPARATE ADMISSION / NOT STARTED
```

The dependency surfaces, Foundation Hardening, Actions admission, Phase 5A
runtime contracts, Phase 5A.1 semantic correction, Phase 5B router, INFRA-1
broker, repository cleanup, CI required docs build, and task journal integrity
fail-closed repair were accepted through normal protected merges and post-merge checks.
Real receiver deployment is an operator follow-up. Gates P38-G0 (Governance Rebaseline),
P38-G1 (North-Star Architecture Alignment), and P38-G2 (Product Identity & Documentation Rebaseline)
are closed and verified. Phase 5C (SearchScope Pushdown, PR #434) is CLOSED /
VERIFIED AFTER R1 CORRECTION (PR #437). Phase 5D (P38-WP02) is CLOSED /
MERGED / VERIFIED (PR #439, PR #440). Phase 5E (P38-WP03) is READY FOR SEPARATE ADMISSION / NOT STARTED.
A post-merge Dependabot run failure on main was investigated and dispositioned as Class C (non-required
dependency update attempt failure, non-blocking).
POWER 3.8.0 cannot be released from this state.

## Canonical governance status

The prior governance, dependency, Foundation Hardening, Phase 5A runtime
contract, Phase 5A.1 correction, Phase 5B merge, INFRA-1 broker merge, and post-INFRA-1
repairs are canonical on protected `main`:

- Governance branch: `docs/power-3.8-final-integration-course-correction`.
- Prior governance bootstrap merge: `4b49e00c75866fa57f71e7bef61547915f7e01db`,
  with GitHub `verified=true`, `reason=valid`.
- Governance PR #413 is protected-merged as `95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a`.
- Post-governance state PR #409 and CI admission repair PR #410 are merged on
  protected `main`.
- Phase 5A runtime contracts PR #415 is protected-merged as
  `0a70ca4e9acc89596acd192931c1d174040ad484`.
- Phase 5A.1 correction PR #416 is protected-merged as
  `dde1e1369c2d79d8f01b9fce21ae1fb55834a814`.
- Phase 5B router PR #418 is protected-merged as
  `6a315d5919eeef797bc506ecb216313c20419fc2`.
- INFRA-1 broker PR #419 is protected-merged as
  `bfb968846c0fc41582c2367782a28540498715b4`, with tree
  `70dbfd0f9c980672a757be601b72b138e4e3d744`, closure comment `5671031312`,
  and post-merge CI/Docs/CodeQL verified.
- INFRA-1 governance reconciliation PR #420 is protected-merged as
  `5e65efa59288cd84aac3d416e4611e19d23ea7b7`.
- Repository cleanup PR #422 is protected-merged as
  `cf017f3f451be4b4e5aca0d599f6265a8ff8113a`.
- CI required docs build PR #423 is protected-merged as
  `906986cc0bf5d29994c65aebcfd1fbceaeec7307`.
- Task journal integrity fail-closed repair PR #424 is protected-merged as
  `3cb94ff7f82d18c0f77b336848d1c34f220e58a3` with tree
  `03c2689023e2e2213cd47f243f8fb46a6f626fcc`.
- Maintenance line `release/3.7` was bootstrapped (PR #425) and published
  releases `v3.7.12` (PR #426, #427) and `v3.7.13` (PR #428, `44a3dd71fc14b4c45e3c379b5728c27395727560`).
- Gate P38-G0 governance rebaseline PR #429 is protected-merged as `df813f4263e472ee4ca9cce6373bf122ec8af5c5`
  with tree `099796bdd4d27d6456f35b6791a10830b87df56d`.
- Gate P38-G1 north-star architecture PR #430 is protected-merged as `38f656b50da3b2307456f673ed1f77e01e907470`
  with tree `ac7c62872f0fe9d1de6d5d0b232aa24ea58509c0`.
- Gate P38-G2 product identity PR #431 is protected-merged as `7546ff86bd5debdd23c9e5a08cddc7b10224b850`
  with tree `2e3e0233639270df5e92d1b348873c0fd6194b38`.
- Phase 5C admission reconciliation PR #433 is protected-merged as `6c247c7e4c1788a8bd5388b1327170a8e7493852`
  with tree `09a6266d6e4336cd3d4c0b7e50561828ae8470af`.
- Phase 5C SearchScope pushdown runtime PR #434 is protected-merged as `294b48319fdcd3dd3bc030a940bda64f7583889f`
  with tree `a22f9267e4ddc626f38e05b23dbdfd6abadd91da`.
- Phase 5C closure reconciliation PR #435 is protected-merged as `319e6101e6c96f04d532de67a6f9e8f2aee4fa73`
  with tree `1768fb1662dc968611b1e8ab7cbd31d2c5997747` and parents
  `294b48319fdcd3dd3bc030a940bda64f7583889f` and `708b3677e97b91ef1748d62fce79c7b642b1419d`.
  Narrative SHA `319e610d4806a6c0c00b5220c3848b3b429ef9eb` is a reporting typo and does not exist as a Git object.
- P38-WP01-R1 admission PR #436 is protected-merged as `a0ee8eea36ede547ef4196f4e54f3c3465de044a`
  with tree `629688d882acd241c5e95679f418d60cac736825` and parents
  `319e6101e6c96f04d532de67a6f9e8f2aee4fa73` and `5ebc13d3cd42ba8bb9d2202e3e4a81c22ae91004`.
- P38-WP01-R1 runtime correction PR #437 is protected-merged as `999f8c04a9cafd39deb9de2716e5cd07ec3e60b6`
  with tree `9da812c49d2c9f43030656f6655d8e541bfe7d7c` and parents
  `a0ee8eea36ede547ef4196f4e54f3c3465de044a` and `d60032111144756beca997b6bc7aeb5d9ff7c659`.
- The prior `docs/power-3.8-premerge-state-publication` branch remains
  provisional evidence and is retained as source material; it is not replaced
  or deleted.
- HF #406 and Actions #396 are closed by protected merges; their candidate
  epochs remain retained evidence for the dependency-refresh audit.

## Next authorized work

1. Prepare admission and prerequisites for Phase 5E (P38-WP03 — Shadow Benchmark / Legacy Comparison).
2. Adhere to strict preflight admission, TDD defect reproduction, and dual-side diff audit.
3. Keep Phase 5E–9 runtime work, version bumps, tags, releases,
   and POWER 3.8.0 publication blocked until each declared gate is
   independently closed.

## Do not start

- Do not reopen or mutate the closed Actions #396 admission; any future
  dependency candidate must record its exact base/head/tree/parent, diff,
  hashes, tests, security, CI, and policy evidence.
- Do not merge, auto-merge, force-push, or bypass protection.
- Do not implement Phase 5E until preflight admission is completed.
- Do not start Phase 5E+ runtime implementation, Phase 5F incremental dense validity, Phase 5G MCP context tools, capture, A2A, AGE, pgvector, PostgreSQL, version bump, tag, or release in this gate.
- Do not bump the public version, create a tag, create a release, or publish
  `POWER 3.8.0`.
- Do not treat candidate or evidence-branch documents as `MERGED MAIN` evidence.

## Cross-links

- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Architecture planning](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Phase 5A.1 report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5a/PHASE_5A_1_REPORT.md)
- [v1 semantic erratum](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5a/EVALUATION_CORPUS_V1_ERRATUM.md)
- [Active evaluation manifest](https://github.com/weby-homelab/power-framework/blob/main/benchmarks/power38/retrieval_eval/v1.1/manifest.json)
- [Phase 5B report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5b/PHASE_5B_REPORT.md)
- [Phase 5B routing evaluation](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5b/domain-routing-evaluation-v1.md)
- [Phase 5C verification report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5c/PHASE_5C_REPORT.md)
- [Phase 5C baseline reproduction](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5c/PHASE_5C_BASELINE.md)
- [Phase 5C implementation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T110500Z_p38_wp01_phase5c_search_scope_pushdown.md)
- [Phase 5C post-merge closure reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T111500Z_p38_wp01_phase5c_closure_reconciliation.md)
- [Phase 5D verification report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5d/PHASE_5D_REPORT.md)
- [Phase 5D verification evidence](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5d/phase5d_verification.json)
- [Phase 5D admission handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T140000Z_p38_wp02_phase5d_admission.md)
- [Phase 5D closure reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T193000Z_p38_wp02_phase5d_closure_reconciliation.md)
- [INFRA-1 governance reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-15T090637Z_infra1_governance_reconciliation.md)
- [Latest final-integration handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-09T065950Z_controlled-dependency-refresh_final-integration.md)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)
