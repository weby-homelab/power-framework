# POWER 3.8 — Phase 5E / P38-WP03-R5 Verdict (CLOSED / FAILED VERIFICATION)

**Execution Date:** 2026-09-18  
**Governance Scope:** Phase 5E / P38-WP03-R5 (Evaluation Contract Remediation + Fresh Sealed Evaluation Closure)  
**Target Repository:** `https://github.com/weby-homelab/power-framework`  
**Execution Node:** `PRXMX-01` (`pve01`, Tailscale IP: `100.86.120.114`)  
**Operator:** `weby-homelab <rekvizitor.ua@gmail.com>`  
**Signing Key:** `2D49E810C7F2527E`  

```text
PHASE 5E = CLOSED / FAILED VERIFICATION (ONE-SHOT HOLDOUT)
PHASE 5F = BLOCKED
POWER 3.8.0 = NO-GO (RELEASE GATED)
HOLDOUT_EVALUATION_EPOCH = v1.4 (ONE-SHOT EXECUTED)
RUNTIME_TUNING_AFTER_HOLDOUT = FALSE (STRICTLY FORBIDDEN & ENFORCED)
WORK_PACKAGE_B = STRICTLY DEFERRED (NOT STARTED)
```

---

## 1. Executive Summary

In strict adherence to the **Zero-Hallucination Evidence Mandate** and the **One-Shot Evaluation Governance Contract**, P38-WP03-R5 executed exactly ONE un-tuned epoch of `benchmark_phase5e_r5.py` against the sealed, freshly authored `v1.4` holdout split (`benchmarks/power38/retrieval_eval/v1.4`).

### Key Outcomes
1. **Quality Thresholds: PASS**
   - **Recall@5:** `0.7500` (threshold `>= 0.70`) — **PASS**
   - **MRR:** `0.6250` (threshold `>= 0.50`) — **PASS**
   - **nDCG@10:** `0.6851` (threshold `>= 0.60`) — **PASS**
   - **MAP:** `0.6750` — **PASS**

2. **Hard Invariants: FAILED VERIFICATION (10 of 12 Passed)**
   - `authority_winner_missing`: `1` violation out of 8 applicable owner-backed queries (`pass: false`).
   - `authority_outranked_by_relevance`: `1` violation out of 8 applicable owner-backed queries (`pass: false`).
   - `authority_order_violations`: `0` violations across all 20 queries (`applicable: 20`, `pass: true`).
   - `authority_provenance_failures`: `0` failures across all 7 applicable queries (`applicable: 7`, `pass: true`).
   - `default_switches`: `0` (`pass: true`).
   - `determinism_mismatches`: `0` (`pass: true`).
   - `prompt_injection_authority_escalation`: `0` (`pass: true`).
   - `query_side_writes`: `0` (`pass: true`).
   - `resource_bounds_pass`: `true` (`pass: true`).
   - `scope_escape`: `0` (`pass: true`).
   - `secret_leakage`: `0` (`pass: true`).
   - `non_regression_pass`: `true` (`pass: true`).

3. **Governed Disposition: Phase 5E Closed as FAILED**
   - Under the frozen evaluation contract, zero retries, zero tuning after holdout exposure, and zero masking are permitted.
   - Phase 5E is officially **CLOSED** with an empirical verdict of **FAILED VERIFICATION**.
   - Phase 5F remains **BLOCKED**.
   - Work Package B (Deferred Replay-Ready Execution Evidence Planning) is **STRICTLY DEFERRED** and not touched in this invocation.

---

## 2. Commit Lineage & Governance Proof

- **R4 Evidence Anchor:** `cd935d35189a92770fe0e02e56119ffec4ff2cf5`  
  *Preserved historical v1.3 holdout run and failure artifacts.*
- **PR-R5A (Remediation):** PR #456, merged into `main` at `d447da0`.  
  *Contract schema generalization, cross-lingual token filtering, and Section 3.2 authority metrics reporting.*
- **PR-R5S (Sealed Corpus v1.4):** PR #457, merged into `main` at `05e2868`.  
  *Authoring of fresh disjoint evaluation revision v1.4 with verified cryptographic digests and data-only registration.*
- **Holdout Execution Epoch Evidence:**  
  *Artifact:* `artifacts/project-state/phase-5e/phase5e_holdout_r5_epoch.json`  
  *Timestamp:* `2026-09-18T14:33:37.695588+00:00`  
  *Platform:* `Linux-7.0.14-16-pve-x86_64-with-glibc2.41` (`PRXMX-01`)  
  *Python:* `3.13.5`  
  *Runner:* `scripts/benchmark_phase5e_r5.py` (SHA-256 `a2da6898f76bc77a4cc354e3e63322231dfcd402f5fabc0fd57dfac46d158c2a`)

---

## 3. Detailed Root-Cause Analysis of Holdout Failure

The single failure occurred on query `p38-ho-q14`:

```text
Query ID: p38-ho-q14
Query Text: "Яка резолюція є остаточно затвердженою для процедури оцінювання?"
Declared Intent: decision
Expected Concept: decision-current
Projected Owner: DecisionService
Owner-Backed: True

Measured Retrieval Results:
  - Legacy Retrieval Concepts: [] (0 results)
  - Shadow Retrieval Concepts: [] (0 results)
  - Winner Present: False
  - Authority Violations: 0
  - Authority Outranked: 1
```

### Technical Root Cause
1. **Lexical Vocabulary Divergence in FAST Profile:**
   - In the `FAST` evaluation budget class, neural dense embeddings and rerankers are disabled (`cpu_only=True`, `dense_used=False`).
   - Retrieval relies entirely on lexical matching (FTS / BM25) and canonical pre-filtering.
   - The Ukrainian noun `"резолюція"` was used in the holdout query, whereas the canonical decision ledger title and markdown body only contain `"рішення"` (`dec_x-current-holdout-tuning-decision: "Canonical decision: holdout tuning current — рішення"`).
   - Because neither BM25 nor `RetrievalPlanner` found lexical overlap between `"резолюція"` and `"рішення"`, 0 candidate records were retrieved.
2. **Authority Winner Gating:**
   - For owner-backed queries (`owner_backed=True`), the authority gate strictly requires the canonical winner to be present in the top retrieved items.
   - When 0 items are retrieved, `winner_present=False`, triggering `authority_winner_missing=1` and `authority_outranked_by_relevance=1`.

---

## 4. Empirical Performance Breakdown

| Metric | Measured Shadow | Measured Legacy | Threshold / Gate | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Recall@5** | `0.7500` | `0.7500` | `>= 0.70` | **PASS** |
| **MRR** | `0.6250` | `0.6250` | `>= 0.50` | **PASS** |
| **nDCG@10** | `0.6851` | `0.6851` | `>= 0.60` | **PASS** |
| **MAP** | `0.6750` | `0.6750` | `Shadow >= Legacy` | **PASS** |
| **Authority Order Violations** | `0` (20/20 app) | N/A | `== 0` | **PASS** |
| **Authority Provenance Failures**| `0` (7/7 app) | N/A | `== 0` | **PASS** |
| **Authority Winner Missing** | `1` (8 app) | N/A | `== 0` | **FAIL** |
| **Authority Outranked** | `1` (8 app) | N/A | `== 0` | **FAIL** |
| **Determinism Mismatches** | `0` | N/A | `== 0` | **PASS** |
| **Query Side Writes** | `0` | N/A | `== 0` | **PASS** |
| **Scope Escapes** | `0` | N/A | `== 0` | **PASS** |
| **Secret Leakages** | `0` | N/A | `== 0` | **PASS** |
| **Default Switches** | `0` | N/A | `== 0` | **PASS** |
| **Prompt Injection Escalations** | `0` | N/A | `== 0` | **PASS** |

---

## 5. Next Steps and Governance Reconciliation

1. **Phase 5E Gate Closure:**
   - Submit PR-R5B staging `PHASE_5E_R5_VERDICT.md` and `phase5e_holdout_r5_epoch.json`.
   - Merge PR-R5B into `main` to finalize Phase 5E history.
2. **Phase 5F Blocking:**
   - As mandated by the Release Gate, POWER 3.8.0 release activities are blocked until a formal resolution track addresses dense embedding support or lexical synonym expansion for cross-lingual queries under FAST profiles.
3. **Work Package B:**
   - Strictly deferred per user mandate.
