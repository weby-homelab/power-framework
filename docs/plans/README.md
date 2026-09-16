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
- [Latest Phase 5A.1 semantic-correction handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-10T190036Z_phase5a1-evaluation-semantic-integrity.md)
- [Phase 5B domain-policy/router report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-5b/PHASE_5B_REPORT.md)
- [Phase 5B domain-policy/router handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-11T011403Z_phase5b-domain-policy-router.md)
- [INFRA-1 original implementation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-12T201530Z_infra-1-constrained-execution-broker.md)
- [INFRA-1 governance reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-15T090637Z_infra1_governance_reconciliation.md)
- [Gate P38-G0 governance rebaseline handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T083000Z_p38_g0_governance_rebaseline.md)
- [Gate P38-G1 north-star architecture alignment handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T084000Z_p38_g1_north_star_architecture_alignment.md)
- [Gate P38-G2 product identity rebaseline handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T084800Z_p38_g2_product_identity_rebaseline.md)
- [Gate P38-G2 post-merge closure & Phase 5C admission reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T103000Z_p38_g2_post_merge_reconciliation.md)
- [Phase 5C implementation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T110500Z_p38_wp01_phase5c_search_scope_pushdown.md)
- [Phase 5C post-merge closure reconciliation handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-16T111500Z_p38_wp01_phase5c_closure_reconciliation.md)
- [INFRA-1 broker API](../api/infra_broker.md)
- [INFRA-1 architectural decision](../adr/0006-infra-1-constrained-execution-broker.md)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)

> Controlled Dependency Refresh is **CLOSED / FINAL INTEGRATION VERIFIED**.
> PR #402 is **DEFERRED / CLOSED WITHOUT MERGE** and PR #407 is
> **SUPERSEDED HISTORICAL EVIDENCE / CLOSED WITHOUT MERGE**. The
> context/memory/retrieval package is **CANONICAL PLANNING V2**. Foundation
> Hardening is **CLOSED / IMPLEMENTED / VERIFIED** after protected PR #414.
> Phase 5A runtime contracts are **CLOSED / MERGED / VERIFIED** through PR #415;
> Phase 5A.1 is **CLOSED / MERGED / VERIFIED** through PR #416. Phase 5B is
> **CLOSED / MERGED / VERIFIED** through PR #418. INFRA-1 is
> **CLOSED / MERGED / VERIFIED** through PR #419. Post-INFRA-1 repairs
> (PR #420, #422, #423, #424) and maintenance releases (`v3.7.12`, `v3.7.13`
> on `release/3.7`) are merged. Gates P38-G0 (PR #429), P38-G1 (PR #430),
> and P38-G2 (PR #431) are closed and verified. Phase 5C SearchScope
> pushdown (PR #434) is **CLOSED / VERIFIED AFTER R1 CORRECTION (PR #437)**.
> P38-WP01-R1 is **CLOSED / MERGED / VERIFIED**.
> Phase 5D (P38-WP02) is **CLOSED / MERGED / VERIFIED (PR #439 / PR #440)**.
> Phase 5E (P38-WP03) is **READY FOR SEPARATE ADMISSION / NOT STARTED**.

> Links to `artifacts/` are GitHub evidence permalinks intentionally outside
> the MkDocs navigation tree; they are not local documentation targets.

### Recovery procedure

To recover the current POWER 3.8 state:

1. Read `POWER_3.8_CURRENT_STATE.md`.
2. Read `POWER_3.8_EXECUTION_ROADMAP.md`.
3. Read `POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
4. Read `POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md` and the planning-artifacts
   README.
5. Read the latest append-only INFRA-1 handoff; classify the Phase 5B and HF
   handoffs as historical evidence.
6. Fetch current GitHub `main`, the closed gate dispositions, required checks,
   reviews, rulesets, and protected-branch policy independently through the
   authenticated REST API.
7. Verify every documented SHA and mutable status, including any candidate's
   exact head, required checks, reviews, and protected-branch policy, before
   acting or attempting a new gate action.
8. Treat this snapshot as repository governance memory and live GitHub as
   mutable operational truth. Verify the Phase 5D candidate and its exact
   protected merge/readback; then stop before Phase 5E.

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

These files remain **PLANNING EVIDENCE** and are not production runtime
dependencies. Phase 5A has an independent installable runtime contract layer
and frozen synthetic evaluation corpus; the v1 context schema and v1 index-cost
policy remain retained historical planning evidence. No planning contract is a
phase report, release artifact, or authorization to start Phase 5E.

## CONTRACT STATUS MAP

| Classification | Meaning | Current examples |
|---|---|---|
| ACTIVE GOVERNANCE | Current repository-state projection | Current state, roadmap, protocol |
| CURRENT PLANNING | Active future design, not runtime | Architecture plan, v2 contracts |
| SUPERSEDED PLANNING CONTRACT | Retained v1 evidence; not future implementation authority | v1 context schema, v1 index policy |
| HISTORICAL EVIDENCE | Immutable prior gate or stale candidate record | Prior handoffs, closed #407 evidence |
| PHASE EVIDENCE | Executed proof for a named phase/gate | Phase reports and receipts |
| ARCHITECTURAL DECISION | Durable decision requiring an ADR | `docs/adr/` records |
| NEXT RUNTIME GATE | Authorized sequence position, not implementation | Phase 5E (P38-WP03 Shadow Benchmark / Legacy Comparison) |

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

HF #406, Actions #396, final-integration checks, and Foundation PR #414 remain
attached to their PR, commit, and handoff evidence. The context/memory/retrieval
files under `artifacts/project-state/planning/` remain planning contracts, not
runtime dependencies. The final dependency and Foundation evidence is `MERGED
MAIN`; Phase 5A runtime contracts and Phase 5A.1 are merged and verified,
Phase 5B is `CLOSED / MERGED / VERIFIED` through PR #418, INFRA-1 is
`CLOSED / MERGED / VERIFIED` through PR #419, Phase 5C SearchScope
pushdown is `CLOSED / MERGED / VERIFIED` through PR #434 and PR #437,
and Phase 5D (RetrievalPlanner + ContextPack) is `CLOSED / MERGED / VERIFIED`
through PR #439 and PR #440. Phase 5E remains `READY FOR SEPARATE ADMISSION / NOT STARTED`.

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
not runtime completion. This canonical projection records the closed Controlled
Dependency Refresh, the v2 planning successor, the closed Phase 5A/5A.1/5B/5C/5D
gates, and the merged INFRA-1 broker. It does not authorize Actions #396,
Phase 5E, any later phase, version bump, tag, release, or `POWER 3.8.0`
publication.
