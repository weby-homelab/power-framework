# POWER 3.8 — Phase 5C (P38-WP01 SearchScope Pushdown) Implementation & Verification Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T11:05:00Z
GATE: Phase 5C (P38-WP01 — SearchScope Pushdown)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: feat/p38-wp01-search-scope-pushdown
BASE_SHA: 6c247c7e4c1788a8bd5388b1327170a8e7493852
BASE_TREE: 09a6266d6e4336cd3d4c0b7e50561828ae8470af
STATUS: VERIFIED_CANDIDATE
```

---

## 1. Executive Summary

This handoff provides verified implementation and test evidence for **Phase 5C / P38-WP01 — SearchScope Pushdown** in `power-framework`.

- **Goal:** Eliminate candidate starvation defect and enforce "SCOPE BEFORE CANDIDATES" pushdown across all retrieval pipelines.
- **Defect Status:** Resolved. In-scope recall improved from `0.0` (starvation) to `1.0` (target retrieved).
- **Out-of-Scope Materialization:** Zero (`0`) out-of-scope candidates materialized at FTS, TF vector, dense embeddings, reranker input pool, graph BFS traversal, and fallback bounded scan boundaries.
- **Fail-Closed Security:** Verified for `trust_states`, `project_ids`, unknown domain IDs, and unauthorized access to privileged boundaries (`include_archived`, `include_quarantine`).
- **Test Results:** 28/28 tests in `tests/test_phase5c_search_scope.py` PASSED; 103/103 tests in `tests/test_searcher.py` PASSED; 74/74 tests in `tests/test_phase5a_runtime_contracts.py` & `tests/test_phase5b_domain_routing.py` PASSED.
- **Linters & Typing:** `ruff check src tests` passed with 0 issues; `mypy src/power_framework` passed with 0 issues across 123 source files.

---

## 2. Modified & Created Artifacts

- `src/power_framework/core/search_scope.py`: New module implementing typed exceptions, `ResolvedSearchScope`, and `compile_search_scope`.
- `src/power_framework/core/db.py`: Added `idx_chunk_embeddings_rel_path` index on `chunk_embeddings(rel_path)`.
- `src/power_framework/core/searcher.py`: Integrated `ResolvedSearchScope` pushdown across FTS, TF-vector, dense semantic, hybrid, reranked, and graph-assisted modes. Scoped query dense matrix caching.
- `tests/test_phase5c_search_scope.py`: Full 28-test verification suite covering defect reproduction, materialization counters, 25-dimension matrix, and security invariants.
- `artifacts/project-state/phase-5c/phase5c_baseline_evidence.json`: Baseline reproduction metrics.
- `artifacts/project-state/phase-5c/PHASE_5C_BASELINE.md`: Baseline defect profile.
- `artifacts/project-state/phase-5c/phase5c_post_fix_evidence.json`: Post-fix metrics confirming 0 out-of-scope materialization.
- `artifacts/project-state/phase-5c/PHASE_5C_REPORT.md`: Comprehensive Phase 5C execution and verification report.
