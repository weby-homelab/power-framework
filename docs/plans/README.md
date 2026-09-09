# POWER Planning Index

This directory is the navigation index for POWER 3.8 planning, architecture,
and execution governance. It does not replace live GitHub state, exact Git
objects, signed commits, branch protection, or authoritative phase reports.

## ACTIVE GOVERNANCE

The following files form the active **post-final-integration governance and
next-gate projection**. The snapshot is canonical on `main` only after this
governance PR is protected-merged; mutable GitHub values always require fresh
REST verification:

- [POWER 3.8 — Current State](POWER_3.8_CURRENT_STATE.md)
- [POWER 3.8 — Execution Roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [POWER 3.8 — Development Protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [POWER 3.8 — Context / Memory / Retrieval Architecture](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Project-state handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Latest Foundation Hardening handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-09T162533Z_pre-phase5-foundation-hardening.md)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)

> Controlled Dependency Refresh is **CLOSED / FINAL INTEGRATION VERIFIED**.
> PR #402 is **DEFERRED / CLOSED WITHOUT MERGE** and PR #407 is
> **SUPERSEDED HISTORICAL EVIDENCE / CLOSED WITHOUT MERGE**. The
> context/memory/retrieval package is **CANONICAL PLANNING V2**. Foundation
> Hardening is **IMPLEMENTED / LOCALLY VERIFIED / PROTECTED-MERGE CANDIDATE**;
> it becomes `MERGED MAIN` only after the exact protected normal merge. Actions
> #396 is already closed/merged, while Phase 5A and all later runtime work are
> not started by this snapshot.

> Links to `artifacts/` are GitHub evidence permalinks intentionally outside
> the MkDocs navigation tree; they are not local documentation targets.

### Recovery procedure

To recover the current POWER 3.8 state:

1. Read `POWER_3.8_CURRENT_STATE.md`.
2. Read `POWER_3.8_EXECUTION_ROADMAP.md`.
3. Read `POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
4. Read `POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md` and the planning-artifacts
   README.
5. Read the latest append-only architecture handoff; classify the HF handoff as
   historical evidence.
6. Fetch current GitHub `main`, the closed gate dispositions, required checks,
   reviews, rulesets, and protected-branch policy independently through the
   authenticated REST API.
7. Verify every documented SHA and mutable status, including any candidate's
   exact head, required checks, reviews, and protected-branch policy, before
   acting or attempting a new gate action.
8. Treat this snapshot as repository governance memory and live GitHub as
   mutable operational truth. Finish the protected Foundation merge/readback,
   then prepare only the separate Phase 5A admission; do not start Phase 5A here.

## CURRENT PLANNING CONTRACTS

The following package is the active POWER 3.8 context, memory, retrieval, and
evaluation planning direction:

- [Human-readable architecture plan](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Planning artifacts README](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Context/retrieval contracts v2](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json)
- [Retrieval evaluation manifest v1](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/retrieval-eval-v1.schema.json)
- [Pre-Phase-5 Foundation Hardening gate](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md)
- [Domain Policy v2 example](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/domain-policy-v2.example.yaml)
- [Phase 5–9 acceptance gates](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/phase5-9-acceptance-gates.md)

These files are **PLANNED**, not implemented runtime behavior. The v1 context
schema and v1 index-cost policy remain retained historical/canonical planning
evidence and are not the active future implementation contract once v2 is
validated through the protected governance gate. No planning contract is a
phase report, release artifact, or authorization to start Phase 5.

## CONTRACT STATUS MAP

| Classification | Meaning | Current examples |
|---|---|---|
| ACTIVE GOVERNANCE | Current repository-state projection | Current state, roadmap, protocol |
| CURRENT PLANNING | Active future design, not runtime | Architecture plan, v2 contracts |
| SUPERSEDED PLANNING CONTRACT | Retained v1 evidence; not future implementation authority | v1 context schema, v1 index policy |
| HISTORICAL EVIDENCE | Immutable prior gate or stale candidate record | Prior handoffs, closed #407 evidence |
| PHASE EVIDENCE | Executed proof for a named phase/gate | Phase reports and receipts |
| ARCHITECTURAL DECISION | Durable decision requiring an ADR | `docs/adr/` records |
| NEXT RUNTIME GATE | Authorized sequence position, not implementation | Foundation protected merge; then Phase 5A |

## HISTORICAL PLAN

The existing dated plans below are retained as historical context. Their
presence does not make them current authority:

- [2026-07-14 POWER Framework v2](2026-07-14-power-framework-v2.md)
- [2026-07-23 POWER 3.2 WTF remediation](2026-07-23-power-3.2-wtf-remediation.md)
- [2026-07-24 multi-methodology expansion](2026-07-24-multi-methodology-expansion-plan.md)
- [Issue 187 production validation checklist](issue-187-production-validation-checklist.md)
- [2026-09-07 security merge → HF admission](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-07_security-merge-hf-admission.md) — historical, not current

No historical plan is deleted or silently reinterpreted by this index.

## PHASE EVIDENCE

Phase reports, receipts, schemas, and replay artifacts under
`artifacts/project-state/` are evidence for the phase or gate they name.
They are not a substitute for current-state projection or live GitHub truth:

- [Phase 4 verification report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-4/PHASE_4_REPORT.md)
- [Dependency refresh ledger](https://github.com/weby-homelab/power-framework/blob/main/artifacts/repository-cleanup/dependency-refresh-ledger.md)

HF #406, Actions #396, and final-integration checks remain attached to their PR,
commit, and handoff evidence. The context/memory/retrieval files under
`artifacts/project-state/planning/` are pre-implementation planning contracts,
not phase evidence. The final dependency evidence is `MERGED MAIN`; Foundation
Hardening is the current protected-merge candidate and Phase 5A remains
`NOT STARTED`.

## ARCHITECTURAL DECISION

Durable architectural decisions live in [`../adr/`](../adr/). The ADR catalog is
separate from execution status and must not be inferred from a chat, handoff,
historical plan, or PR comment.

## Status vocabulary

Every planning artifact must be explicitly understood as one of:

```text
ACTIVE
SUPERSEDED
HISTORICAL
EVIDENCE
ADR
PLANNED
APPROVED PLANNING DIRECTION
CANONICAL PLANNING
NOT IMPLEMENTED
IMPLEMENTED
VALIDATED
```

Machine-readable artifacts use three separate namespaces:

```text
planning_status: approved_planning_direction | canonical_planning | superseded
implementation_status: planned | implemented | validated | superseded
phase_status: blocked | not_started | implemented | validated | superseded
```

For backward compatibility, `status: planned` in the planning policy and YAML
example is a publication alias for the pre-implementation package. It does not
override or replace the three explicit namespaces above.

`PLANNED != IMPLEMENTED`: a merged architecture document is canonical planning,
not runtime completion. This canonical projection records the closed
Controlled Dependency Refresh, the v2 planning successor, and the next
Foundation Hardening admission. It does not authorize Actions #396, Phase 5,
any later phase, version bump, tag, release, or `POWER 3.8.0` publication.
