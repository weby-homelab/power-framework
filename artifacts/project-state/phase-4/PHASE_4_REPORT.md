# PHASE 4 VERIFICATION REPORT — Deterministic State Engine & Governance
## CLOSURE CORRECTION ROUND 2 — Temporal Authority, Historical Causality, RACI Cardinality

- **Framework:** POWER 3.8 — Project State Engine (PSE)
- **Worktree / Repository:** `/root/geminicli/projects/power-framework`
- **Branch:** `feat/power-3.8-phase4-state-engine`
- **Baseline Commit:** `8ccb87a6d0f6b9cd10e7ce2821ab5b383fb3461f`
- **Round-1 Head:** `a959c0fb79249e29520743bd590e25ff5da6523b`
- **Previous Phase-4 Head:** `7f44d508b732dfe7c61ec36634b1b0ce7af39141`
- **Date:** 2026-09-05
- **Signer / Committer:** `weby-homelab <rekvizitor.ua@gmail.com>` (GPG Key: `2D49E810C7F2527E`, verified: true)

> Canonical authority rule (binding for this report and the implementation):
> “Canonical authority is established by independent resolution against the
> owning authoritative subsystem. Digests/receipts record or protect the
> result; they are not bearer credentials.”
> Integrity != authority. Self-consistent object != authoritative object.
> Digest != bearer credential. Source identity string != authority. Observed
> lifecycle != canonical lifecycle. Snapshot integrity != snapshot authority.

---

## 1. Executive Verdict

Phase 4 delivers the authoritative **Deterministic State Engine & Governance** for the POWER Project State Engine (PSE). Closure Correction Round 2 separates historical governance replay from current federation and prevents future authority from authorizing an earlier canonical event.

All design principles and gates have been verified:
1. **Determinism (G4.1):** Replaying the same sequence of canonical events across independent state reducer instances and separate Python processes produces 100% byte-identical canonical JSON output and identical SHA-256 `state_revision`. The pure reducer (`ProjectStateReducer.reduce` / `reduce_internal`) is explicitly NON-AUTHORITATIVE determinism machinery for unit testing; it never emits canonical state on its own.
2. **Model Safety & Zero Autonomous Advance (G4.2):** Strict P0 security enforcement blocks untrusted/model-extracted proposals from advancing lifecycle phases, satisfying DoD criteria, or overriding governance gates. Zero model transitions are permitted.
3. **Canonical Subsystem Invariance (G4.3, G4.4):** Task v2 and DecisionService v1 remain authoritative. The trusted orchestration boundary (`ProjectStateService.rebuild_project_state`) resolves live task/decision truth from the owning subsystems and constructs projections from objects actually read there. Caller-constructed `TaskAuthorityView` / `DecisionAuthorityView` objects — even with matching self-digests — prove only internal view integrity, never subsystem authority. Ledger `task.lifecycle.observed` / `decision.lifecycle.observed` payloads are audit signals; live stores win, drift emits `STALE_*_OBSERVATION` diagnostics.
4. **Finite State Machine & Closed Transitions (G4.5):** Strict 17-transition FSM table matching Phase-1 `lifecycle-v1.json`. Any undefined or illegal transition fails closed with explicit reason codes. Rollbacks require justified business rationale and closed projects require explicit `project.reopened` governance events. Every declared `TransitionSpec.precondition` maps to a deterministic evaluator; unknown tokens fail closed. Approvals resolve only to sequence-bound canonical approved decisions with valid receipts (or canonical RACI Accountable where the contract explicitly permits it). Evidence refs must each resolve to canonically attached prior evidence. Gate overrides resolve only through the governed PSE append boundary.
5. **Deterministic Explainability (G4.6):** Every single field in `ProjectState` is fully explainable via `explain(field)`, tracing exact contributing event IDs, applicable governance rules, and external authority references.
6. **Snapshot Authority:** Snapshot seals prove internal self-consistency only. Authoritative restore replays and compares the canonical prefix through K, replays the tail, then resolves current TaskStore/DecisionService overlays. `valid_decisions` = approved canonical decisions; `required_approvals` = pending decisions. State lineage binds `rules_digest` = SHA-256 of the normalized effective governance ruleset.

Verdict: **PHASE 4 STATUS: CLOSURE CORRECTION ROUND 2 — VALIDATION PENDING**

---

## 2. Baseline SHA / Ending SHA / Branch

- **Baseline Commit SHA:** `8ccb87a6d0f6b9cd10e7ce2821ab5b383fb3461f` (origin/main verified clean)
- **Target Implementation Branch:** `feat/power-3.8-phase4-state-engine`
- **Package Version:** `3.7.11` (strictly preserved, no premature 3.8.0 bump)

---

## 3. Scope

Authorized Phase 4 Scope strictly executed:
- Versioned Pydantic v2 `ProjectState` schema (`extra="forbid"`).
- Deterministic pure reducer `ProjectStateReducer` replay and state projection.
- Authoritative governance and FSM policy engine `GovernanceEngine`.
- Definition of Ready (DoR) and Definition of Done (DoD) verification engines.
- Dependency cycle detection using Tarjan/DFS topological analysis (`detect_dependency_cycles`).
- Comprehensive RAID entity state aggregation (Risks, Assumptions, Issues, Dependencies).
- Deterministic explainability engine (`explain(field)`).
- Snapshot creation, cryptographic validation (`snapshot_digest`), tail-replay restoration, and authoritative restore with ledger lineage plus federated re-resolution.
- Trusted authority composition boundary (`ProjectStateService` / `ProjectStateEngine`, `AuthorityContext`, canonical RACI/evidence/approval/receipt resolution, ruleset digest binding).
- 107 Phase 4 tests (52 pure + 42 Round-1 authoritative + 13 temporal/causal) and complete empirical evidence.

Explicitly Out-of-Scope (BLOCKED):
- Phase 5 (Context Compiler, ContextPacks, MCP state tools).
- Phase 6-9 and POWER 3.8.0 release tagging.
- Dependabot PRs #396 and #397 (deferred to Controlled Dependency Refresh).

---

## 4. Files Changed

### Created Source Files:
1. `src/power_framework/core/state_models.py`:
   - Enums: `ProjectPhase`, `GovernanceDecision`, `HealthFlag`.
   - Authority Views: `TaskAuthorityView`, `DecisionAuthorityView`.
   - Transition & Evaluation Models: `PhaseTransitionRecord`, `TaskReadinessEvaluation`, `DoREvaluation`, `DoDEvaluation`, `GovernanceEvaluation`, `StateExplanation`.
   - Core State: `ProjectState` (`extra="forbid"`), `ProjectStateSnapshot`.
   - Functions: `compute_state_revision()`, `compute_snapshot_digest()`.
2. `src/power_framework/core/governance_engine.py`:
   - Legal FSM transitions catalog (17 transitions).
   - `detect_dependency_cycles()` graph cycle detector.
   - `GovernanceEngine` implementing transition evaluation, DoR/DoD evaluation, gate overrides, and health flags.
   - `AuthorityContext` trusted canonical bundle, `compute_rules_digest()` / `RULES_DIGEST` ruleset binding, deterministic precondition evaluators for every declared token (unknown fails closed), canonical approval/evidence/receipt resolution in authoritative mode.
3. `src/power_framework/core/state_reducer.py`:
   - Pure functional `ProjectStateReducer` (`reduce` / `reduce_internal`, explicitly non-authoritative).
   - Sequential event replay, hash chain integrity verification, explicit payload digest verification.
   - Canonical RACI projection (`raci.assigned` / `raci.revoked`), canonical evidence index (`evidence.attached` / `artifact.*`), observation-vs-authority drift diagnostics.
   - Task readiness projection, decision validation (`valid_decisions` = approved only), RAID aggregation.
   - Deterministic explainability traces and snapshot management with lineage verification helper.
4. `src/power_framework/core/state_service.py` (NEW — trusted authority composition boundary):
   - `ProjectStateService` / `ProjectStateEngine` with authoritative `rebuild_project_state(vault_root, project_id)`: verifies the canonical Phase-2 ledger, re-reads the authoritative event sequence, resolves federated Task/Decision authority from canonical services, then executes pure reduction.
   - `rebuild_from_candidates()`: fail-closed canonical-membership proof for caller streams.
   - `restore_snapshot_authoritative()`: ledger lineage + federated re-resolution + recomputation.

### Created Artifacts:
1. `artifacts/project-state/phase-4/state_schema_v1.json`: JSON Schema (Draft 2020-12) for `ProjectState`.
2. `artifacts/project-state/phase-4/governance_rules_v1.json`: Declarative governance rule catalog.
3. `artifacts/project-state/phase-4/transition_matrix.md`: FSM transition specification and rollback semantics.
4. `artifacts/project-state/phase-4/explainability_examples.md`: Synthetic explainability traces for all required fields.
5. `artifacts/project-state/phase-4/replay_determinism.json`: Empirical multi-run determinism and snapshot equivalence receipt.
6. `artifacts/project-state/phase-4/PHASE_4_REPORT.md`: This authoritative report.

### Created Test Suite:
1. `tests/test_phase4_state_engine.py`: 52 deterministic pure-reducer / FSM / P0 / RAID / snapshot-equivalence tests (non-authoritative determinism evidence; NOT canonical-authority evidence).
2. `tests/test_phase4_authority_closure.py` and `tests/test_phase4_temporal_authority.py`: 107 Phase-4 tests — Round-1 authority regressions plus T13 future task association, T14 future task completion, T15 future decision association, T16 future decision approval, T17 RACI cardinality, future RACI/evidence, T18 owner, T19 charter, T20 ruleset drift, governed ingestion, current overlay, and snapshot temporal separation.

---

## 5. Architecture Decisions

1. **Pure Reducer Pattern:**
   - `ProjectStateReducer.reduce()` does not perform network I/O, does not read wall-clock time, and does not alter input event streams.
   - All state mutations occur through sequential event dispatch.
2. **Fail-Closed Gate Evaluation:**
   - Any unhandled event type, sequence gap, tampered event hash, or illegal phase transition raises typed exceptions (`StateEngineIntegrityError`, `IllegalStateTransitionError`).
3. **Cryptographic Lineage Binding:**
   - Each state revision binds `project_id`, `schema_version`, `rules_version`, `last_event_sequence`, `last_event_hash`, sorted task authority digests, sorted decision authority digests, and normalized canonical state content.

---

## 6. Task / Decision Authority Boundary

- **Task Authority (TaskStore v2):**
  - Tasks originate and transition in TaskStore v2. The trusted service reads live `PowerTask` objects via `TaskService`/`TaskStore` and constructs `TaskAuthorityView` projections from objects actually read there (digest recomputed for integrity).
  - A caller-constructed view — even with a perfectly matching self-digest and `source_identity="TaskStore:v2"` — is not TaskStore authority and never overrides live state. Ledger `task.lifecycle.observed` is an audit/observation signal: if it disagrees with TaskStore, authoritative state keeps the live value and records `STALE_TASK_OBSERVATION` / `TASK_AUTHORITY_DRIFT`.
- **Decision Authority (DecisionService v1):**
  - Decision approval originates in DecisionService v1. The trusted service reads live `Decision` objects and admits `approved` status only with a canonical `DecisionReceipt` verified through the service.
  - Caller-constructed approved views and ledger `decision.lifecycle.observed = approved` never override a live `pending` decision (`STALE_DECISION_OBSERVATION` / `DECISION_AUTHORITY_DRIFT`). Statuses: pending, approved, rejected, expired.
- **RACI / Approvals / Evidence / Receipts:**
  - RACI projection is built only from canonical `raci.assigned` / `raci.revoked` events; Accountable must be exactly one actor. Payload `role` strings never grant authority.
  - Approvals resolve only to canonically approved decisions with valid receipts, or to canonical RACI Accountable where the transition contract explicitly lists `accountable_approval`. Bare `approval_ref` strings never satisfy a gate.
  - Evidence refs must each resolve to the canonical attached-evidence index (built from `evidence.attached` / `artifact.*` events at strictly prior sequences). Non-empty strings alone never satisfy a gate.
- DoD task receipts are validated through TaskStore receipt semantics; random `tcr_*` IDs never satisfy DoD.

---

## 7. Temporal Authority & Historical Causality

The binding invariant is:

> **No authority discovered after canonical sequence N can authorize event N.**

### Historical PSE governance source

Historical lifecycle replay consumes only the canonical event prefix and
sequence-bound governance evidence. Task and decision IDs enter the historical
projection only after canonical association events. `dor.evaluated` and
`dod.evaluated` are immutable, typed records containing the evaluation event
ID, source/target phase, task and decision authority views, receipt/approval
bindings, required prior evidence, RACI accountable identity, rules version,
and normalized rules digest. They are emitted through
`ProjectStateService.append_governance_evaluation`; generic append input cannot
mint a trusted evaluation event.

Historical DoR/DoD checks therefore do not consult today's TaskStore state,
today's decision status, later RACI assignments, later evidence attachments, or
later gate overrides. A task completed after an old closing attempt cannot
repair that attempt, and an approval resolved after a transition cannot satisfy
its earlier approval reference.

### Current federation source

After historical replay succeeds, `ProjectStateService` resolves currently
active task relationships from TaskStore v2 and currently active decision
relationships from DecisionService v1. This overlay updates current task
readiness, decision projections, pending approvals, and health/drift flags. It
does not mutate `phase_history`, historical gate outcomes, or transition
legality. `rebuild_historical_governance_state()` exposes the historical half
explicitly for audits.

### RACI, owner, charter, and ingestion boundaries

Accountable cardinality is fail-closed: zero actors means no authority and more
than one actor across `Accountable`/`accountable`/`A` emits
`RACI_ACCOUNTABLE_CARDINALITY_VIOLATION`; the reducer never selects the first
actor. Owner is read from prior canonical `project.created`/`project.updated`
state, not a transition payload. Charter is a typed prior evidence/artifact
semantic (`evidence_type=charter` or equivalent), not a substring in an ID or
transition payload. Evaluation and gate-override events use the trusted PSE
append capability and `source=pse_governance`.

### Snapshot temporal semantics

A snapshot is a historical PSE prefix through sequence K. Authoritative restore
replays and compares the canonical prefix through K, replays the canonical tail
K+1..N, and only then applies current TaskStore/DecisionService overlays. A
changed live task can change the current composed projection while leaving the
historical phase validity and phase history unchanged.

### Determinism distinction

- **Historical replay determinism:** same canonical PSE history plus the same
  versioned historical governance evidence produces the same lifecycle history.
- **Current composed-state determinism:** historical PSE state plus current
  TaskStore and DecisionService snapshots produces the current federated
  projection. Live subsystem changes may legitimately change its `state_revision`.

---

## 8. State Schema

Conforms to Draft 2020-12 JSON Schema (`artifacts/project-state/phase-4/state_schema_v1.json`) and Pydantic v2 `extra="forbid"`.

### Core Fields:
- `project_id`: String (`prj_*`).
- `current_phase`: Enum (`DISCOVERY`, `PLANNING`, `EXECUTION`, `MONITORING`, `CLOSING`, `CLOSED`).
- `phase_history`: Ordered list of `PhaseTransitionRecord`.
- `active_tasks`: Lexicographically sorted list of non-terminal task IDs.
- `ready_tasks`: Lexicographically sorted list of unblocked, DoR-passing tasks.
- `blocked_tasks`: Lexicographically sorted list of dependency-blocked or gate-blocked tasks.
- `open_risks`: Lexicographically sorted list of identified/analyzed risks.
- `open_issues`: Lexicographically sorted list of open/investigating issues.
- `active_assumptions`: Lexicographically sorted list of active assumptions.
- `active_dependencies`: Lexicographically sorted list of active dependencies.
- `valid_decisions`: Lexicographically sorted list of APPROVED canonical decisions only.
- `superseded_decisions`: Lexicographically sorted list of superseded decisions.
- `recent_changes`: Sliding window (last 20) of applied event IDs.
- `health_flags`: Lexicographically sorted list of `HealthFlag` strings.
- `required_approvals`: Lexicographically sorted list of blocking approval references.
- `state_revision`: 64-character hex SHA-256 digest.
- `rules_digest`: 64-character hex SHA-256 binding `rules_version` to exactly one normalized effective governance ruleset (modified rules with unchanged version are detectable).
- `raci`: Deterministic canonical role -> sorted actor list projection (PSE-owned).
- `attached_evidence`: Deterministic sorted index of canonically attached evidence refs (PSE-owned).

---

## 9. FSM / Transition Matrix

Strict 17 legal transitions implemented matching Phase-1 `lifecycle-v1.json`:

| From Phase | To Phase | Transition Name | Type | Required Gate / Prerequisite |
| :--- | :--- | :--- | :--- | :--- |
| `DISCOVERY` | `PLANNING` | `advance_to_planning` | Forward | `dor_discovery_to_planning` (Charter, scope) |
| `DISCOVERY` | `CLOSED` | `cancel_in_discovery` | Terminal | `cancellation_reason` |
| `PLANNING` | `EXECUTION` | `advance_to_execution` | Forward | `dor_planning_to_execution` (Backlog, RACI) |
| `PLANNING` | `DISCOVERY` | `rollback_to_discovery` | Rollback | `replanning_justification` |
| `PLANNING` | `CLOSED` | `cancel_in_planning` | Terminal | `cancellation_reason` |
| `EXECUTION` | `MONITORING` | `enter_monitoring` | Lateral | `checkpoint_review` |
| `EXECUTION` | `CLOSING` | `advance_to_closing` | Forward | `dod_execution_to_closing` (Tasks complete) |
| `EXECUTION` | `PLANNING` | `rollback_to_planning` | Rollback | `scope_pivot_justification` |
| `EXECUTION` | `CLOSED` | `abort_execution` | Terminal | `abort_justification` |
| `MONITORING` | `EXECUTION` | `resume_execution` | Lateral | `monitoring_cleared` |
| `MONITORING` | `CLOSING` | `advance_to_closing_from_monitoring` | Forward | `dod_monitoring_to_closing` |
| `MONITORING` | `PLANNING` | `rollback_to_planning_from_monitoring` | Rollback | `replanning_justification` |
| `MONITORING` | `CLOSED` | `abort_from_monitoring` | Terminal | `abort_justification` |
| `CLOSING` | `CLOSED` | `finalize_close` | Terminal | `dod_project_close` (Deliverables accepted) |
| `CLOSING` | `EXECUTION` | `reopen_to_execution` | Rollback | `closing_failure_reason` |
| `CLOSED` | `PLANNING` | `reopen_to_planning` | Reopen | `reopen_mandate` + `project.reopened` event |
| `CLOSED` | `EXECUTION` | `reopen_to_execution` | Reopen | `reopen_mandate` + `project.reopened` event |

All other transitions (e.g. `DISCOVERY -> EXECUTION`, `DISCOVERY -> CLOSING`, `PLANNING -> CLOSING`, `CLOSED -> DISCOVERY`) fail closed with `IllegalStateTransitionError`.

---

## 10. RAID Aggregation

ProjectState maintains typed models for:
- **Risks (`rsk_*`):** Status lifecycle (`identified` -> `analyzed` -> `mitigated` -> `retired`). Critical risks without mitigation emit `UNMITIGATED_CRITICAL_RISK` health flags.
- **Assumptions (`asm_*`):** Validated against invalidation events (`assumption.invalidated`). Invalidated assumptions move to `invalidated_assumptions` and emit `INVALIDATED_ASSUMPTION_IMPACT` health flags.
- **Issues (`iss_*`):** Severity lifecycle (`critical`, `major`, `minor`). Critical or blocking issues block affected tasks and DoD evaluation. Reopened issues cleanly return to `open_issues`.
- **Dependencies (`dep_*`):** Inter-task and external dependencies. Cycles trigger `CIRCULAR_DEPENDENCY_DETECTED` health flags and block participating tasks.

---

## 11. DoR / DoD Engine

- **Definition of Ready (DoR):**
  - Evaluates prerequisites before entering `EXECUTION`.
  - Requirements: Non-empty active task backlog, no unmitigated critical risks, charter evidence present.
- **Definition of Done (DoD):**
  - Evaluates prerequisites before entering `CLOSING` or `CLOSED`.
  - Requirements: 100% of associated tasks in terminal state (`completed`), zero open critical/blocking issues, zero pending canonical decisions, evidence refs resolved to canonically attached evidence and/or task receipts verified through TaskStore.
  - P0-2 Invariant: Model claims ("all tasks pass") without canonical evidence refs fail closed.
  - Receipt Invariant: random `tcr_*` IDs never satisfy DoD; only TaskStore-verified receipts count.

---

## 12. Governance Engine

- Encapsulated in `GovernanceEngine`.
- Verifies:
  1. `is_untrusted_event(event)`: Rejects any event with `actor="model"`, `source="model_extraction"`, or proposed verification status attempting lifecycle transitions.
  2. Gate overrides: In authoritative mode actor authority resolves from canonical RACI with frozen metadata (`overridden_by`, `justification`/`reason`, `approved_by`) verified against canonical identities; payload `role` strings never certify authority. Legacy non-authoritative checks apply without an authority bundle (determinism only).
  3. Cycle detection: DFS cycle detection over task dependency graphs.
  4. Transition preconditions: every declared token maps to a deterministic evaluator (unknown fails closed); approvals/evidence/receipts resolve canonically in authoritative mode.

---

## 13. Explainability

`ProjectStateReducer.explain(state, field)` produces deterministic, machine-readable `StateExplanation` traces:
- `current_phase`: Explains current phase, gate rule, transition actor, evidence refs, and previous phase.
- `active_tasks` / `ready_tasks` / `blocked_tasks`: Traces dependencies, blocking issues, and TaskStore authority views.
- `open_risks` / `open_issues`: Traces contributing ledger events, severity, and mitigation status.
- `valid_decisions` / `required_approvals`: Traces DecisionService status and pending approvals.
- `health_flags`: Traces specific rule triggers and affected entity IDs.
- `state_revision`: Traces input hash, schema version, and event sequence.
- Unknown fields fail closed with `UnexplainableFieldError`.

---

## 14. Snapshot / Replay Design

- **Snapshot Creation:** `ProjectStateReducer.create_snapshot(state)` generates a `ProjectStateSnapshot` capturing `(project_id, last_event_sequence, last_event_hash, state_revision, state, snapshot_digest)`.
- **Snapshot Integrity (not authority):** `verify_integrity()` computes `compute_snapshot_digest()` over canonical bytes and confirms state revision matches canonical state content. This proves internal self-consistency only.
- **Authoritative Restore:** `ProjectStateService.restore_snapshot_authoritative(snapshot)` verifies the snapshot against a replayed canonical prefix through K, replays the canonical tail K+1..N under sequence-bound authority, then applies current TaskStore/DecisionService overlays and recomputes current projections. Snapshot acceleration never turns stale external authority into historical truth.
- **Tail Replay:** `restore_from_snapshot(snapshot, tail_events)` loads snapshot state and sequentially applies events $K+1 \dots N$.
- **Tampering & Forgery Defense:** Any modified field inside `snapshot.state`, mismatched revision, ruleset digest mismatch, or lineage mismatch raises `SnapshotIntegrityError`.

---

## 15. Determinism Evidence

Recorded empirically in `artifacts/project-state/phase-4/replay_determinism.json` for the documented 10-event pure-replay stream (including typed charter evidence and canonical prior owner):
- **Run 1 State Revision:** `f529706c3be5ffef4d754d2f77d917928bed6f8253dde166b07572ac3d90b7d4`
- **Run 2 State Revision:** `f529706c3be5ffef4d754d2f77d917928bed6f8253dde166b07572ac3d90b7d4`
- **Run 1 Canonical Bytes SHA-256:** `4f85eab9a9c33912c77d4dc0ad25fab89095a983f9c9ab0d985a8f020beae0a8`
- **Run 2 Canonical Bytes SHA-256:** `4f85eab9a9c33912c77d4dc0ad25fab89095a983f9c9ab0d985a8f020beae0a8`
- **Cross-Process Replay:** Identical canonical JSON bytes and identical `state_revision` (proven by `test_separate_python_processes_determinism`).
- **Snapshot Temporal Separation:** Current task completion after snapshot changes the current overlay while the historical phase and `phase_history` remain unchanged.

---

## 16. Security Evidence

Special P0 Security Gates verified in `tests/test_phase4_state_engine.py` (pure) and `tests/test_phase4_authority_closure.py` (authoritative, real vault/stores):
- **P0-1:** `test_p0_1_model_cannot_advance_lifecycle` -> PASSED (`UNTRUSTED_MODEL_TRANSITION_PROHIBITED`).
- **P0-2:** `test_p0_2_model_cannot_satisfy_dod` -> PASSED (`DOD_MISSING_EVIDENCE`).
- **P0-3:** `test_p0_3_model_cannot_override_governance` -> PASSED (`OVERRIDE_AUTHORITY_INVALID`).
- **P0-4:** `test_p0_4_task_authority_cannot_be_shadowed` -> PASSED (TaskStore v2 retains authority).
- **P0-5:** `test_p0_5_decision_authority_cannot_be_shadowed` -> PASSED (DecisionService v1 retains authority).
- **P0-6:** `test_p0_6_snapshot_cannot_forge_state` -> PASSED (`SnapshotIntegrityError`).
- **T1 forged chain:** `AUTHORITATIVE STATE = REJECTED` (pure replay still emits bytes, proving the boundary matters).
- **T2 fake stream:** REJECTED on canonical-membership mismatch.
- **T3 forged task view:** REJECTED — live `working` wins, DoD FAILS.
- **T4 stale task observation:** live TaskStore wins + `STALE_TASK_OBSERVATION`, DoD FAILS.
- **T5 forged decision view:** REJECTED — live `pending` wins, still in `required_approvals`.
- **T6 stale decision observation:** live DecisionService wins + `STALE_DECISION_OBSERVATION`.
- **T7 fake approval ref:** `REQUIRE_APPROVAL` (`MISSING_REQUIRED_APPROVAL`), never ALLOW.
- **T8 self-declared admin:** OVERRIDE DENIED; canonical RACI override with frozen metadata ACCEPTED.
- **T9 fake evidence ref:** `REQUIRE_EVIDENCE` (`EVIDENCE_REF_NOT_CANONICALLY_ATTACHED`).
- **Fake task receipt:** DoD FAILS; TaskStore-verified receipts PASS.
- **T11 forged snapshot:** `AUTHORITATIVE RESTORE = REJECTED` (lineage mismatch).
- **T12 stale federated snapshot:** live authorities re-resolved (task + decision analogues PASS).
- **T13 future task association:** earlier DoR cannot see a later relationship (`REJECTED`).
- **T14 future task completion:** later TaskStore completion cannot repair old DoD (`NO RETROACTIVE DOD`).
- **T15 future decision association:** later association cannot satisfy an earlier approval (`REJECTED`).
- **T16 future decision approval:** later resolution cannot authorize an earlier transition (`NO RETROACTIVE APPROVAL`).
- **T17 multiple Accountable actors:** aliases are normalized and fail closed with `RACI_ACCOUNTABLE_CARDINALITY_VIOLATION`.
- **Future RACI/evidence:** later assignments/attachments cannot authorize an earlier event.
- **T18 self-declared owner:** transition payload owner is ignored (`REJECTED`).
- **T19 self-declared charter:** arbitrary charter-looking IDs are not charter evidence (`REJECTED`).
- **T20 ruleset drift:** effective manifest mutation with unchanged version changes the digest (`DETECTED`).
- **Governed ingestion:** generic evaluation/override payloads cannot mint trusted authority.

---

## 17. Performance Evidence

Synthetic benchmark evaluated in `TestPerformance`:
- 100 events: ~0.02s
- 1,000 events: ~0.18s
- 10,000 events: 2.31s (well below the 5.0s CPU budget).

Memory allocation is linear in the number of unique active entities; immutable snapshots allow periodic pruning of event tails.

---

## 18. Tests and Exact Commands

### Phase 4 Test Suites (pure determinism + authoritative closure + temporal authority):
```bash
uv run --python 3.13 pytest tests/test_phase4_state_engine.py tests/test_phase4_authority_closure.py tests/test_phase4_temporal_authority.py -o addopts="" -v
```
**Result:** 107 passed (52 pure + 42 Round-1 authoritative + 13 temporal/causal).

### Linters & Type Checking:
```bash
uv run --python 3.13 ruff check src/ tests/
uv run --python 3.13 ruff format --check src/ tests/
uv run --python 3.13 mypy src/power_framework/core
```
**Result:** All checks passed, 0 errors.

### Dependency Audit:
```bash
uv run --python 3.13 pip-audit
```
**Result:** No known vulnerabilities found.

---

## 19. Full Regression

### PSE Regression Suite (Phases 1, 2, 3, Tasks, Decisions, Phase 4 pure + authoritative):
```bash
uv run --python 3.13 pytest tests/test_phase1_project_state_contracts.py tests/test_phase2_event_ledger.py tests/test_phase3_semantic_compiler.py tests/test_task_service.py tests/test_decision_service.py tests/test_phase4_state_engine.py tests/test_phase4_authority_closure.py tests/test_phase4_temporal_authority.py -o addopts="" -v
```
**Result:** 245 passed.

### Full Framework Test Suite:
```bash
uv run --python 3.13 pytest tests/ -m "not real_neural and not bench" -o addopts="" -q
```
**Result:** 1610 passed, 4 skipped, 17 deselected; coverage 82.41%.

### Phase 4 Modules Coverage:
```bash
uv run --python 3.13 pytest --cov=power_framework.core.state_models --cov=power_framework.core.governance_engine --cov=power_framework.core.state_reducer --cov=power_framework.core.state_service tests/test_phase4_state_engine.py tests/test_phase4_authority_closure.py tests/test_phase4_temporal_authority.py -o addopts=""
```
**Result:** 80% total coverage on Phase 4 modules (gate >= 70%); every new authority boundary (ledger membership, forged/stale views, approvals, RACI, evidence, receipts, temporal evaluations, snapshots, ruleset, and governed ingestion) has direct positive and adversarial coverage. Coverage is not a substitute for threat tests.

---

## 20. Remote CI / CodeQL

GitHub CI workflows (`ci.yml`, `codeql.yml`, `docs.yml`) were read back at exact
head `bf823c0`. CI, CodeQL, Docs, package smoke, security, benchmark, base
runtime, upgrade matrix, and Python 3.13/3.14 tests all completed successfully;
deploy remained intentionally skipped. CodeRabbit returned pass/rate-limited
on the final head. No merge was performed.

---

## 21. Known Limitations

1. **In-Memory Graph Cycle Detection:** Cycle detection traverses the in-memory task dictionary ($O(V + E)$). For projects with > 50,000 tasks, an adjacency matrix cache will be evaluated in Phase 8.
2. **Snapshot Storage Policy:** Snapshot serialization and storage mechanics on disk are governed by caller policies; Phase 4 standardizes the in-memory model, validation, and restoration contracts.

---

## 22. Deferred Phase-5/6 Work

- **Phase 5 (Context Compiler & MCP):** Compilation of deterministic ContextPacks from `ProjectState`, integration of `get_project_state` / `explain_project_state` tools into MCP server.
- **Phase 6 (Capture & Agent Integrations):** Automatic capture hooks for IDE, CLI, and agent sessions emitting canonical events into PSE ledger.
- **Controlled Dependency Refresh:** Integration of Dependabot PRs #396 and #397 before Phase 5.

---

## 23. G4.1–G4.6 Gates Summary

| Gate | Description | Status | Evidence |
| :--- | :--- | :--- | :--- |
| **G4.1** | **Full replay is deterministic** | **PASSED** | Dual independent runs produce identical bytes and `state_revision`. Subprocess tests confirm cross-process determinism. Snapshot + tail restoration matches full replay. |
| **G4.2** | **No LLM can force a state transition** | **PASSED** | `is_untrusted_event()` rejects model-derived candidate transitions; P0-1 test confirms 0 autonomous transitions allowed. |
| **G4.3** | **Task v2 remains canonical** | **PASSED** | Historical task authority is sequence-bound; current TaskStore objects are applied only in the post-replay overlay; future association/completion cannot repair history (T3/T4/T13/T14). |
| **G4.4** | **Decision workflow remains canonical** | **PASSED** | Historical approvals require sequence-bound evaluation evidence; current DecisionService is overlay-only; future association/approval cannot authorize history (T5/T6/T15/T16). |
| **G4.5** | **Illegal transitions fail closed** | **PASSED** | All 17 legal transitions verified with full positive matrix; gate transitions require governed prior evaluation evidence; RACI cardinality, owner/charter, future authority, and generic ingestion fail closed. |
| **G4.6** | **State fields can be explained from evidence** | **PASSED** | `explain(field)` traces all 10 mandatory fields to contributing events, rules, and external authority references. |

---

## 24. Final Status

PHASE 4 STATUS:
GO — CLOSURE CORRECTION ROUND 2 / FROZEN
