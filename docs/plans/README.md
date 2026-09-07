# POWER Planning Index

This directory is the navigation index for POWER 3.8 planning and execution
evidence. It does not replace live GitHub state, exact Git objects, signed
commits, branch protection, or authoritative phase reports.

## ACTIVE GOVERNANCE

The following files are the active **blocked-state recovery projection** in this
publication branch:

- [POWER 3.8 — Current State](POWER_3.8_CURRENT_STATE.md)
- [POWER 3.8 — Execution Roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [POWER 3.8 — Development Protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Project-state handoff protocol](../../artifacts/project-state/handoffs/README.md)
- [Latest blocked-state handoff](../../artifacts/project-state/handoffs/2026-09-07T234711Z_hf-406_pre-merge-blocked.md)

> These documents are published for recovery because the HF gate is blocked.
> They are **not** the post-HF canonical governance bootstrap and must not be
> called `MERGED MAIN` evidence until a protected merge establishes that state.

### Recovery procedure

To recover the current POWER 3.8 state:

1. Read `POWER_3.8_CURRENT_STATE.md`.
2. Read `POWER_3.8_EXECUTION_ROADMAP.md`.
3. Read `POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
4. Read the latest append-only handoff.
5. Fetch current GitHub `main` and PR #406 independently through REST API.
6. Verify every documented SHA and mutable status before acting.
7. Work only on the current HF admission gate; do not start Actions #396 or
   Phase 5.

## HISTORICAL PLAN

The existing dated plans below are retained as historical context. Their
presence does not make them current authority:

- [2026-07-14 POWER Framework v2](2026-07-14-power-framework-v2.md)
- [2026-07-23 POWER 3.2 WTF remediation](2026-07-23-power-3.2-wtf-remediation.md)
- [2026-07-24 multi-methodology expansion](2026-07-24-multi-methodology-expansion-plan.md)
- [Issue 187 production validation checklist](issue-187-production-validation-checklist.md)

No historical plan is deleted or silently reinterpreted by this index.

## PHASE EVIDENCE

Phase reports, receipts, schemas, and replay artifacts under
`../../artifacts/project-state/` are evidence for the phase or gate they name.
They are not a substitute for current-state projection or live GitHub truth:

- [Phase 4 verification report](../../artifacts/project-state/phase-4/PHASE_4_REPORT.md)
- [Dependency refresh ledger](../../artifacts/repository-cleanup/dependency-refresh-ledger.md)

HF #406 remote checks and exact commit evidence remain attached to the PR and
commit links in the latest handoff. They are `REMOTE EXACT-HEAD`, not `MERGED
MAIN`, evidence.

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
```

This publication branch is **EVIDENCE** for the blocked HF gate. It does not
authorize any dependency, phase, version, tag, release, or governance merge.
