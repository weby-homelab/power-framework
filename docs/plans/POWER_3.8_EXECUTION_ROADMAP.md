# POWER 3.8 — Execution Roadmap

> This roadmap is a repository-visible governance projection. Before a
> protected merge it is provisional; after a protected merge its paths are
> canonical for that snapshot. It is not a release authorization and does not
> replace live GitHub state, exact Git objects, or protected merge policy.

## Canonical execution sequence

```text
POWER 3.7.13
DONE / PUBLIC / FROZEN (Maintenance line `release/3.7`)
        ↓
Phase 0
CLOSED / FROZEN
        ↓
Phase 1
CLOSED / FROZEN
        ↓
Phase 2
CLOSED / FROZEN
        ↓
Phase 3
CLOSED / FROZEN
        ↓
Phase 4
CLOSED / FROZEN
        ↓
Controlled Dependency Refresh
         ├── Pre-HF governance snapshot — CLOSED / PR #408 MERGED
         ├── Python admission — DONE
         ├── WEB-01 / WEB-05 — DONE
         ├── CI admission repair PR #410 — CLOSED / MERGED
         ├── HF admission PR #406 — CLOSED / MERGED
         ├── Actions admission PR #396 — CLOSED / MERGED
         ├── PR #402 — DEFERRED / CLOSED WITHOUT MERGE
         ├── PR #407 — SUPERSEDED / CLOSED WITHOUT MERGE
         └── Final integration admission — CLOSED / VERIFIED
          ↓
Pre-Phase-5 Foundation Hardening
CLOSED / IMPLEMENTED / VERIFIED
            ↓
Phase 5A — Runtime contracts v2 + frozen evaluation corpus
CLOSED / MERGED / VERIFIED (PR #415)
             ↓
Phase 5A.1 — Evaluation corpus semantic integrity correction
CLOSED / MERGED / VERIFIED (PR #416)
              ↓
Phase 5B — Domain Policy v2 and deterministic multi-domain router
CLOSED / MERGED / VERIFIED (PR #418 / merge 6a315d5)
        ↓
INFRA-1 — Constrained Local Infrastructure Execution Broker
CLOSED / MERGED / VERIFIED (PR #419 / merge bfb9688)
        ↓
Post-INFRA-1 Governance Reconciliation & Fixes
CLOSED / MERGED / VERIFIED (PR #420, #422, #423, #424)
        ↓
Gate P38-G0 — Governance Rebaseline
CLOSED / MERGED / VERIFIED (PR #429)
        ↓
Gate P38-G1 — North-Star Architecture Alignment
CLOSED / MERGED / VERIFIED (PR #430)
        ↓
Gate P38-G2 — Product Identity & Documentation Rebaseline
CLOSED / MERGED / VERIFIED (PR #431)
        ↓
Phase 5C (P38-WP01) — Search Scope Pushdown
CLOSED / MERGED / VERIFIED (PR #434)
         ↓
Phase 5D (P38-WP02) — Multi-Domain Union & Conflict Resolution / ContextPack
CLOSED / MERGED / VERIFIED (PR #439 / PR #440)
         ↓
Phase 5E (P38-WP03) — Shadow Benchmark / Legacy Comparison
OPEN / NOT PASSED / EVALUATION TRUST REPAIRED (P38-WP03-R5 CLOSED / FAILED VERIFICATION; v1.5 exposed/unused/invalidated/not reusable; fresh evaluation authoring remains deferred)
           ↓
P38-WP03-R6A.1 — Evaluation Admission Integrity Repair
CLOSED / MERGED / DEVELOPMENT ADMITTED (review provenance v2, independent fixture ownership, fail-closed development admission, metric semantics, FAST contract, and historical q14 diagnostic; no fresh holdout and no one-shot)
           ↓
P38-WP03-R6A.2 — Final Holdout-Execution Admission Repair
CLOSED / MERGED / EXACT REPAIR TREE PRESENT / INTEGRITY VERIFIED (no fresh revision authored and no fresh holdout executed)
            ↓
OPENVINO_471_SIGNED_UPSTREAM_INTEGRATION
NEXT SEPARATE INVOCATION (reconstruct #473 from current protected main; preserve attribution; resolve runtime-baseline blockers)
            ↓
Fresh evaluation authoring
DEFERRED until the OpenVINO runtime baseline is dispositioned (sealed-not-secret/no-tuning policy; no one-shot execution in this gate)
            ↓
Phase 5F (P38-WP04) — Phase 5F Incremental Dense Validity / dirty-set behavior
BLOCKED (Phase 5E remains OPEN / NOT PASSED; OpenVINO integration, fresh evaluation authoring, and separate admission are required)
          ↓
Phase 5G–5H (P38-WP05–P38-WP06) — MCP, Closure
PLANNED / NOT STARTED (gated behind Phase 5F)
         ↓
Phase 6 (P38-WP07–P38-WP09) — Observation & Capture
PLANNED / NOT STARTED
         ↓
Phase 7 (P38-WP10–P38-WP11) — Graph, Artifact & Optional Hub
PLANNED / NOT STARTED
        ↓
Phase 8 (P38-WP12) — Security / Durability / Chaos Verification
PLANNED / NOT STARTED
        ↓
Phase 9 (P38-WP13) — Real-Work Validation & Release Decision
PLANNED / NOT STARTED
        ↓
POWER 3.8.0
NO-GO
```

## Current status markers

| Work item | Status | Meaning |
|---|---|---|
| Public `3.7.13` | DONE / PUBLIC | Stable public maintenance release (`release/3.7`, tags `v3.7.12`, `v3.7.13`) |
| Development main | `3.7.11` | Package metadata on development `main`; no premature bump |
| Phases 0–4 | DONE / FROZEN | No reopening in this gate |
| Python refresh | DONE | Prior controlled admission |
| WEB-01 / WEB-05 | DONE | Closed through security PR #405 |
| Pre-HF governance snapshot | CLOSED | PR #408 protected merge is on `main` |
| CI admission repair | CLOSED | PR #410 protected merge is on `main` |
| HF refresh | CLOSED | PR #406 protected merge and post-merge checks are on `main` |
| Actions #396 | CLOSED | Exact candidate and protected merge are preserved as immutable evidence |
| PR #402 | DEFERRED / CLOSED WITHOUT MERGE | Broad unsafe maintenance bundle; future updates require bounded split admissions |
| PR #407 | SUPERSEDED / CLOSED WITHOUT MERGE | Historical pre-HF evidence retained for auditability |
| Final integration | CLOSED / FINAL INTEGRATION VERIFIED | Current main dependency graph, security, package, upgrade, frozen regression, Docs, and CodeQL evidence passed |
| Foundation Hardening | CLOSED / IMPLEMENTED / VERIFIED | PR #414 protected merge and post-merge checks are on `main` |
| Phase 5A runtime contracts | CLOSED / MERGED / VERIFIED | PR #415 protected merge and post-merge checks |
| Evaluation corpus v1 | HISTORICAL / RETAINED / SEMANTIC ERRATUM | Immutable historical evidence; v1.1–v1.4 exposed, v1.5 exposed/unused/invalidated/not reusable |
| Phase 5A.1 | CLOSED / MERGED / VERIFIED | PR #416 protected merge and post-merge checks |
| Phase 5B | CLOSED / MERGED / VERIFIED | PR #418; live parent erratum is retained in current state |
| INFRA-1 | CLOSED / MERGED / VERIFIED | PR #419; merge `bfb9688`; framework contract closed; real receiver is operator follow-up |
| INFRA-1 reconciliation | CLOSED / MERGED / VERIFIED | PR #420; merge `5e65efa5`; framework vs operator receiver separation |
| PR #421 (review findings) | SUPERSEDED / CLOSED WITHOUT MERGE | Replaced by P38-G0 governance rebaseline |
| Repository cleanup | CLOSED / MERGED / VERIFIED | PR #422; merge `cf017f3`; removed confirmed obsolete repository artifacts |
| CI required docs build | CLOSED / MERGED / VERIFIED | PR #423; merge `906986c`; always emit required docs build for PRs |
| Task journal integrity | CLOSED / MERGED / VERIFIED | PR #424; merge `3cb94ff`; fail-closed on corrupt task journal |
| Maintenance bootstrap | CLOSED / MERGED / VERIFIED | PR #425 on `release/3.7` |
| Patch release 3.7.12 | CLOSED / MERGED / VERIFIED | PR #426, PR #427 on `release/3.7`; tagged `v3.7.12` |
| Patch release 3.7.13 | CLOSED / MERGED / VERIFIED | PR #428 on `release/3.7`; tagged `v3.7.13` |
| Gate P38-G0 | CLOSED / MERGED / VERIFIED | Governance Rebaseline; aligns mutable state with live reality (PR #429, merge `df813f4`) |
| Gate P38-G1 | CLOSED / MERGED / VERIFIED | North-Star Architecture Alignment; freezes architecture direction (PR #430, merge `38f656b`) |
| Gate P38-G2 | CLOSED / MERGED / VERIFIED | Product Identity & Documentation Rebaseline; aligned docs with ADR-0007 (PR #431, merge `7546ff8`) |
| Phase 5C (P38-WP01) | CLOSED / VERIFIED AFTER R1 CORRECTION | SearchScope pushdown PR #434 corrected by PR #437 |
| P38-WP01-R1 | CLOSED / MERGED / VERIFIED / PR #437 | Phase 5C SearchScope Closure Correction |
| Phase 5D (P38-WP02) | CLOSED / VERIFIED AFTER R1 CORRECTION | Multi-Domain Union & Conflict Resolution / RetrievalPlanner / ContextPack vertical slice (PR #439, PR #440, PR #441 corrected by PR #442, PR #443) |
| P38-WP02-R1 | CLOSED / MERGED / VERIFIED / PR #443 | Phase 5D RetrievalPlanner / ContextPack Closure Correction |
| Phase 5E (P38-WP03) | OPEN / NOT PASSED / FRESH EVALUATION AUTHORING REQUIRED | Shadow Benchmark / Legacy Comparison; historical R1–R5 failures retained; R6A.1 repaired development admission and R6A.2 technical repair is retained without fresh holdout execution; authoring is deferred until OpenVINO baseline disposition |
| P38-WP03-R1 | CLOSED / FAILURE EVIDENCE | Phase 5E failure evidence |
| P38-WP03-R2 attempt | CLOSED / FAILED VERIFICATION | PR #449 runtime + PR #450 governance |
| P38-WP03-R3 | CLOSED / SECURITY CORRECTION VERIFIED | PR #451 runtime correction; PR-R3B governance rebaseline |
| P38-WP03-R4 | CLOSED / HISTORICAL FAILED VERIFICATION | Superseded historical admission epoch; do not reuse its exposed evidence |
| P38-WP03-R6A.1 | CLOSED / MERGED / DEVELOPMENT ADMITTED | Evaluation admission integrity repair; freeze `phase5e_protocol_r6a1_freeze.json`; no fresh holdout or one-shot execution |
| P38-WP03-R6A.2 | CLOSED / MERGED / EXACT REPAIR TREE PRESENT / INTEGRITY VERIFIED | Security repair retained; original admission process deviation recorded; no fresh holdout |
| PR #453 | CLOSED STALE / NOT MERGED | Future dedicated dependency-refresh gate if still needed |
| PR #454 | CLOSED STALE / NOT MERGED | Future dedicated dependency-refresh gate if still needed |
| PR #473 | CLOSED SUPERSEDED AS INTEGRATION VEHICLE / NOT MERGED | OpenVINO provenance retained; no feature rejection |
| Issue #471 | OPEN | Hardware-performance acceptance, including full-sync benchmark, remains incomplete |
| OpenVINO | PENDING SIGNED UPSTREAM INTEGRATION FROM CURRENT MAIN | Next action; unsigned source, old base, and review findings require independent disposition |
| Phase 5F (P38-WP04) | BLOCKED | Phase 5E remains open; OpenVINO integration, fresh evaluation authoring, and separate admission are required before Phase 5F |
| Phase 5G–5H (P38-WP05–06) | PLANNED / NOT STARTED | Gated by predecessor sequence (5E → fresh authoring/admission → 5F → 5G → 5H) |
| Phases 6–9 (P38-WP07–13) | PLANNED / NOT STARTED | No work authorized |
| POWER 3.8.0 | NO-GO | No tag, release, or public version change |

## R6A.2 post-merge governance reconciliation checkpoint

This checkpoint records the protected-main readback and queue cleanup after PR
#472. It is a post-merge governance reconciliation, not a retroactive approval
of the original admission process.

```text
PR #472 source head: 419ac4962d2b9e2f40095e61def2c242e15f2e83
PR #472 base: 2cfc9d3cf7264c71dae0b4cd5ed884738a56a1aa
PR #472 source tree: 24d2a6e507363662d0a047803aa7446309e39d9a
PR #472 source head parents: [2cfc9d3cf7264c71dae0b4cd5ed884738a56a1aa]
Actual merged commit: aafafe7453ba1d242cd80003866146a14abe311e
Actual merged tree: 24d2a6e507363662d0a047803aa7446309e39d9a
Actual merge parents: [2cfc9d3cf7264c71dae0b4cd5ed884738a56a1aa]
Source commit in main ancestry: NO
Source head tree preserved on main: YES
Merge signature: verified=true / reason=valid
Formal APPROVED reviews on #472: 0
Required approvals: at least 1
Required merge method: protected normal merge commit
Actual merge topology: squash-style / one parent
Original #472 admission process: NONCOMPLIANT
Technical repair: MERGED / EXACT REPAIR TREE PRESENT / INTEGRITY VERIFIED
Security repair: RETAINED
Process incident: HISTORICAL / RECORDED

Historical freeze sha256: 4dff4b361d98adcd74c1b1de5d78a66fe8936cb6b4809e7cb9cea9602f1b0250
Correction freeze sha256: 1381b8d38980a21a427a43dd340c0986dfc23835adba252102f4cbc0b6570762
Correction-freeze referenced artifact digests: 11/11 VERIFIED

PR_CLEANUP_ALLOWLIST: {453, 454, 473}
Allowlist scope: comment and close only for these exact PRs; no merge, rebase,
branch edit/deletion, issue closure, review-thread resolution, or policy change.
PR #453: CLOSED STALE / NOT MERGED / future dedicated dependency-refresh gate
PR #454: CLOSED STALE / NOT MERGED / future dedicated dependency-refresh gate
PR #473: CLOSED SUPERSEDED AS INTEGRATION VEHICLE / NOT MERGED
Issue #471: OPEN
OpenVINO: PENDING SIGNED UPSTREAM INTEGRATION FROM CURRENT MAIN
Phase 5E: OPEN / NOT PASSED
Phase 5F: BLOCKED
POWER 3.8.0: NO-GO
NEXT_ACTION: OPENVINO_471_SIGNED_UPSTREAM_INTEGRATION
```

The evidence-supported process statement is limited to the contract and live
objects: approval was required but absent, and the actual merge topology had
one parent instead of the required normal merge. No admin bypass,
branch-protection configuration, or human intent is inferred. #473 review
threads were not resolved during closure, and #471 remains open.

### INFRA-1 closed framework gate and governance reconciliation

INFRA-1 was admitted, reviewed, and merged on `main` via PR #419
(`bfb968846c0fc41582c2367782a28540498715b4`, tree
`70dbfd0f9c980672a757be601b72b138e4e3d744`, parents
`6a315d5919eeef797bc506ecb216313c20419fc2` and
`d6eaa4f1967178f5ebbf458168c1b7e7fadb524b`, closure comment `5671031312`).
Pre-merge required checks (11/11) and post-merge CI, Docs, and CodeQL passed.

Governance reconciliation resolved the contradiction between host-specific
deployment facts and generic framework invariants:

- Invariant: `HOST-SPECIFIC DEPLOYMENT FACT != FRAMEWORK INVARIANT`.
- Availability of PRXMX-01, specific IP addresses, individual receiver accounts,
  or storage mounts belongs to operator deployment validation, not generic
  framework gate closure.
- Framework gate proves receiver security contracts, broker behavior, fixed
  transport argv, hermetic tests, and reference deployment configuration.
- Security controls are fully preserved: zero arbitrary command surface, zero
  credential exposure, zero password fallback, zero direct agent SSH, strict
  receiver lockdown, and secret-free client/agent boundary.
- Real receiver deployment remains an operator follow-up.
- Historical note (INFRA-1 era): Phase 5C was then unstarted. Phase 5C was subsequently CLOSED via PR #434, corrected via P38-WP01-R1 (PR #437 / PR #438), and is CLOSED / VERIFIED AFTER R1 CORRECTION. Phase 5D is CLOSED / VERIFIED AFTER R1 CORRECTION (PR #439 / PR #440 / PR #441 corrected by PR #442 / PR #443). Phase 5E is OPEN / NOT PASSED / FRESH EVALUATION AUTHORING REQUIRED; R6A.1 development admission and the R6A.2 technical repair are CLOSED / MERGED / INTEGRITY VERIFIED. Phase 5F (P38-WP04 / Phase 5F Incremental Dense Validity / dirty-set behavior) remains BLOCKED.

## Controlled Dependency Refresh

The refresh is a sequence of independent gates, not one undifferentiated
dependency update:

1. **Python admission — complete.** Preserve its merged evidence.
2. **WEB-01 / WEB-05 — complete.** Security boundaries are closed through PR
   #405 and must not be reopened as part of HF work.
3. **CI admission repair — complete.** PR #410 fixed the missing PR-associated
   Docs `build` context for dependency-only changes and was normally merged.
4. **HF admission — complete.** PR #406 was refreshed through three candidate
   epochs, passed exact dependency/security/CI admission, and was normally
   merged. Its final merge is recorded below.
5. **Actions admission — complete.** PR #396 is protected-merged; its exact
   candidate and merge/tree relationship are retained above.
6. **PR #402 — deferred.** The broad maintenance bundle is closed without
   merge; future updates require bounded compatibility/security admissions.
7. **PR #407 — superseded.** The historical pre-HF evidence PR is closed
   without merge and retained for auditability.
8. **Final integration admission — complete.** Current main dependency,
   security, package, upgrade, frozen-regression, Docs, and CodeQL evidence
   passed on the exact protected main.
9. **Foundation Hardening — closed.** PR #414 is protected-merged with
   post-merge CI, Docs, and CodeQL verification.
10. **Phase 5A runtime contracts — closed.** PR #415 is protected-merged with
     independent post-merge verification.
11. **Phase 5A.1 — closed.** The corrected v1.1 corpus is protected-merged as
      PR #416 with independent post-merge CI, Docs, and CodeQL verification.
12. **Phase 5B — closed.** Domain Policy v2 and the deterministic multi-domain
       router were protected-merged as PR #418; the actual candidate parent
       `12dda70c…` corrects a historical reporting typo.
13. **INFRA-1 — closed.** The constrained local infrastructure
       execution broker was protected-merged as PR #419 (merge `bfb9688`).
        Real receiver deployment is an operator follow-up. Historical note: Phase 5C was
        unstarted at INFRA-1 time; it was subsequently CLOSED via PR #434 / PR #435, corrected via
         P38-WP01-R1 (PR #437 / PR #438), and is CLOSED / VERIFIED AFTER R1 CORRECTION. Phase 5D is CLOSED / VERIFIED AFTER R1 CORRECTION (PR #439 / PR #440 / PR #441 corrected by PR #442 / PR #443). Phase 5E is OPEN / NOT PASSED / FRESH EVALUATION AUTHORING REQUIRED; R6A.1 development admission and the R6A.2 technical repair are CLOSED / MERGED / INTEGRITY VERIFIED. Phase 5F (P38-WP04 / Phase 5F Incremental Dense Validity / dirty-set behavior) remains BLOCKED.

The controlled refresh and prior closures do not authorize a public version
bump, tag, release, Phase 5C, or any later phase.

## HF #406 admission anchor

```text
BASE_SHA:
7ed70766904e394d9717fe3fb7e18ed079e1887b

HEAD_SHA:
c385073583dc00dc7752169eb36f66ecdd7f4361

HEAD_TREE:
a5f63eb671d3d57dd304d497cef4c03c52ed340b

HEAD_PARENTS:
75f3d7dad242566887fe77b5c64cd5b64aaa0576, 7ed70766904e394d9717fe3fb7e18ed079e1887b

MERGE_SHA:
2d8058854ffbfae8526095af9809ab2c6f9c04f6

TARGET:
huggingface-hub 1.30.0

SPECIFIER:
>=1.30.0,<1.31.0

LIVE_PR_STATE:
MERGED / CLOSED

LIVE_MERGEABILITY:
N/A after merge; pre-merge exact state was mergeable=true / mergeable_state=clean

ADMISSION:
CLOSED / POST-MERGE VERIFIED
```

`mergeable_state` alone is neither merge authorization nor an automatic stop.
For each candidate, record the required and optional check-runs, pending or
failed checks, required reviews and requests, unresolved conversations, branch
freshness, rulesets, merge queue, deployment requirements, and the result of
the protected normal-merge admission test. Only GitHub policy acceptance for
the exact current head can close the gate.

## Candidate epoch rule

The candidate tuple is:

```text
PR number + base SHA + head SHA + head tree SHA + parent(s)
```

If any tuple member, relevant diff, lock/export hash, or policy state changes:

1. record the new head/tree/parent/base and the reason;
2. recompute the diff and all hashes;
3. rerun targeted local tests, security checks, and the required remote CI;
4. re-check the live merge policy; and
5. publish a new handoff/state pointer.

This is a new candidate audit epoch, not a workflow stop condition.

## Phase 5–9 boundaries

Phase 5 may eventually cover retrieval planning, ContextPacks, governed context
assembly, and MCP context/explainability surfaces. It begins only after
Pre-Phase-5 Foundation Hardening is admitted and separately authorized. The
Controlled Dependency Refresh, Phase 5A runtime contracts, Phase 5A.1
correction, Phase 5B router, and INFRA-1 broker are closed in this snapshot;
Phase 5C SearchScope pushdown is CLOSED / VERIFIED AFTER R1 CORRECTION
(PR #437);
Phase 5D is CLOSED / VERIFIED AFTER R1 CORRECTION (PR #439 / PR #440 / PR #441 corrected by PR #442 / PR #443); P38-WP02-R1 is CLOSED / MERGED / VERIFIED; Phase 5E is OPEN / NOT PASSED / FRESH EVALUATION AUTHORING REQUIRED; P38-WP03-R6A.1 is CLOSED / MERGED / DEVELOPMENT ADMITTED; P38-WP03-R6A.2 is CLOSED / MERGED / EXACT REPAIR TREE PRESENT / INTEGRITY VERIFIED; Phase 5F (P38-WP04 / Phase 5F Incremental Dense Validity / dirty-set behavior) remains BLOCKED.

### Phase 5 internal gates

Phase 5A, Phase 5A.1, Phase 5B, INFRA-1, Phase 5C, P38-WP01-R1, Phase 5D, P38-WP02-R1, P38-WP03-R6A.1 development admission, and the P38-WP03-R6A.2 technical repair are closed. Phase 5E is OPEN / NOT PASSED / FRESH EVALUATION AUTHORING REQUIRED. The following future
runtime gates remain `PLANNED / NOT IMPLEMENTED` until their own evidence and
protected admission; `OPENVINO_471_SIGNED_UPSTREAM_INTEGRATION` is the next separate gate, fresh evaluation authoring is deferred until its runtime baseline is dispositioned, and Phase 5F is BLOCKED:

```text
5A.1 — Evaluation corpus semantic integrity correction (closed)
5B — Deterministic multi-domain router (closed)
INFRA-1 — Constrained Local Infrastructure Execution Broker (closed / merged PR #419)
5C — Search scope pushdown (PR #434 corrected by PR #437; CLOSED)
P38-WP01-R1 — Phase 5C SearchScope Closure Correction (CLOSED / PR #437)
5D — RetrievalPlanner + ContextPack read-only vertical slice (CLOSED / VERIFIED AFTER R1 CORRECTION)
P38-WP02-R1 — Phase 5D RetrievalPlanner / ContextPack Closure Correction (CLOSED / PR #443)
5E — Shadow benchmark / legacy comparison (OPEN / NOT PASSED / FRESH EVALUATION AUTHORING REQUIRED; historical R1–R5 failures retained; R6A.1 development admission and R6A.2 technical repair closed)
P38-WP03-R6A.1 — Evaluation Admission Integrity Repair (CLOSED / MERGED / DEVELOPMENT ADMITTED; no fresh holdout or one-shot)
P38-WP03-R6A.2 — Final Holdout-Execution Admission Repair (CLOSED / MERGED / EXACT REPAIR TREE PRESENT / INTEGRITY VERIFIED; no fresh holdout)
OPENVINO_471_SIGNED_UPSTREAM_INTEGRATION — NEXT SEPARATE INVOCATION (reconstruct #473 from current protected main; preserve attribution; resolve runtime-baseline blockers)
Fresh evaluation authoring — DEFERRED until OpenVINO runtime baseline disposition (v1.5 exposed/unused/invalidated/not reusable; `SEALED_NOT_SECRET_NO_TUNING`)
5F — Phase 5F Incremental Dense Validity / dirty-set behavior (BLOCKED until OpenVINO integration, fresh evaluation authoring, and separate admission)
5G — Small MCP read/explainability surfaces
5H — Phase closure / default decision
```

The phase title is intentionally **Retrieval Planner, ContextPack Compiler &
MCP**. The existing Phase 3 Project Semantic Compiler remains the candidate
and proposal producer; it is not a context assembler. No generic
`SemanticCompiler` or `ContextCompiler` parallel subsystem is authorized.

### Pre-Phase-5 Foundation Hardening

The historical prerequisite was the explicit F1–F5 contract at
`artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md`.
It closed implicit mutation authority, principal/session semantics,
retrieval boundary overrides, bounded secret-free failure receipts, and actual
deadline/cancellation/budget behavior. It was an integration admission before
Phase 5, not a reopening of Phase 0–4.

### Phase 6 architecture scope

Phase 6 is **Agent Capture & Integrations** and remains `NOT STARTED`. Its
planned order is adapter → append-only raw event → session segmentation →
cheap noise gate → ProjectSemanticCompiler → domain membership →
`MemoryDisposition` → persistent `IndexWorkQueue`. Backpressure, idempotency,
restart recovery, session identity, privacy/sensitivity, retention/bitemporal
metadata, adapter isolation, and non-destructive retention are prerequisites.
Automatic canonical promotion and automatic embedding of every message are
anti-goals.

### Phase 7 architecture scope

Phase 7 is **Optional Context Broker, Materialized Views & Web** and remains
`NOT STARTED`. A broker façade is created only if multiple real consumers show
orchestration value beyond `ContextPackCompiler`, `ApplicationService`, and
materialized views. Rebuildable current-project, issue, decision, task, change,
hot-knowledge, session, domain, contradiction, and repair views use existing
PSE, TaskService, DecisionService, memory, source, and index boundaries. The
phase must not create a second source of truth or silently retain the legacy
`.power/tasks` / `.power/work-packets` ambiguity.

### Phase 8 architecture scope

Phase 8 is **Security / Reliability / Performance** and remains `NOT STARTED`.
It covers index-cost control, bounded queues, low-RAM behavior, crash recovery,
privacy/forgetting, quarantine, repair safety, concurrency, load/soak, and
cache/index recovery. Security evidence must cover untrusted model output,
path traversal, SSRF, shell injection, secret handling, and authorization.

### Phase 9 architecture scope

Phase 9 is **Migration / Benchmark / Release** and remains `NOT STARTED`. It
starts only after architecture, shadow, small-dataset, soak, capture, broker,
and hardening gates pass. The release order is migration → benchmark → upgrade
validation → RC → explicit POWER 3.8.0 decision; a plan is not release evidence.

Phases 5–9 work packages use explicit P38 governance and work-package identifiers:

```text
P38-G0: Governance Rebaseline
P38-G1: North-Star Architecture Alignment
P38-G2: Product Identity & Documentation Rebaseline
P38-WP01: Phase 5C SearchScope Pushdown
P38-WP02: Phase 5D ContextPack + EvidenceRef
P38-WP03: Phase 5E Shadow Evaluation
P38-WP04: Phase 5F Incremental Dense Validity
P38-WP05: Phase 5G MCP Context / Explainability
P38-WP06: Phase 5H Phase Closure
P38-WP07: Phase 6 Forensic & Capture Architecture
P38-WP08: Phase 6 Observation Contracts, Schema & Tests
P38-WP09: Phase 6 Agent Capture Runtime & Adapters
P38-WP10: Phase 7 Graph & Artifact Storage Projections
P38-WP11: Phase 7 Context Broker & Optional Hub Benchmark
P38-WP12: Phase 8 Security / Privacy / Chaos Verification
P38-WP13: Phase 9 Real-Work Validation / Release Candidate
```

These are **INTERNAL WORK-PACKAGE IDENTIFIERS — NOT RELEASES**. SemVer belongs strictly to real public releases on release branches. They do not authorize tags, GitHub releases, version bumps, or release artifacts.

## Roadmap remediation conditions

Treat the following as remediation inputs rather than automatic stops:

- HF base, head, tree, parent, diff, or PR state changes after authorization;
  start a new candidate epoch and recompute evidence.
- `mergeable_state=unstable`, `blocked`, or `unknown`; diagnose the concrete
  required check/policy cause and retry admission only after remediation.
- A required check fails; inspect its logs, apply a minimal related fix, and
  rerun the bounded gate.
- Required policy is not observable through one interface; use the approved
  authenticated fallback channels without exposing credentials.
- A source, dependency, workflow, version, or release file appears in a docs
  publication change; remove the unrelated scope before publication.

Stop only when a human-only approval/permission is objectively required after
the reviewer/request path is exhausted, a secret is lawfully unavailable, a
security remediation remains impossible after three meaningful cycles, or a
history/data-loss risk is demonstrated. Do not use admin bypass, protection
disablement, fake approval, or force merge. A later agent must independently
admit Foundation Hardening before starting Phase 5 and must not treat this
planning snapshot as runtime implementation evidence.

## Cross-links

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Context / memory / retrieval architecture](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Phase 5B report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5b/PHASE_5B_REPORT.md)
- [Phase 5B handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-11T011403Z_phase5b-domain-policy-router.md)
- [Phase 5C verification report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5c/PHASE_5C_REPORT.md)
- [Phase 5C baseline reproduction](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5c/PHASE_5C_BASELINE.md)
- [Phase 5C implementation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T110500Z_p38_wp01_phase5c_search_scope_pushdown.md)
- [Phase 5C post-merge closure reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T111500Z_p38_wp01_phase5c_closure_reconciliation.md)
- [Phase 5A.1 semantic-correction report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5a/PHASE_5A_1_REPORT.md)
- [Evaluation v1 erratum](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5a/EVALUATION_CORPUS_V1_ERRATUM.md)
- [Latest Phase 5A.1 handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-10T190036Z_phase5a1-evaluation-semantic-integrity.md)
- [Latest final-integration handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-09T065950Z_controlled-dependency-refresh_final-integration.md)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)
