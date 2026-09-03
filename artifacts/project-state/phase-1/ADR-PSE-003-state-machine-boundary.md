# ADR-PSE-003: Project Lifecycle State Machine Boundary and Transition Invariants

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** Project management in agentic and hybrid environments frequently suffers from "zombie projects" or undefined project states where work occurs without planning, or projects never formally close.

## Context and Problem Statement
Projects in POWER need a formal, deterministic lifecycle engine. We must prevent agents or users from jumping arbitrarily between states (e.g. from `DISCOVERY` straight into `CLOSING` without execution), or bypassing quality gates (DoR / DoD). The state machine must be machine-testable and mathematically closed.

## Decision Drivers
- Strict governance of project evolution.
- Enforcing preconditions and machine-evaluable quality gates prior to phase advancement.
- Explicit audit trail for rollbacks, replanning, and emergency overrides.
- Prevention of unvalidated or hallucinated phase transitions by AI agents.

## Decision Outcome
Chosen Solution: **Formal 6-State FSM with Gate Enforcement and Explicit Reversal Semantics**.

### State Taxonomy:
```text
[DISCOVERY] ──> [PLANNING] ──> [EXECUTION] <──> [MONITORING]
     │              │               │                 │
     │              │               v                 v
     │              │          [CLOSING] <────────────┘
     │              │               │
     v              v               v
    └───────────> [CLOSED] <────────┘
                    │   ^
                    └───┘ (Reopen: CLOSED -> PLANNING / EXECUTION)
```

### Invariants and Transition Rules:
1. **Event-Driven Transition:** Project phase can NEVER be altered by directly modifying a state field. A phase change requires emitting a validated `project.phase.changed` event.
2. **Transition Validation Table:** All transitions are strictly validated against `lifecycle-v1.json`. Any transition not explicitly listed in the transition table raises `IllegalStateTransitionError`.
3. **Precondition and Quality Gate Enforcement:**
   - Advancement from `PLANNING` to `EXECUTION` requires passing the **Definition of Ready (DoR)** gate or registering a formally approved override.
   - Advancement from `CLOSING` to `CLOSED` requires 100% passage of the **Definition of Done (DoD)** gate, terminal status on all related tasks, and recorded completion receipts.
4. **Rollback & Reopen Semantics:**
   - Transitions marked `is_rollback: true` (e.g. `EXECUTION -> PLANNING` for replanning) require mandatory justification metadata in the event payload.
   - Reopening a `CLOSED` project requires an explicit `project.reopened` event accompanied by accountable human or executive agent approval evidence.
5. **No Terminal Mutation:** When a project is `CLOSED`, no RAID items, RACI mappings, or task associations may be modified without formally reopening the project.

## Consequences
### Positive
- Projects follow a predictable, orderly lifecycle with verifiable artifacts at each phase.
- Agents cannot declare a project finished without meeting objective DoD criteria.
- Complete historical visibility into project pauses, replanning loops, or cancellations.

### Negative
- Adds strictness to agile ad-hoc changes: developers must fulfill DoR/DoD conditions or explicitly log an override.
