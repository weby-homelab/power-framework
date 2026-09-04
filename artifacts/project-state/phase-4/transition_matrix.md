# POWER Project State Engine Phase 4 — Transition Matrix

## 1. Overview

The POWER Project State Engine (PSE) implements a mathematically formal 6-state Finite State Machine (FSM) governed by `artifacts/project-state/phase-1/lifecycle-v1.json` and executed deterministically by `GovernanceEngine`.

Under **Gate G4.5**, all transitions not explicitly defined in this matrix are illegal and **fail closed** with `IllegalStateTransitionError` and reason code `ILLEGAL_LIFECYCLE_TRANSITION`.

Under **Gate G4.2 (P0-1)**, no LLM or unverified semantic candidate (`source == "model_extraction"`, `verification_status == "proposed"`) can directly or indirectly trigger a state transition.

---

## 2. Formal 6-State Lifecycle Taxonomy

| Phase | Description | Is Terminal | Normal Mutations Blocked | Reopen Semantics |
| :--- | :--- | :---: | :---: | :---: |
| **`DISCOVERY`** | Initial ideation, charter drafting, objective definition | No | No | N/A |
| **`PLANNING`** | Work breakdown, architecture, task mapping, DoR gate | No | No | Reopen target |
| **`EXECUTION`** | Active task execution, code generation, delivery | No | No | Reopen target |
| **`MONITORING`** | Progress checkpoints, health telemetry, quality reviews | No | No | N/A |
| **`CLOSING`** | Postconditions, DoD gate evaluation, completion receipts | No | No | N/A |
| **`CLOSED`** | Sealed terminal state; mutations blocked | Yes | **Yes** | Explicit `project.reopened` required |

---

## 3. The 17 Legal Directed Transitions

| # | From Phase | To Phase | Transition Name | Required Gate | Approval Req. | Evidence Req. | Rollback / Reopen | Reason Codes / Preconditions |
| :-: | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| 1 | `DISCOVERY` | `PLANNING` | `advance_to_planning` | `dor_discovery_to_planning` | No | Yes | No | `charter_present`, `owner_assigned` |
| 2 | `DISCOVERY` | `CLOSED` | `cancel_during_discovery` | None | Yes | Yes | No | `cancellation_reason_provided` |
| 3 | `PLANNING` | `EXECUTION` | `start_execution` | `dor_planning_to_execution` | Yes | Yes | No | `dor_passed_or_overridden`, `raci_accountable_assigned`, `initial_tasks_registered` |
| 4 | `PLANNING` | `DISCOVERY` | `revert_to_discovery` | None | Yes | Yes | **Yes** | `reversion_justification_recorded` |
| 5 | `PLANNING` | `CLOSED` | `cancel_during_planning` | None | Yes | Yes | No | `cancellation_reason_provided` |
| 6 | `EXECUTION` | `MONITORING` | `enter_monitoring` | None | No | No | No | Periodic steady-state checkpoint |
| 7 | `EXECUTION` | `PLANNING` | `replanning_from_execution` | None | Yes | Yes | **Yes** | `replanning_justification_recorded` |
| 8 | `EXECUTION` | `CLOSING` | `begin_closing` | `dod_execution_to_closing` | No | Yes | No | `all_tasks_terminal`, `no_blocking_issues` |
| 9 | `EXECUTION` | `CLOSED` | `abort_execution` | None | Yes | Yes | No | `termination_reason_recorded` |
| 10 | `MONITORING` | `EXECUTION` | `resume_active_execution` | None | No | No | No | Resume implementation |
| 11 | `MONITORING` | `PLANNING` | `replanning_from_monitoring` | None | Yes | Yes | **Yes** | `replanning_justification_recorded` |
| 12 | `MONITORING` | `CLOSING` | `conclude_from_monitoring` | `dod_execution_to_closing` | No | Yes | No | `all_tasks_terminal`, `no_blocking_issues` |
| 13 | `MONITORING` | `CLOSED` | `terminate_from_monitoring` | None | Yes | Yes | No | `termination_reason_recorded` |
| 14 | `CLOSING` | `EXECUTION` | `reject_closing_to_execution` | None | No | Yes | **Yes** | `closing_failure_reason_recorded` |
| 15 | `CLOSING` | `CLOSED` | `finalize_close` | `dod_final_closing` | Yes | Yes | No | `dod_passed_or_overridden`, `all_tasks_terminal`, `all_decisions_resolved`, `all_issues_resolved_or_waived` |
| 16 | `CLOSED` | `PLANNING` | `reopen_to_planning` | None | Yes | Yes | **Yes** | `reopen_justification_recorded`, `accountable_approval` |
| 17 | `CLOSED` | `EXECUTION` | `reopen_to_execution` | None | Yes | Yes | **Yes** | `reopen_justification_recorded`, `accountable_approval` |

---

## 4. Prohibited Transitions (Sample Fail-Closed Invariants)

All 19 non-listed directed pairs are strictly prohibited and fail closed.

| Attempted Transition | Legal? | Rejection Reason Code | Rationale |
| :--- | :---: | :--- | :--- |
| `DISCOVERY -> EXECUTION` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Work cannot start without passing the Planning phase and DoR gate. |
| `DISCOVERY -> CLOSING` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Cannot close un-executed work without formal cancellation. |
| `PLANNING -> CLOSING` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Cannot claim closing without active execution deliverables. |
| `EXECUTION -> DISCOVERY` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | In-progress execution must replan via `PLANNING` first. |
| `MONITORING -> DISCOVERY` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Must route replanning through `PLANNING`. |
| `CLOSING -> DISCOVERY` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Rejected closing deliverables must return to `EXECUTION`. |
| `CLOSING -> PLANNING` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Rework must return to `EXECUTION`. |
| `CLOSED -> DISCOVERY` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Reopening a closed project is only permitted into `PLANNING` or `EXECUTION`. |
| `CLOSED -> MONITORING` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Cannot monitor a closed project without active work. |
| `CLOSED -> CLOSING` | **No** | `ILLEGAL_LIFECYCLE_TRANSITION` | Already closed. |

---

## 5. Rollback & Reopen Semantics

1. **Append-Only Invariant:**
   Rollbacks never delete or mutate prior events in the ledger. A rollback or replanning is recorded as a new `project.phase.changed` event with `is_rollback: true`.
2. **Mandatory Justification:**
   Transitions 4, 7, 11, 14, 16, 17 require non-empty justification (`reason`, `reopen_justification`, or `replanning_justification`) in the event payload. Omission fails closed with `MISSING_TRANSITION_REASON`.
3. **Reopening CLOSED Projects:**
   Requires an explicit `project.reopened` event, accompanied by accountable approval evidence. Regular `project.phase.changed` events on a closed project fail closed with `CLOSED_PROJECT_REQUIRES_EXPLICIT_REOPEN`.

---

## 6. Gate Overrides (`gate.overridden`)

- Permitted only for authorized roles: `admin`, `architect`, `lead`, `accountable`.
- Must provide non-empty justification `reason` and non-empty `evidence_ref`.
- **Untrusted / model proposals strictly prohibited:** Model-derived events attempting `gate.overridden` are rejected fail-closed with `UNTRUSTED_MODEL_OVERRIDE_PROHIBITED` (Gate G4.2 / P0-3).
