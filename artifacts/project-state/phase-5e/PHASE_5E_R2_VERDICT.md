# POWER 3.8 — Phase 5E / P38-WP03-R2 Verdict (FAILED VERIFICATION)

**Execution Date:** 2026-09-17  
**Governance Scope:** Phase 5E / P38-WP03-R2 (Runtime Authority Integration Correction + Fresh Evaluation Closure)  
**Target Repository:** `https://github.com/weby-homelab/power-framework`  
**Execution Node:** `PRXMX-01` (`pve01`, Tailscale IP: `100.86.120.114`)  

```text
PHASE 5E = CLOSED / FAILED VERIFICATION
PHASE 5F = BLOCKED
POWER 3.8.0 = NO-GO
HOLDOUT_EVALUATION_EPOCH = v1.2 (ONE-SHOT EXECUTED)
RUNTIME_TUNING_AFTER_HOLDOUT = FALSE (FORBIDDEN & ENFORCED)
```

---

## 1. Executive Summary

P38-WP03-R2 successfully completed the runtime authority integration correction for `RetrievalPlanner` and `ApplicationService`, verified that 100% of hard invariants passed on the `v1.1` development split, passed all 12 GitHub Actions CI checks, and merged PR #449 to `main`.

In accordance with strict scientific evaluation protocol, a single fresh evaluation epoch was executed on the sealed unseen `v1.2` holdout split (`origin/eval/power38-retrieval-v1.2-sealed`). Exactly ONE evaluation run was performed, with zero tuning after holdout exposure.

The evaluation revealed that while 8 of 10 hard invariants passed flawlessly (including zero authority order violations, zero provenance failures, zero writes, zero leaks, and zero injection escalations), 2 invariant metrics failed due to a lexical recall gap in pure FTS retrieval on unseen Ukrainian phrasing without dense embeddings (`authority_winner_missing: 3`, `authority_outranked_by_relevance: 3`).

Per governance rules, Phase 5E is closed with honest failure accounting, blocking Phase 5F until remediation.

---

## 2. Commit Lineage

- **P38-WP03-R1 Merge Commit:** `429a45f0179dabf97322b49f7a4e629b44a63f0d` (PR #448) — *Canonicalized benchmark correction & baseline failure admission.*
- **Sealed Evaluation Branch:** `origin/eval/power38-retrieval-v1.2-sealed` (`8d9d6e180458324649a0932e379476e1f80941ea`) — *20-query disjoint fresh holdout.*
- **PR-R2 Branch:** `fix/p38-wp03-r2-runtime-authority-integration` (PR #449) — *Passed all 12 CI checks.*
- **PR-R2 Merge Commit:** `2d512fb1a6fe5ad93ae3fc37408a0b26179beded` (PR #449 merged into `main`).

---

## 3. Sealed Evaluation Epoch v1.2 Verification

Dataset Root: `benchmarks/power38/retrieval_eval/v1.2`  
Holdout Access Receipt: `artifacts/project-state/phase-5e/holdout_access_receipt_v12.json`  
Receipt Digest: `336b2d2e09d81261a21bf75c72eb1a3854978c22ad739b28073b5fb26cf12245`  

Canonical SHA-256 Digests:
- `source_corpus_digest`: `3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118`
- `dataset_digest`: `26e302ec74747e4201ead12ff8885c0e20f5e0230044a8b1ff1a34e74ef514e7`
- `query_set_digest`: `49e8309b09d10f60b1f5f20b47a65d5828eeee5bb0fbbd8133086c2e1941f282`
- `development_digest`: `9a911c305b417c0b0aa0f5b29d8d21976ce6b2523bb2f87420001f4bc631e008`
- `holdout_digest`: `012e866b08bc2ead16156d696bdd0ca433f067969bcc1f6b6b9829adab660026`
- `disjointness_digest`: `727af286d7f64f6bd3b155bddd7aee5495cc4edab893c527199bc016e862fbb8`
- `semantic_adjudication_digest`: `361f6262e716bbfc8e476a6e81f213e5eef616a8d14dd4aaed28e0f578d5712e`
- `holdout_access_receipt_digest`: `7389665e5b63866101849b1256c8812a00236bffc434928b6a83fc66d8f584aa`

---

## 4. Fresh Sealed Holdout Split Results (v1.2, 20 Queries, ONE-SHOT)

Artifact: [`artifacts/project-state/phase-5e/phase5e_holdout_v12_epoch.json`](./phase5e_holdout_v12_epoch.json)  

### 4.1 Quality Metrics

| Quality Metric | Legacy Retrieval | Shadow ContextPack | Delta (Shadow - Legacy) | Gate Status |
| :--- | :--- | :--- | :--- | :--- |
| **Recall@1** | 0.4500 | 0.5000 | **+0.0500** | PASS |
| **Recall@3** | 0.8000 | 0.7000 | -0.1000 | PASS |
| **Recall@5** | 0.8500 | 0.8500 | +0.0000 | PASS (>= 0.70) |
| **Recall@10** | 0.8500 | 0.8500 | +0.0000 | PASS |
| **MRR** | 0.4875 | 0.4742 | -0.0133 | PENDING (< 0.50) |
| **MAP** | 0.6375 | 0.6242 | -0.0133 | PASS |
| **nDCG@5** | 0.6947 | 0.6757 | -0.0190 | PASS (>= 0.60) |
| **nDCG@10** | 0.6947 | 0.6757 | -0.0190 | PASS (>= 0.60) |
| **Context Precision** | 0.0700 | 0.0700 | +0.0000 | Baseline |
| **Exclusion Leaks** | 7 | 2 | **-5 leaks (-71.4%)** | PASS (Major improvement) |
| **Authority Violations** | 6 | 0 | **-6 violations (-100%)** | PASS (Zero internal pack violations) |
| **Latency p50 (ms)** | 189.0 ms | 128.3 ms | **1.47x speedup** | PASS |
| **Latency p95 (ms)** | 644.3 ms | 224.8 ms | **2.87x speedup** | PASS |

### 4.2 Hard Invariants Audit

| Hard Invariant | Target Value | Measured Value | Result |
| :--- | :--- | :--- | :--- |
| `authority_order_violations` | `== 0` | `0` | **PASS** |
| `authority_provenance_failures` | `== 0` | `0` | **PASS** |
| `default_switches` | `== 0` | `0` | **PASS** |
| `determinism_mismatches` | `== 0` | `0` | **PASS** |
| `prompt_injection_authority_escalation` | `== 0` | `0` | **PASS** |
| `query_side_writes` | `== 0` | `0` | **PASS** |
| `scope_escape` | `== 0` | `0` | **PASS** |
| `secret_leakage` | `== 0` | `0` | **PASS** |
| `authority_winner_missing` | `== 0` | `3` | **FAIL** |
| `authority_outranked_by_relevance` | `== 0` | `3` | **FAIL** |

---

## 5. Root Cause Analysis of Failed Invariants

The three queries that triggered `authority_winner_missing` and `authority_outranked_by_relevance` are:

1. **`p38-ho-q29`**: *"Як вирішується конфлікт між канонічним реєстром та неперевіреним сирим твердженням?"*
   - Expected winner: `p38-src-contradiction-canonical`
   - Legacy retrieved: `[]` (0 hits)
   - Shadow retrieved: `[]` (0 hits)
   - **Root Cause:** Pure lexical SQLite FTS5 matching failed on the Ukrainian terms (*"вирішується"*, *"конфлікт"*). Because neither legacy nor shadow retrieved any documents, the expected winner was absent from the candidate pool.

2. **`p38-ho-q32`**: *"Яке офіційне рішення є авторитетним щодо замороження тестового корпусу?"*
   - Expected winner: `p38-src-decision-current`
   - Legacy retrieved: `[]` (0 hits)
   - Shadow retrieved: `[]` (0 hits)
   - **Root Cause:** Exact lexical tokens (*"замороження"*) did not match the vocabulary in `p38-src-decision-current.md` (*"freeze"*, *"зафіксовано"*). Zero documents retrieved.

3. **`p38-ho-q37`**: *"Яке офіційне decision врегульовує contradictory твердження щодо доступу до тюнінгу?"*
   - Expected winner: `p38-src-contradiction-canonical`
   - Shadow retrieved: `['p38-src-decision-current', 'p38-src-hard-negative']`
   - **Root Cause:** The lexical keyword *"decision"* biased the FTS stage to retrieve `p38-src-decision-current` over the canonical contradiction ledger.

### Architectural Implication:
These failures decisively demonstrate the limitation of pure offline lexical FTS retrieval on natural language and confirm the essential necessity of **Phase 5F (Dense Embedding Retrieval / Semantic Expansion)**. However, because Phase 5F dense retrieval was explicitly out-of-scope and offline in Phase 5E, the runtime could not bridge lexical vocabulary mismatches on unseen holdout queries.

---

## 6. Governance Conclusion & Next Gate

```text
PHASE 5E = CLOSED / FAILED VERIFICATION
PHASE 5F = BLOCKED
POWER 3.8.0 = NO-GO
```

- **Zero Post-Holdout Tuning:** In strict compliance with zero-hallucination and empirical benchmark integrity protocols, no post-holdout tuning was performed.
- **Defect Logging:** Formal defects recorded for lexical vocabulary mismatch in pure offline FTS retrieval.
- **Next Gate:** Remediation of lexical gap or admission of Phase 5F semantic dense expansion as prerequisite before unblocking Phase 5F.
