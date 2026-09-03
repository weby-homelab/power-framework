# POWER Project State Engine (PSE) — Phase 1 Domain Model & Architecture Contract

- **Framework Version:** POWER 3.8 (Draft)
- **Status:** APPROVED / FROZEN CONTRACT
- **Date:** 2026-09-03
- **Author:** Weby Homelab & POWER Architecture Guild

---

## Executive Summary & Purpose
This document establishes the binding architectural contract for the **POWER Project State Engine (PSE)**. It provides a formal, machine-testable domain model for project lifecycle governance, RAID logging, RACI allocation, and automated quality gating. All implementation in subsequent phases (Storage, Ingestion, CLI, Web surfaces) must strictly adhere to the contracts defined herein.

---

## 1. Canonical Authority Matrix Inheritance
PSE directly inherits the authority boundaries established in Phase 0 (`artifacts/project-state/phase-0/authority_matrix.md`):

| Domain Entity | Canonical Authoritative Subsystem | Canonical Storage Location |
| :--- | :--- | :--- |
| **Markdown Notes & Docs** | `Vault Mutation Boundary` (`mutation.py`) | Obsidian root (`01_Projects/`, etc.) |
| **Tasks (`PowerTask v2`)** | `TaskService` / `TaskStore` (`task_store.py`) | `.power/tasks/<task_id>.json` & `.power/tasks/events.jsonl` |
| **Decisions (`Decision v1`)** | `DecisionService` (`decision_service.py`) | `.power/decisions/<decision_id>.json` |
| **Project State & Events** | **Project State Engine (PSE)** | `.power/projects/<project_id>/events.jsonl` |
| **RAID & RACI Entities** | **Project State Engine (PSE)** | Projected from `.power/projects/<project_id>/events.jsonl` |
| **Quality Gates (DoR/DoD)** | **Project State Engine (PSE)** | Evaluated from live subsystem state, logged to PSE ledger |

**Non-Ambiguity Invariant:** PSE NEVER acts as a shadow authority for tasks or decisions. Tasks are owned exclusively by `TaskStore`; decisions are owned exclusively by `DecisionService`.

---

## 2. Project Identity Contract
Project identity is decoupled from filesystem folder names, display titles, or file paths.

1. **Stable Identifier (`project_id`):**
   - Syntax: `^prj_[a-z0-9][a-z0-9_-]{2,63}$`
   - Example: `prj_power_3_8_pse`, `prj_vault_migration_2026`
   - Invariant: Immutable once assigned. Never changes across renames, relocations, or archiving.
2. **Creation Protocol:**
   - Emits `project.created` event as sequence `1` (genesis event).
   - Establishes `project_id`, slug, title, owner, and initial state (`DISCOVERY`).
   - Generates directory `.power/projects/<project_id>/`.
3. **Discovery Protocol:**
   - Filesystem scanner locates all `.power/projects/<project_id>/` directories.
   - Project metadata and current state are discovered by reading the project snapshot or replaying `events.jsonl`.
   - Vault notes in `01_Projects/` link to their project via frontmatter key `project_id: prj_...`.
4. **Rename Protocol:**
   - Changing the display name or title emits `project.renamed` (or `project.updated`).
   - The underlying `project_id` remains strictly unchanged.
5. **Move / Relocation Protocol:**
   - Moving the human-authored documentation folder within the Obsidian vault (e.g. from `01_Projects/Active/` to `01_Projects/Archive/`) emits `project.relocated`.
   - The ledger records the new relative `vault_path`. No internal event files or `project_id` values are modified.
6. **Archival Protocol:**
   - When a project transitions to `CLOSED` or is explicitly archived, PSE records `project.phase.changed` or `project.archived`.
   - The event stream remains permanently stored and verifiable in `.power/projects/<project_id>/events.jsonl`.
7. **Collision Handling:**
   - Creation of a project with an already existing `project_id` is rejected at the ledger initialization level under lock with `ProjectAlreadyExistsError`.

---

## 3. Project↔Task and Project↔Decision Relation Contract
PSE coordinates with tasks and decisions through typed relational bindings, strictly avoiding data duplication:

1. **Referential Integrity:**
   - A project references tasks via foreign keys (`task_id`) in `task_refs` and `dependencies`.
   - A project references decisions via foreign keys (`decision_id`) in `decision_refs` and `dependencies`.
2. **No Model Duplication:**
   - PSE does not duplicate `title`, `state`, `lease_owner`, or `execution_state` inside canonical project records.
3. **Event-Driven Linking:**
   - When an existing task is bound to a project, PSE emits:
     ```json
     {
       "event_type": "task.associated",
       "payload": {
         "task_id": "tsk_build_core_engine",
         "relation": "milestone_deliverable"
       }
     }
     ```
4. **Dynamic Status Resolution:**
   - To check whether all tasks for a milestone or project phase are completed, PSE queries `TaskStore` directly using `TaskStore.get_task(task_id)` or joins against the synchronized SQLite task projection.
5. **Disassociation & Deletion:**
   - Deleting or canceling a task in `TaskStore` leaves the PSE historical reference intact. The state machine interprets missing or cancelled tasks according to DoD validation rules.

---

## 4. ProjectEvent v1 Canonical Serialization Contract
To guarantee deterministic cryptographic hashing and byte-for-byte reproducibility across languages and operating systems, all `ProjectEvent` records must follow strict canonical serialization rules.

1. **JSON Encoding:**
   - UTF-8 encoding without Byte Order Mark (BOM).
   - Keys sorted lexicographically at all nesting levels (`sort_keys=True`).
   - Minimal compact whitespace separators: `(',', ':')` without trailing spaces.
   - Non-ASCII characters preserved without escaping (`ensure_ascii=False`).
2. **Timestamp Formatting:**
   - Strict RFC 3339 / ISO 8601 representation in UTC.
   - Format: `YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
   - Local offsets (e.g. `+03:00`) must be converted to UTC before serialization.
3. **Numeric and String Values:**
   - Sequences and counters must be integers.
   - Floating-point numbers are strictly forbidden in cryptographic header manifests to eliminate cross-platform precision drift.
   - `NaN`, `Infinity`, and `-Infinity` are rejected as invalid JSON.
4. **File Serialization:**
   - Each event is serialized as exactly one single line in `events.jsonl` terminated by an ASCII newline `\n` (`0x0A`).

---

## 5. ProjectEvent Integrity & Cryptographic Hash-Chain
As decided in `ADR-PSE-006`, PSE implements an envelope-binding cryptographic SHA-256 hash chain:

```text
Event 1 (Genesis, seq=1):
  prev_event_hash = ""
  payload_digest = SHA256(canonical_json(payload))
  event_hash = SHA256(canonical_json(header_manifest_1))

Event 2 (seq=2):
  prev_event_hash = Event 1.event_hash
  payload_digest = SHA256(canonical_json(payload))
  event_hash = SHA256(canonical_json(header_manifest_2))
```

- **Header Manifest Fields Included in `event_hash`:**
  `actor`, `event_id`, `event_type`, `payload_digest`, `prev_event_hash`, `project_id`, `schema_version`, `sequence`, `source`, `timestamp`.
- **Integrity Verification:**
  Replaying the event log recalculates `payload_digest` and `event_hash` for each line and confirms that `prev_event_hash == last_event_hash`. Any deviation signals data corruption or tampering.

---

## 6. Sequence, Order, and Idempotency Contract
1. **Strict Monotonic Sequence:**
   - The genesis event of a project has `sequence = 1`.
   - Each subsequent event must have `sequence = predecessor.sequence + 1`.
   - Any gap or duplicate sequence causes the append operation to fail with `SequenceOrderViolationError`.
2. **Concurrency Control:**
   - Appenders must hold the project-level lock (`.power/projects/<project_id>/.lock`).
   - Appenders check the current tail sequence before writing.
3. **Idempotency Deduplication:**
   - Callers may provide an optional `idempotency_key` or use deterministic `event_id`.
   - If an event with the same `idempotency_key` or `event_id` is appended again, PSE returns the previously committed event without creating a duplicate record.

---

## 7. Lock Hierarchy Contract
As codified in `ADR-PSE-007`, all processes must strictly follow the 3-level lock acquisition hierarchy:

```text
Level 1: .power/mutation.lock               (Vault note mutations)
  └── Level 2: .power/tasks/.lock           (TaskStore transactions)
        └── Level 3: .power/projects/<id>/.lock (PSE event ledger)
```

- **Ascending Acquisition Order:** Always acquire lower numbers first.
- **Descending Release Order:** Release higher numbers first.
- **Prohibition:** NEVER acquire Level 1 or Level 2 while holding Level 3.
- **Scope:** Level 3 is fine-grained per `project_id`.

---

## 8. Cross-Subsystem Transaction Semantics
As established in `ADR-PSE-008`:
1. **No Distributed 2PC:** PSE does not engage in distributed synchronous two-phase commits with other stores.
2. **Asynchronous / Reactive Coordination:** Primary operations complete in the authoritative service first; the linking event is appended to PSE subsequently.
3. **Failure Containment:** If PSE fails or crashes during a multi-subsystem workflow, the authoritative task or decision remains intact.

---

## 9. Failure Recovery and Reconciliation Contract
1. **Ledger Truncation Recovery:**
   - On boot, PSE inspects the tail of `events.jsonl`.
   - If an incomplete line or un-hashed fragment exists due to an abrupt shutdown, it is safely truncated to the last complete hashed record.
2. **Subsystem Reconciliation Engine:**
   - `reconcile_project_subsystems(project_id)` queries `TaskStore` and `DecisionService` to discover any unlinked items or resolve status drift.
   - Missing links are appended as synthetic idempotent events (`source: "reconciliation"`).
3. **Secondary Index Rebuild:**
   - If SQLite indexes or `snapshot.json` files are deleted or corrupted, `rebuild_from_events(project_id)` re-creates them from `events.jsonl` in seconds.

---

## 10. Temporal Truth Semantics
To eliminate ambiguity when processing asynchronous agent and human events, PSE distinguishes multiple temporal dimensions:

| Field | Meaning & Semantics |
| :--- | :--- |
| `created_at` | Physical UTC timestamp when the event or record was committed to the ledger. |
| `observed_at` | UTC timestamp when an external event, observation, or test execution was recorded by an agent or sensor. |
| `valid_from` | Domain-effective start timestamp of a plan, estimation, or fact. |
| `valid_to` | Domain-effective expiration timestamp (null if currently active). |
| `supersedes` | Entity ID or Decision ID that this current record legally replaces. |
| `invalidates` | Entity ID or Assumption ID that this current record disproves or renders void. |
| `confidence` | Numeric float from `0.0` to `1.0` indicating certainty (especially for agent-derived observations). |
| `verification_status` | Discrete epistemic status: `unverified`, `verified`, `refuted`, `quarantined`. |

---

## 11. Project Lifecycle State Machine
The project lifecycle comprises six formal states defined in `lifecycle-v1.json`:
`DISCOVERY` -> `PLANNING` -> `EXECUTION` -> `MONITORING` -> `CLOSING` -> `CLOSED`.

### Transition Matrix Summary:
- **`DISCOVERY -> PLANNING`**: Charter and objectives documented; owner assigned.
- **`PLANNING -> EXECUTION`**: Scope defined; initial tasks queued; **Definition of Ready (DoR)** passed or overridden.
- **`EXECUTION <-> MONITORING`**: Bidirectional active work and health assessment loop.
- **`EXECUTION / MONITORING -> CLOSING`**: Deliverables completed; all tasks terminal; no blocking issues.
- **`CLOSING -> CLOSED`**: **Definition of Done (DoD)** passed; final completion receipts verified; approval signed.
- **Rollback Transitions (`is_rollback = true`)**:
  - `PLANNING -> DISCOVERY`, `EXECUTION -> PLANNING`, `MONITORING -> PLANNING`, `CLOSING -> EXECUTION`.
  - Require formal justification metadata.
- **Reopening (`CLOSED -> PLANNING / EXECUTION`)**:
  - Requires executive accountable actor sign-off and logged justification.

---

## 12. RAID Entity Contracts
RAID items are managed as first-class typed domain entities:

1. **Risk (`rsk_...`):**
   - Probability: `low` | `medium` | `high`
   - Impact: `low` | `medium` | `high` | `critical`
   - Status: `identified` | `mitigated` | `materialized` | `retired`
   - Mandatory mitigation plan and assigned owner.
2. **Assumption (`asm_...`):**
   - Statement and rationale.
   - Confidence score (`0.0` to `1.0`).
   - Status: `valid` | `invalidated` | `confirmed`.
   - Invalidation records `invalidated_at` and `invalidated_by`.
3. **Issue (`iss_...`):**
   - Severity: `minor` | `major` | `critical` | `blocker`
   - Status: `open` | `investigating` | `resolved` | `closed`
   - Tracks `blocking_task_ids`. Blocker issues halt phase progression.
4. **Dependency (`dep_...`):**
   - Links `source_id` to `target_id`.
   - `target_type`: `task` | `decision` | `artifact` | `project` | `external`
   - `dependency_kind`: `blocks` | `blocked_by` | `relates_to` | `requires`
   - Status: `pending` | `satisfied` | `broken`.

---

## 13. RACI Semantics for Hybrid Human/Agent Fleets
1. **Responsible (R):** One or more actors (human `user:...` or agent `agent:...`) executing the deliverable.
2. **Accountable (A):** **Strictly exactly ONE actor.** Accountability cannot be shared. If an agent is designated as Accountable, it must be an executive or autonomous orchestrator agent, with ultimate liability resting on the vault owner.
3. **Consulted (C):** Subject matter experts or reviewer agents consulted prior to decisions.
4. **Informed (I):** Stakeholders notified upon milestone completion or phase change.

---

## 14. Definition of Ready (DoR) & Definition of Done (DoD) Rule Model
DoR and DoD are not informal text checklists; they are machine-evaluable rulesets:

1. **Rule Representation:**
   ```json
   {
     "rule_id": "dod_no_blocking_issues",
     "category": "dod",
     "phase": "CLOSING",
     "predicate_kind": "no_open_blockers",
     "predicate_params": {},
     "severity": "blocking"
   }
   ```
2. **Evaluation Protocol:**
   - Evaluator evaluates every rule in the gate suite against the live domain state.
   - Produces a `GateEvaluation` entity with overall status `passed` or `failed`.
3. **Override Semantics:**
   - If a blocking rule fails, an authorized actor may register an override with `overridden_by`, `justification`, and `approved_by`.
   - The override is permanently committed to the event ledger (`gate.overridden`).

---

## 15. Canonical vs Derived Storage Contract
1. **Canonical Primary Storage:**
   - Path: `.power/projects/<project_id>/events.jsonl`
   - Role: Immutable, append-only, cryptographic event ledger.
   - Lock: `.power/projects/<project_id>/.lock`.
2. **Derived Cache Storage:**
   - Snapshot: `.power/projects/<project_id>/snapshot.json`
   - Relational Index: `.power/project-state/indexes/project_state.sqlite3`
   - Obsidian Views: `01_Projects/<project>/status.md`
   - Rebuildability: 100% regenerable from `events.jsonl` at any time with zero data loss.
