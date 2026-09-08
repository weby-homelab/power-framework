# POWER Planning Index

This directory is the navigation index for POWER 3.8 planning and execution
evidence. It does not replace live GitHub state, exact Git objects, signed
commits, branch protection, or authoritative phase reports.

## ACTIVE GOVERNANCE

The following files are the active **post-HF next-gate projection** in the
canonical `main` tree:

- [POWER 3.8 — Current State](POWER_3.8_CURRENT_STATE.md)
- [POWER 3.8 — Execution Roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [POWER 3.8 — Development Protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Project-state handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Latest HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)

> Governance PR #408, state PR #409, CI repair PR #410, and HF PR #406 are
> merged on protected `main`. Actions #396 is the next gate and remains HOLD;
> these paths are canonical memory for the merged dependency state, not release
> authorization.

> Links to `artifacts/` are GitHub evidence permalinks intentionally outside
> the MkDocs navigation tree; they are not local documentation targets.

### Recovery procedure

To recover the current POWER 3.8 state:

1. Read `POWER_3.8_CURRENT_STATE.md`.
2. Read `POWER_3.8_EXECUTION_ROADMAP.md`.
3. Read `POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
4. Read the latest append-only handoff.
5. Fetch current GitHub `main`, merged PRs #408/#409/#410/#406, and the open
   Actions PR #396 independently through authenticated REST API.
6. Verify every documented SHA and mutable status, including each candidate's
   exact head, required checks, reviews, and protected-branch policy, before
   acting or attempting a new gate action.
7. Treat HF #406 as `MERGED MAIN` evidence. Work only on the next Actions #396
   admission gate in a later bounded session; do not start it from this handoff.

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
commit links in the latest handoff. The final dependency evidence is
`MERGED MAIN`; Actions #396 remains `HOLD / NOT STARTED`.

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

This canonical projection records the closed HF gate and the next Actions
admission. It does not authorize Actions #396, any later phase, version bump,
tag, release, or `POWER 3.8.0` publication.
