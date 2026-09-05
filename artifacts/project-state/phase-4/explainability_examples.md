# POWER Project State Engine Phase 4 — Explainability Trace Examples

This document demonstrates the deterministic explainability traces produced by `ProjectStateReducer.explain(state, field)` (Gate G4.6).

Every explainability record binds:
- `project_id`: Target canonical project identifier
- `field`: The queried state property
- `state_revision`: Exact cryptographic hash of the state
- `value`: Current materialized value of the field
- `contributing_event_ids`: Chronological list of causal ledger events
- `applicable_rules`: Versioned governance or lifecycle rules that produced the value
- `decision_references`: Related Decision IDs
- `evidence_references`: Audit and verification evidence tokens
- `authority_references`: Authoritative source subsystem (`TaskStore:v2`, `DecisionService:v1`, etc.)

---

## 1. Field: `current_phase`

```json
{
  "project_id": "prj_syn_alpha",
  "field": "current_phase",
  "state_revision": "4f8a91c7b2e35a6d90f14892c53a71b802de9a13b4cf7102e3a51809cb2d41fa",
  "value": "EXECUTION",
  "contributing_event_ids": [
    "evt_01J8F90A11B2C3D4E5F60001",
    "evt_01J8F90A11B2C3D4E5F60002",
    "evt_01J8F90A11B2C3D4E5F60005"
  ],
  "applicable_rules": [
    "FSM_RULE:DISCOVERY->PLANNING:advance_to_planning",
    "FSM_RULE:PLANNING->EXECUTION:start_execution"
  ],
  "decision_references": [
    "dec_approval_execution_kickoff_01"
  ],
  "evidence_references": [
    "evi_charter_signoff_2026",
    "evi_dor_planning_checklist_passed"
  ],
  "authority_references": [
    "ProjectLifecycleFSM:v1"
  ]
}
```

*Explanation Summary:*
Project advanced from `DISCOVERY` through `PLANNING` into `EXECUTION` via events `evt_...0002` and `evt_...0005`. The transition satisfied `dor_planning_to_execution` with charter sign-off and DoR checklist evidence, approved under decision `dec_approval_execution_kickoff_01`.

---

## 2. Field: `blocked_tasks`

```json
{
  "project_id": "prj_syn_alpha",
  "field": "blocked_tasks",
  "state_revision": "4f8a91c7b2e35a6d90f14892c53a71b802de9a13b4cf7102e3a51809cb2d41fa",
  "value": [
    "task_build_api_gateway",
    "task_deploy_staging_cluster"
  ],
  "contributing_event_ids": [
    "evt_01J8F90A11B2C3D4E5F60003",
    "evt_01J8F90A11B2C3D4E5F60004",
    "evt_01J8F90A11B2C3D4E5F60008"
  ],
  "applicable_rules": [
    "TASK_BLOCKED_BY_DEPENDENCY_OR_CYCLE"
  ],
  "decision_references": [],
  "evidence_references": [],
  "authority_references": [
    "TaskStore:v2"
  ]
}
```

*Explanation Summary:*
`task_build_api_gateway` is blocked because its dependency `task_setup_schema` is non-terminal. `task_deploy_staging_cluster` is blocked by open gate `gate_security_review`.

---

## 3. Field: `open_risks`

```json
{
  "project_id": "prj_syn_alpha",
  "field": "open_risks",
  "state_revision": "4f8a91c7b2e35a6d90f14892c53a71b802de9a13b4cf7102e3a51809cb2d41fa",
  "value": [
    "rsk_upstream_rate_limit"
  ],
  "contributing_event_ids": [
    "evt_01J8F90A11B2C3D4E5F60006",
    "evt_01J8F90A11B2C3D4E5F60009"
  ],
  "applicable_rules": [
    "RISK_STATUS_IDENTIFIED"
  ],
  "decision_references": [],
  "evidence_references": [],
  "authority_references": [
    "PSE:RAID:v1"
  ]
}
```

*Explanation Summary:*
Risk `rsk_upstream_rate_limit` was opened in event `evt_...0006` and updated with mitigation plan in `evt_...0009`. Its current status remains `identified` with impact `high`.

---

## 4. Field: `valid_decisions`

```json
{
  "project_id": "prj_syn_alpha",
  "field": "valid_decisions",
  "state_revision": "4f8a91c7b2e35a6d90f14892c53a71b802de9a13b4cf7102e3a51809cb2d41fa",
  "value": [
    "dec_approval_execution_kickoff_01"
  ],
  "contributing_event_ids": [
    "evt_01J8F90A11B2C3D4E5F60007"
  ],
  "applicable_rules": [
    "DECISION_STATUS_APPROVED"
  ],
  "decision_references": [
    "dec_approval_execution_kickoff_01"
  ],
  "evidence_references": [
    "dcr_883a2bf9104c81a28cf1204859a01d672839401bf5829104fa281048bcae9021"
  ],
  "authority_references": [
    "DecisionService:v1"
  ]
}
```

*Explanation Summary:*
`dec_approval_execution_kickoff_01` is approved with receipt `dcr_883...`. `dec_select_database_engine` remains pending and appears under `required_approvals`, not `valid_decisions`.

---

## 5. Field: `required_approvals`

```json
{
  "project_id": "prj_syn_alpha",
  "field": "required_approvals",
  "state_revision": "4f8a91c7b2e35a6d90f14892c53a71b802de9a13b4cf7102e3a51809cb2d41fa",
  "value": [
    "dec_select_database_engine"
  ],
  "contributing_event_ids": [
    "evt_01J8F90A11B2C3D4E5F60010"
  ],
  "applicable_rules": [
    "PENDING_DECISION_REQUIRES_APPROVAL"
  ],
  "decision_references": [
    "dec_select_database_engine"
  ],
  "evidence_references": [],
  "authority_references": [
    "DecisionService:v1"
  ]
}
```

*Explanation Summary:*
`dec_select_database_engine` is registered in `state.decisions` with status `pending`. It blocks downstream schema provisioning until approved.

---

## 6. Field: `health_flags`

```json
{
  "project_id": "prj_syn_alpha",
  "field": "health_flags",
  "state_revision": "4f8a91c7b2e35a6d90f14892c53a71b802de9a13b4cf7102e3a51809cb2d41fa",
  "value": [
    "BLOCKED_TASKS_PRESENT",
    "HIGH_RISKS_OPEN",
    "UNRESOLVED_GOVERNANCE_REQUIREMENTS"
  ],
  "contributing_event_ids": [
    "evt_01J8F90A11B2C3D4E5F60006",
    "evt_01J8F90A11B2C3D4E5F60008",
    "evt_01J8F90A11B2C3D4E5F60010"
  ],
  "applicable_rules": [
    "HEALTH_RULES_V1"
  ],
  "decision_references": [],
  "evidence_references": [],
  "authority_references": [
    "GovernanceEngine:v1"
  ]
}
```

*Explanation Summary:*
Health indicators evaluated deterministically:
1. `BLOCKED_TASKS_PRESENT`: 2 blocked tasks currently in state.
2. `HIGH_RISKS_OPEN`: `rsk_upstream_rate_limit` has impact `high`.
3. `UNRESOLVED_GOVERNANCE_REQUIREMENTS`: 1 pending decision requires resolution.
