# POWER 3.8 — Phase 5E (P38-WP03) Formal Admission Record

```text
ADMISSION_SCHEMA: power.admission.v2
CREATED_AT_UTC: 2026-09-17T11:10:00Z
GATE: Phase 5E / P38-WP03 — Shadow Benchmark / Legacy Comparison
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: feat/p38-wp03-phase5e-development-benchmark
STARTING_MAIN_SHA: 5bcec9cc2c0db27e142f8c5c7c30bdcfa57137d2
STARTING_MAIN_TREE: 647748130a7a16a87f45ed556ed7905f966887a2
STATUS: ADMITTED / IN PROGRESS
```

---

## 1. Live Preflight Verification (GitHub Canonical Truth)

Live verification against `origin/main` was executed independently prior to any implementation:

| Axis | Expected Live Truth | Observed Live Evidence | Status |
| :--- | :--- | :--- | :--- |
| **Main Commit SHA** | `5bcec9cc2c0db27e142f8c5c7c30bdcfa57137d2` | `5bcec9cc2c0db27e142f8c5c7c30bdcfa57137d2` | **MATCH** |
| **Main Tree SHA** | `647748130a7a16a87f45ed556ed7905f966887a2` | `647748130a7a16a87f45ed556ed7905f966887a2` | **MATCH** |
| **Preceding Gate** | Phase 5D / P38-WP02-R1 | Merged in PR #444 (`docs/p38-wp02-r1-phase5d-closure`) | **CLOSED / VERIFIED** |
| **Public Version** | `v3.7.13` | Tag `v3.7.13` (Latest Release) | **CONFIRMED** |
| **Main Package Version** | `3.7.11` | `power_framework.__version__ == "3.7.11"` | **CONFIRMED** |
| **POWER 3.8.0 Release** | NO-GO | No tag, no release, development target only | **ENFORCED** |
| **GPG Key Identity** | `2D49E810C7F2527E` | Key available with ultimate trust, `commit.gpgsign=true` | **READY** |

### Live Branch Protection Revalidation

Live inspection of `repos/weby-homelab/power-framework/branches/main/protection` confirmed:
- `strict: true`
- Required contexts (11 total):
  1. `test (3.13)`
  2. `test (3.14)`
  3. `security`
  4. `package-smoke`
  5. `upgrade-matrix (ubuntu-latest)`
  6. `upgrade-matrix-aggregate`
  7. `base-runtime-smoke`
  8. `benchmark-integrity`
  9. `analyze (python)`
  10. `CodeQL`
  11. `build`
- Required commit signatures: `enabled: true`
- `enforce_admins: true`

---

## 2. Governance Defect Reconciliation

Two governance defects in mutable current-state documents were identified and reconciled:
1. **Stale `CURRENT_LIVE_MAIN` Snapshot:**
   Following the merge of PR #444, `docs/plans/POWER_3.8_CURRENT_STATE.md` retained the pre-merge base SHA (`ed23beee8f7c60a24529422f8234dd0e6982d473`). Updated to live main SHA `5bcec9cc2c0db27e142f8c5c7c30bdcfa57137d2` and tree `647748130a7a16a87f45ed556ed7905f966887a2`.
2. **Phase 5E Canonical Naming:**
   Line 51 of `POWER_3.8_CURRENT_STATE.md` mislabeled Phase 5E as *"Context Memory / Stateful Multi-Turn Context"*. Canonical Phase 5E title is strictly **`P38-WP03 Shadow Benchmark / Legacy Comparison`**. Reconciled.

---

## 3. PRXMX-01 Findings Disposition

PRXMX-01 operational findings were classified in `artifacts/project-state/phase-5e/PRXMX01_FINDINGS_DISPOSITION.md`:
- **Doc/Workflow Fix:** Resolved Skill documentation drift in `skills/power/SKILL.md` and `references/agent-workflow.md`, clarifying that canonical transaction receipts already prove internal index and search synchronization, prohibiting blind duplicate full-vault sync/index.
- **Scope Preservation:** No runtime MCP mutation modifications, doctor architecture changes, or cancellation rewrites are permitted in Phase 5E.

---

## 4. Frozen Benchmark Contract Verification

Corpus `benchmarks/power38/retrieval_eval/v1.1` was verified offline via `scripts/verify_retrieval_eval.py`:
- `dataset_digest`: `5d8f2d7e68b62b3a2385c7a534a492083e1ff1b9f68973d4cbe8bf64461521fc`
- `query_set_digest`: `b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e`
- `development_digest`: `4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95` (20 queries)
- `holdout_digest`: `61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551` (20 queries, sealed)
- `source_corpus_digest`: `3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118` (20 sources)
- `semantic_adjudication_digest`: `106d3e220d01cc325ada3ffc3e551ebd4111be5c3fc5aebf62d22b0d45516218`
- `disjointness_digest`: `cf8054395040f17e4d21a005e248b7804fd515cc555b12b52b0afca0f32376d4`
- `semantic_adjudication_status`: **PASS**
- Overall Integrity: **PASS**

### Critical Ground Truth Grounding Rule

```text
GROUND TRUTH SCORES OUTPUT.
GROUND TRUTH NEVER PRODUCES OUTPUT.
```
Evaluation metadata (`authority`, `trust_state`, `temporal_state`, `noise_disposition`, `expected_authority_winner`) is strictly restricted to scoring and metric evaluation. It is never supplied to the planner, router, or ranking pipeline.

---

## 5. Scope Constraints (Non-Negotiable Boundaries)

Phase 5E operates under strict negative constraints:
- **Default Switch:** FORBIDDEN. Legacy retrieval remains served default.
- **Phase 5F+ Features:** FORBIDDEN.
- **Public MCP Context Tools:** FORBIDDEN.
- **Capture / Context Broker:** FORBIDDEN.
- **Version Bump / Tag / Release:** FORBIDDEN.
- **POWER 3.8.0 Release:** NO-GO.
- **Query-Side Writes:** FORBIDDEN (enforced via SHA-256 tree audit).
