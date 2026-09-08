# POWER Planning Index

This directory is the navigation index for POWER 3.8 planning, architecture,
and execution governance. It does not replace live GitHub state, exact Git
objects, signed commits, branch protection, or authoritative phase reports.

## ACTIVE GOVERNANCE

The following files form the active **post-HF next-gate and architecture
planning projection**. The post-HF state files are canonical on `main`; the
new architecture package is provisional on this branch and becomes canonical
planning only after its protected merge:

- [POWER 3.8 — Current State](POWER_3.8_CURRENT_STATE.md)
- [POWER 3.8 — Execution Roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [POWER 3.8 — Development Protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [POWER 3.8 — Context / Memory / Retrieval Architecture](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Project-state handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Latest architecture handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T140647Z_context-memory-architecture_planned.md)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)

> Governance PRs #408, #409, #410, #411, and HF PR #406 are merged on
> protected `main`. The context/memory/retrieval package has **APPROVED
> PLANNING DIRECTION** on this candidate branch and becomes **CANONICAL
> PLANNING** only after its protected merge. Actions #396 is the next
> independent gate and remains HOLD. None of these paths authorizes a release
> or runtime implementation.

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
6. Fetch current GitHub `main`, merged PRs #408/#409/#410/#411/#406, and the
   open Actions PR #396 independently through authenticated REST API.
7. Verify every documented SHA and mutable status, including each candidate's
   exact head, required checks, reviews, and protected-branch policy, before
   acting or attempting a new gate action.
8. Treat HF #406 and post-HF governance as `MERGED MAIN` evidence. Work only on
   the next Actions #396 admission gate in a later bounded session; do not start
   it from this handoff.

## ACTIVE ARCHITECTURE PLANNING

The following package is the active POWER 3.8 context, memory, and retrieval
planning direction:

- [Human-readable architecture plan](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Planning artifacts README](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Context/retrieval contracts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/context-retrieval-contracts-v1.schema.json)
- [Index cost policy](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/index-cost-policy-v1.json)
- [Domain Policy v2 example](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/domain-policy-v2.example.yaml)
- [Phase 5–9 acceptance gates](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/phase5-9-acceptance-gates.md)

These files are **PLANNED**, not implemented runtime behavior. A planning
contract is not a phase report, a release artifact, or authorization to start
Phase 5.

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

HF #406 remote checks and exact merge evidence remain attached to the PR and
commit links in the historical HF handoff. The context/memory/retrieval files
under `artifacts/project-state/planning/` are pre-implementation planning
contracts, not phase evidence. The final dependency evidence is `MERGED MAIN`;
Actions #396 remains `HOLD / NOT STARTED`.

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
not runtime completion. This canonical projection records the closed HF gate,
the merged post-HF governance state, and the next Actions admission. It does
not authorize Actions #396, any later phase, version bump, tag, release, or
`POWER 3.8.0` publication.
