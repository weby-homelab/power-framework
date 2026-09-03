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
| **Tasks (`PowerTask v2`)** | `TaskService` / `TaskStore` (`task_store.py`) | `.power/tasks/<task_id>.json` & `.power/tasks/events/<task_id>.jsonl` |
| **Decisions (`Decision v1`)** | `DecisionService` (`decision_service.py`) | `.power/tasks/decisions/<decision_id>.json` & receipts in `.power/tasks/decisions/receipts/` |
| **Project State & Events** | **Project State Engine (PSE)** | `.power/projects/<project_id>/events.jsonl` |
| **RAID & RACI Entities** | **Project State Engine (PSE)** | Projected from `.power/projects/<project_id>/events.jsonl` |
| **Semantic Entities (Fact, Hypo, Obs, Lesson)** | **Project State Engine (PSE)** | Projected from `.power/projects/<project_id>/events.jsonl` |
| **Quality Gates (DoR/DoD)** | **Project State Engine (PSE)** | Evaluated from live subsystem state, logged to PSE ledger |

**Non-Ambiguity & Federated Composed State Invariant:**
`.power/projects/<project_id>/events.jsonl` is the single canonical authority for domains owned by PSE (lifecycle state, RAID logs, RACI assignments, DoR/DoD quality gates, project relations, semantic entities). Task state remains authoritative in `TaskStore`. Decision approval state remains authoritative in `DecisionService`. The **Composed Project State** is a federated deterministic representation over these authoritative sources.

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
   - `PowerTask` has no `metadata` container; PSE does not assume any `metadata.project_id` in tasks.
3. **Association-Intent Saga Coordination (Zero 2PC):**
   - Associating a task:
     PSE emits `task.association.requested` (`project_id`, `task_id`, `relation`, `correlation_id`, `idempotency_key`).
     Upon validation with `TaskStore`, PSE records `task.associated` (or `task.association.failed`).
   - Associating a decision:
     PSE emits `decision.association.requested` (`project_id`, `decision_id`, `relation`, `correlation_id`, `idempotency_key`).
     Upon validation with `DecisionService`, PSE records `decision.associated` (or `decision.association.failed`).
4. **Dynamic Status Resolution & Observation:**
   - To check whether all tasks for a milestone or project phase are completed, PSE queries `TaskStore` directly using `TaskStore.get_task(task_id)` or joins against the synchronized SQLite task projection.
   - External state changes may be noted via `task.lifecycle.observed` and `decision.lifecycle.observed`.
5. **Disassociation & Deletion:**
   - When a link is severed, PSE emits `task.disassociated` or `decision.disassociated`.
   - Deleting or canceling a task in `TaskStore` leaves the PSE historical reference intact. The state machine interprets missing or cancelled tasks according to DoD validation rules.

---

## 4. ProjectEvent v1 Canonical Serialization Contract
To guarantee deterministic cryptographic hashing and byte-for-byte reproducibility across languages and operating systems, all `ProjectEvent` records must follow strict canonical serialization rules.

1. **Exact Schema Version Token:**
   - The canonical stored version identifier is strictly `"power.project-event.v1"`.
   - Dual serialized formats are prohibited in stored events. Legacy aliases (such as `"1.0"`) are accepted only at the ingress/upcaster boundary and normalized prior to storage.
2. **Authoritative Canonical JSON & Server-Side Hashing:**
   - All hashes (`event_hash`, `payload_digest`), monotonic sequences, and `prev_event_hash` pointers are generated by POWER under project lock, never chosen by clients. CLI and MCP clients submit Append Commands or Proposals.
   - The canonicalizer strictly implements RFC 8785 / JCS (JSON Canonicalization Scheme).
   - UTF-8 encoding without BOM, keys sorted lexicographically at all nesting levels (`sort_keys=True`), compact separators `(',', ':')`, non-ASCII preserved without escaping (`ensure_ascii=False`).
   - Floats are forbidden in envelope metadata; `NaN`, `Infinity`, and `-Infinity` are rejected fail-closed.
3. **Timestamp Formatting:**
   - Strict RFC 3339 / ISO 8601 representation in UTC.
   - Format: `YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
   - Local offsets (e.g. `+03:00`) must be converted to UTC before serialization.
4. **File Serialization:**
   - Each event is serialized as exactly one single line in `events.jsonl` terminated by an ASCII newline `\n` (`0x0A`).

---

## 5. ProjectEvent Integrity & Cryptographic Hash-Chain
As codified in `ADR-PSE-006`, PSE implements a full envelope-binding cryptographic SHA-256 hash chain:

```text
Event 1 (Genesis, seq=1):
  prev_event_hash = ""
  payload_digest = SHA256(canonical_json(payload))
  event_hash = SHA256(canonical_json(integrity_record_1))

Event 2 (seq=2):
  prev_event_hash = Event 1.event_hash
  payload_digest = SHA256(canonical_json(payload))
  event_hash = SHA256(canonical_json(integrity_record_2))
```

- **Full Envelope `integrity_record` Definition:**
  `integrity_record` is the canonical ProjectEvent dictionary excluding ONLY `event_hash`:
  ```python
  integrity_record = {k: v for k, v in event.items() if k != "event_hash"}
  event_hash = hashlib.sha256(canonical_json_dumps(integrity_record).encode("utf-8")).hexdigest()
  ```
  This seals all envelope fields: `actor`, `artifact_refs`, `causation_id`, `correlation_id`, `event_id`, `event_type`, `evidence_refs`, `idempotency_key`, `payload`, `payload_digest`, `prev_event_hash`, `project_id`, `schema_version`, `sequence`, `session_id`, `source`, and `timestamp`.
  Neither `evidence_refs` nor `artifact_refs` may be omitted from cryptographic sealing.
- **Two-Tier Verification:**
  1. `payload_digest == SHA256(canonical_json(payload))` verifies inner payload authenticity.
  2. `event_hash == SHA256(canonical_json(integrity_record))` verifies envelope immutability.
  3. Linear linkage: `event.prev_event_hash == predecessor.event_hash` (or `""` for genesis). Any mismatch signals tampering or corruption.

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
2. **Subsystem Reconciliation Engine (`reconcile_project_subsystems`):**
   - Eliminates reliance on non-existent `PowerTask.metadata`.
   - Scans the project ledger for unresolved `task.association.requested` and `decision.association.requested` saga intents.
   - Queries `TaskStore.get_task(task_id)` and `DecisionService.get_decision(decision_id)`.
   - If the entity exists, appends idempotent `task.associated` or `decision.associated` (`source: "reconciliation"`, `actor: "system:reconciler"`).
   - If missing after retry policy timeout, appends `task.association.failed` or `decision.association.failed`.
3. **Secondary Index Rebuild Semantics:**
   - If `project_state.sqlite3` contains purely PSE-owned state, rebuilding from `events.jsonl` is valid and complete.
   - If the global index also projects tasks and decisions, the rebuild routine is strictly required to read from all three authoritative sources: PSE `events.jsonl` + TaskStore (`.power/tasks/`) + DecisionService (`.power/tasks/decisions/`).

---

## 10. Temporal & Epistemic Truth Semantics
To eliminate ambiguity when processing asynchronous agent and human events, PSE distinguishes multiple temporal dimensions:

| Field | Meaning & Semantics |
| :--- | :--- |
| `created_at` | Physical UTC timestamp when the event or record was committed to the ledger. |
| `observed_at` | UTC timestamp when an external event, observation, or test execution was recorded by an agent or sensor. |
| `valid_from` | Domain-effective start timestamp of a plan, estimation, or fact. |
| `valid_to` | Domain-effective expiration timestamp (null if currently active). |
| `supersedes` | Entity ID or Decision ID that this current record legally replaces. |
| `invalidates` | Entity ID or Assumption ID that this current record disproves or renders void. |
| `confidence` | Numeric float from `0.0` to `1.0` indicating certainty (for probabilistic knowledge like Hypotheses and Observations). |
| `verification_status` | Epistemic status: `unverified`, `verified`, `refuted`, `quarantined`. |

**Multi-Event Provenance Contract:**
All semantic entities feature a mandatory `provenance` record tracking `source_event_ids: [event_id, ...]` (at least 1, unique), optional `primary_source_event_id`, `actor`, `timestamp`, `source_type`, optional `correlation_id`, and `evidence_refs`. Confidence is never forced onto deterministic entities.

---

## 11. Project Lifecycle State Machine
The project lifecycle comprises six formal states defined in `lifecycle-v1.json`:
`DISCOVERY` -> `PLANNING` -> `EXECUTION` -> `MONITORING` -> `CLOSING` -> `CLOSED`.

### Transition Invariants (Exactly 17 Legal Transitions):
The state machine strictly validates transitions against the 17 directed transitions declared in `lifecycle-v1.json`:
- **Forward Progression**: `DISCOVERY -> PLANNING`, `PLANNING -> EXECUTION`, `EXECUTION -> MONITORING`, `MONITORING -> EXECUTION`, `EXECUTION -> CLOSING`, `MONITORING -> CLOSING`, `CLOSING -> CLOSED`.
- **Cancellations & Terminations**: `DISCOVERY -> CLOSED`, `PLANNING -> CLOSED`, `EXECUTION -> CLOSED`, `MONITORING -> CLOSED`.
- **Rollbacks (`is_rollback = true`)**: `PLANNING -> DISCOVERY`, `EXECUTION -> PLANNING`, `MONITORING -> PLANNING`, `CLOSING -> EXECUTION`. Require recorded justification metadata.
- **Reopening (`CLOSED -> PLANNING`, `CLOSED -> EXECUTION`)**: Require accountable executive approval and logged justification.

### CLOSED State Semantics (Resolving Terminal Duality):
Rather than declaring `CLOSED` as an absorbing terminal state while permitting reopenings, the contract formalizes:
- `"is_closed": true`
- `"normal_mutations_blocked": true` (direct RAID, RACI, and task association mutations are rejected)
- `"requires_explicit_reopen": true` (only explicit `project.reopened` transitions to `PLANNING` or `EXECUTION` are allowed).

---

## 12. Semantic Domain Entities
Entities are versioned and validated against `semantic-entity-schema-v1.json`:

1. **RAID Entities:**
   - **Risk (`rsk_...`):** Probability (`low`/`medium`/`high`), Impact (`low`/`medium`/`high`/`critical`), Status (`identified`/`mitigated`/`materialized`/`retired`), mitigation plan, owner.
   - **Assumption (`asm_...`):** Statement, rationale, confidence (`0.0`-`1.0`), Status (`valid`/`invalidated`/`confirmed`).
   - **Issue (`iss_...`):** Severity (`minor`/`major`/`critical`/`blocker`), Status (`open`/`investigating`/`resolved`/`closed`). Blocker issues with status `open` or `investigating` are UNRESOLVED and halt phase progression.
   - **Dependency (`dep_...`):** Source and target links, target type (`task`/`decision`/`artifact`/`project`/`external`), kind (`blocks`/`blocked_by`/`relates_to`/`requires`), status (`pending`/`satisfied`/`broken`).
2. **Knowledge & Epistemic Entities:**
   - **Fact (`fct_...`):** Verified empirical assertion with verification method and timestamp.
   - **Hypothesis (`hyp_...`):** Testable proposition with confidence score, validation criteria, and status (`proposed`/`testing`/`validated`/`refuted`/`abandoned`).
   - **Observation (`obs_...`):** Contextual finding or sensor/agent observation with `observed_at`.
   - **Lesson (`lsn_...`):** Retrospective takeaway and actionable recommendation.
3. **Decision Reference Projection:**
   - **DecisionReference (`dref_...`):** References canonical `decision_id` from `DecisionService`, capturing project relation and synchronized status (`proposed`/`pending`/`accepted`/`rejected`/`superseded`). Never duplicates Decision models.

---

## 13. RACI Semantics for Hybrid Human/Agent Fleets
1. **Responsible (R):** One or more actors (human `user:...` or agent `agent:...`) executing deliverables.
2. **Accountable (A):** **Strictly exactly ONE actor.** Accountability cannot be shared.
3. **Consulted (C):** Subject matter experts or reviewer agents consulted prior to decisions.
4. **Informed (I):** Stakeholders notified upon milestone completion or phase change.

---

## 14. Definition of Ready (DoR) & Definition of Done (DoD) Rule Model
Quality gates are machine-evaluable rulesets:
1. **Evaluation Rules:**
   - `all_tasks_terminal`: checks all associated tasks against Task v2 canonical terminal states: `completed`, `failed`, `canceled`, `rejected`.
   - `no_open_blockers`: checks that zero issues with severity `blocker` have status not in `{"resolved", "closed"}` (investigating issues are blocked).
   - `receipt_present`, `assumption_validated`, `file_exists`, `metric_threshold`, `registered_policy`.
   - **Prohibition of Custom Scripts:** Arbitrary execution (`custom_script`) is strictly eliminated to prevent remote execution hazards. Dynamic rules must use `registered_policy`.
2. **Evaluation Protocol & Override:**
   - Produces a `GateEvaluation` entity with overall status `passed`, `failed`, or `overridden`.
   - Overrides require formal `overridden_by`, `justification`, and `approved_by` metadata, permanently committed to the ledger (`gate.overridden`).

---

## 15. Canonical vs Derived Storage Contract
1. **Canonical Primary Storage:**
   - Path: `.power/projects/<project_id>/events.jsonl`
   - Role: Immutable, append-only, cryptographic event ledger.
   - Lock: `.power/projects/<project_id>/.lock`.
2. **Derived Cache Storage:**
   - Snapshot: `.power/projects/<project_id>/snapshot.json`
   - Relational Index: `.power/project-state/indexes/project_state.sqlite3`
   - Vault Views: `<project.vault_path>/status.md` (contract-driven vault path, annotated with generation marker).
   - Rebuildability: 100% regenerable from canonical ledgers and subsystem stores.

---

## 16. Operational Privacy Profiles & Secret Sanitization
Codified in `ADR-PSE-005`:
1. **Three Explicit Privacy Modes:**
   - `metadata-only`: captures strictly operational envelopes and tool manifests.
   - `structured-events` (DEFAULT): agent dialogue is distilled in-memory into structured domain events; conversation buffer is purged immediately upon append. Raw dialogue is prohibited in `payload`.
   - `full-content` (Explicit Opt-In Only): sanitized conversation turns retained in a local-only raw-evidence store (`.power/raw-evidence/` with mode `0600`/`0700` and 14-day retention). NEVER stored in event payloads, NEVER committed to Git, and NEVER synced across fleet nodes by default.
2. **Defense-in-Depth Sanitization:** Automated scrubbing filters redact tokens, passwords, and `.env` credentials before disk append as defense-in-depth. Evidence is recorded via content-free SHA-256 digests in `evidence_refs`.
