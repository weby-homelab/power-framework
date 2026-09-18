# Phase 5E — Independent Root-Cause Adjudication (Query h20)

## 1. Status and Fact-Anchored Context

- **Gate:** P38-WP03 / Phase 5E Closure
- **Active Holdout Epoch:** `v1.3` (one-shot execution at commit `b253bc329d1ad75d4b4feb672dd0baf675064864`, PR #455 / PR-R4A)
- **Reported Epoch Result:** `all_hard_invariants_pass = false` (2 hard gate failures on `p38-v13-h20`)
- **Failing Query ID:** `p38-v13-h20`
- **Failing Invariants:**
  - `authority_winner_missing = 1` (applicable = 8, failures = 1)
  - `authority_outranked_by_relevance = 1` (applicable = 8, failures = 1)
- **Primary Evidence Reviewed:**
  - `benchmarks/power38/retrieval_eval/v1.3/queries.holdout.jsonl` (query `p38-v13-h20`)
  - `benchmarks/power38/retrieval_eval/v1.3/ground_truth.holdout.jsonl` (GT `p38-v13-h20`)
  - `benchmarks/power38/retrieval_eval/v1.3/corpus/p38-src-contradiction-canonical.md`
  - `artifacts/project-state/phase-5e/phase5e_runtime_fixture_manifest_v2.json`
  - `scripts/phase5e_concept_mapping.py`
  - `src/power_framework/core/retrieval_planner.py`
  - `src/power_framework/core/state_service.py` and `state_models.py`
  - ADR-0007, ADR-0008, `EvidenceOrderingPolicy` in `context_contracts.py`

---

## 2. Reviewer A — Query Semantics, GT Contract, and Subsystem Ownership

### 2.1 Analysis
Query `p38-v13-h20` wording:
> *"Узгодьте суперечливі твердження про статус проєкту за канонічним записом, відкинувши шумовий блок і застарілий знімок."*

The query is categorized under `["CONTRADICTION", "NOISE", "SUPERSEDED"]` with intent `governance`.
Ground truth designates `p38-src-contradiction-canonical` as `expected_authority_winner` and excludes `p38-src-contradiction-raw`, `p38-src-noise-injection`, and `p38-src-project-superseded`.

However, inspecting the actual content of `p38-src-contradiction-canonical.md`:
```markdown
---
type: Project
title: "Synthetic contradiction ledger — canonical side"
description: "Synthetic canonical contradiction-resolution fixture."
timestamp: 2026-09-10T06:00:00+00:00
owner: "power38-fixture"
status: active
tags: [power38, synthetic, contradiction]
---
# Contradiction resolution
The canonical ledger states that holdout labels are not tuning input. A
conflicting raw statement is retained for diagnosis but cannot change this
authority state.
```

The underlying fact is: *"holdout labels are not tuning input"*. This is a **GOVERNANCE POLICY / BENCHMARK INTEGRITY RULE**, not a runtime project state.
The note has frontmatter `type: Project`. The benchmark author inferred that because `type == Project`, the owner must be `ProjectStateService`, and fabricated a synthetic runtime project object `prj_x-contradiction-tuning-authority-canonical` in `phase5e_runtime_fixture_manifest_v2.json`.

Binding architectural invariants:
- `TYPE != OWNER`
- `TAG != OWNER`
- `PATH != OWNER`
- `DOMAIN != OWNER`
- `GT != OWNER`

`ProjectStateService` manages project lifecycles (phases, tasks, decisions, RACI, health). It does **NOT** own arbitrary policy rules about benchmark holdout labels. This fact class is a **DECLARED SOURCE ARTIFACT / GOVERNANCE POLICY DOCUMENT**, which has **NO CANONICAL RUNTIME OWNER** in `ProjectStateService`, `TaskService`, or `DecisionService`.

Expecting `ProjectStateService` to be the canonical runtime owner for this policy concept was an architectural misattribution in the benchmark.

### 2.2 Reviewer A Classification
**A — EVALUATION_OWNER_MAPPING_DEFECT** (secondary: **F — INVALID_CAPABILITY_EXPECTATION / NO CANONICAL RUNTIME OWNER**).

---

## 3. Reviewer B — Runtime Planner, Candidate Routing, and Projection Coverage

### 3.1 Analysis
Diagnostic reproduction on the live runtime reveals:
1. When `intent == QueryIntentKind.GOVERNANCE`, `_PRIMARY_OWNER_BY_INTENT.get(intent)` returns `None`.
2. In `retrieval_planner.py` lines 968–977:
   ```python
   if (
       scope_project_ids is None
       and primary_owner != "project"
       and query_meaningful
       and not (query_meaningful & _meaningful_tokens(project_id))
   ):
       continue
   ```
   Because `primary_owner` is `None` (not `"project"`), the pre-filter executed.
   `query_meaningful` contained Ukrainian tokens: `{"узгодьте", "суперечливі", "твердження", "про", "статус", "проєкту", "канонічним", "записом", "відкинувши", "шумовий", "блок", "застарілий", "знімок"}`.
   `_meaningful_tokens(project_id)` contained English tokens: `{"prj", "contradiction", "tuning", "authority", "canonical"}`.
   The intersection was empty, so `prj_x-contradiction-tuning-authority-canonical` was dropped immediately without evaluating its eligibility.

3. Furthermore, even if the pre-filter had not dropped the ledger:
   `match_text` was constructed as `f"{project_id} {p_phase} {p_owner} {p_members}"`.
   In `state_models.py`, `ProjectState` model is strictly validated with `extra='forbid'` and contains only: `project_id`, `current_phase`, `owner`, `phase_history`, `active_tasks`, `ready_tasks`, `blocked_tasks`, `open_risks`, `open_issues`, `active_assumptions`, `active_dependencies`, `valid_decisions`, `superseded_decisions`, `recent_changes`, `health_flags`, `required_approvals`, `state_revision`, `raci`, `evidence_kinds`, `attached_evidence`.
   `ProjectState` carries NO `name`, `description`, or custom `status` string.
   The fabricated payload text ("Contradiction tuning authority canonical") was never projected into `ProjectState`.
   Therefore, `match_text` contained only English tokens (`"prj_x-contradiction-tuning-authority-canonical DISCOVERY"`), yielding zero overlap with the Ukrainian query.

4. The search engine retrieved `01_Projects/corpus/p38-src-project-current-ua.md` (which matched Ukrainian keywords `"проєкт"`, `"статус"`). Because the expected canonical winner was not admitted, this note became the highest-ranked result, triggering `authority_winner_missing = 1` and `authority_outranked_by_relevance = 1`.

### 3.2 Reviewer B Classification
**A — EVALUATION_OWNER_MAPPING_DEFECT** (secondary: **C — RUNTIME_ELIGIBILITY_OR_ROUTING_DEFECT** in the cross-lingual identity pre-filter).

---

## 4. Diagnostic Reproduction Table (Query h20)

| Dimension | Observed Reality |
|---|---|
| **Query ID** | `p38-v13-h20` |
| **Intent** | `governance` (`QueryIntentKind.GOVERNANCE`) |
| **Query Tokens** | `узгодьте`, `суперечливі`, `твердження`, `про`, `статус`, `проєкту`, `за`, `канонічним`, `записом`, `відкинувши`, `шумовий`, `блок`, `і`, `застарілий`, `знімок` |
| **Owners Consulted** | `ProjectStateService`, `DecisionService`, `TaskService` (matrix for `GOVERNANCE`) |
| **Candidate Identities** | `prj_x-contradiction-tuning-authority-canonical`, `prj_x-power-current-project-phase-status` |
| **Owner Identity** | `ProjectStateService` |
| **Eligibility Tier** | `Ineligible` (0 query tokens matched `match_text`) |
| **Matched Terms** | `()` (empty) |
| **Relevance Score** | `0.0` |
| **Authority** | Not admitted (`CANONICAL` candidate discarded before context pack) |
| **Admission Reason** | None |
| **Rejection Reason** | Skipped by pre-filter (no token intersection between Ukrainian query and English project ID) and 0 token overlap with `ProjectState` projection |
| **Final Ordering** | Note `01_Projects/corpus/p38-src-project-current-ua.md` (rank 1) |
| **Expected Concept Absence Reason** | `contradiction-canonical` has no real runtime owner in `ProjectStateService`; the fabricated fixture object was dropped by planner routing |

---

## 5. Adjudication Synthesis and Root-Cause Classification

### Primary Root Cause
**Class A — EVALUATION_OWNER_MAPPING_DEFECT**

### Secondary Factor
**Class C — RUNTIME_ELIGIBILITY_OR_ROUTING_DEFECT** (planner pre-filter dropping candidates purely on ASCII ID token intersection when `primary_owner` is None).

### Subsystem Fact Ownership
- The statement *"holdout labels are not tuning input"* belongs to **GOVERNANCE POLICY / DECLARED SOURCE ARTIFACT**.
- It is NOT a `ProjectState` object.
- Assigning `production_owner = "ProjectStateService"` to `contradiction-canonical` merely because its Markdown file has `type: Project` was a violation of `TYPE != OWNER`.

### Rejected Alternatives
1. **Rejected: Modify production planner with an `if "суперечливі"` or `if "h20"` shortcut.**
   *Rationale:* Benchmark-specific branching violates core architecture invariants (`NO BENCHMARK-SPECIFIC PRODUCTION LOGIC`).
2. **Rejected: Read arbitrary event payload text from the raw ledger into `ProjectState`.**
   *Rationale:* Section 2B.5 forbids reading arbitrary ledger payloads to grab missing words. `ProjectState` is a formal state machine, not a free-text document store.
3. **Rejected: Classify as Runtime Core Defect (Class B/D) and redesign PSE.**
   *Rationale:* PSE functions exactly as designed per ADR-0007/0008. The defect was evaluating a policy document as if it were a canonical project state object.

---

## 6. Actionable Decisions for R5

1. **Production Retrieval (R5 Remediation):**
   - Fix general routing in `retrieval_planner.py`: When `primary_owner` is None or for cross-lingual queries, do not prematurely drop projects using a strict ASCII-only `_meaningful_tokens(project_id)` pre-filter when the query contains general project terms.
   - Fix `item_text` projection in `retrieval_planner.py`: Project `current_phase.value` instead of non-existent `.phase`.
2. **Evaluation Harness (R5 Versioning):**
   - In `phase5e_runtime_fixture_manifest_r5.json`: Classify `contradiction-canonical` as `production_owner = "VaultNote"`, `expected_runtime_authority = None`, `owner_backed = False`.
   - Ensure all three canonical owners (`TaskService`, `DecisionService`, `ProjectStateService`) are tested with legitimate owner-backed concepts (`task-current`, `decision-current`, `project-current`).
   - Authority metrics in the runner (`benchmark_phase5e_r5.py`) must report explicit `applicable_query_count`, `measured_violation_count`, `not_applicable_count` for all 4 authority invariants.
   - Ground truth for future holdout revisions must never require `CANONICAL` or `owner_backed = True` for concepts lacking a real canonical runtime owner.
