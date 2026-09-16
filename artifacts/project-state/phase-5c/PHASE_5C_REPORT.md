# Phase 5C (P38-WP01) Execution & Verification Report

```text
EVIDENCE_TYPE: phase5c_execution_report
CREATED_AT_UTC: 2026-09-16T11:00:00Z
BASE_SHA: 6c247c7e4c1788a8bd5388b1327170a8e7493852
PYTHON_VERSION: 3.13.5
SQLITE_VERSION: 3.46.1
PLATFORM: Linux-7.0.14-16-pve-x86_64-with-glibc2.41
DATASET_REVISION: v1.1 (benchmarks/power38/retrieval_eval/v1.1)
QUERY_SET_DIGEST: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
STATUS: VERIFIED
```

---

## 1. Executive Summary

Phase 5C (P38-WP01 — SearchScope Pushdown) eliminates the adversarial candidate starvation defect where out-of-scope notes with high lexical or dense similarity displaced valid in-scope documents before post-retrieval filtering could be applied.

The implementation enforces the foundational invariant **"SCOPE BEFORE CANDIDATES"**:
1. All candidate generation stages (FTS BM25, TF vector, Dense chunk embeddings, Graph BFS, Fallback bounded scan, Reranker input pooling) compile and push `SearchScope` constraints directly into the earliest storage and retrieval predicates.
2. Across all 6 materialization boundaries, out-of-scope rows materialized are strictly `0`.
3. The adversarial candidate starvation test is resolved: in-scope recall improved from `0.0` (starvation) to `1.0` (winner retrieved).
4. Security fail-closed rules prevent authority escalation: unsupported dimensions (`trust_states`, `project_ids`) and unauthorized access to privileged boundaries (`include_archived`, `include_quarantine`) fail closed with typed exceptions.

---

## 2. Adversarial Starvation Resolution

| Metric | Baseline (Pre-Pushdown) | Post-Pushdown (Phase 5C) | Status |
|---|---|---|---|
| In-Scope Target Retrieved | `False` (`[]` empty result) | `True` (`01_Projects/quantum_project.md`) | RESOLVED |
| In-Scope Recall | `0.0` | `1.0` | 100% Target Retrieval |
| Out-Of-Scope Candidates at FTS Boundary | 20 / 20 | **0** | ELIMINATED |
| Out-Of-Scope Candidates at TF Boundary | 30 / 31 | **0** | ELIMINATED |
| Out-Of-Scope Dense Chunks Scored | 30 / 31 | **0** | ELIMINATED |
| Out-Of-Scope Rerank Documents | 20 / 20 | **0** | ELIMINATED |
| Out-Of-Scope Fallback File Reads | 30 / 31 | **0** | ELIMINATED |

---

## 3. Implementation Details

1. **`power_framework.core.search_scope`:**
   - Typed exception hierarchy: `SearchScopeError`, `UnsupportedSearchScopeError`, `SearchScopeAccessDeniedError`, `UnknownDomainError`.
   - `ResolvedSearchScope`: Encapsulates canonical domains, path prefixes, source types, temporal exclusions, archive and quarantine permissions.
   - SQL Builders:
     - `build_fts_condition()`: Pushes SQL predicates into `fts_notes` (`rel_path` and `note_type`).
     - `build_vector_condition()`: Pushes SQL predicates into `tf_vectors JOIN fts_notes`.
     - `build_chunk_condition()`: Pushes SQL predicates into `chunk_embeddings` with `idx_chunk_embeddings_rel_path`.
   - In-memory checker: `is_path_in_scope(rel_path, note_type)` used for BFS graph traversal and fallback scanning.
   - Deterministic digest: `canonical_scope_digest()` ensures scoped query cache isolation.
   - Fail-closed security validation for privileged flags (`include_archived`, `include_quarantine`) requiring server-issued `AccessPolicy`.

2. **`power_framework.core.db`:**
   - Added index `idx_chunk_embeddings_rel_path ON chunk_embeddings(rel_path)` in `_init_db` for fast chunk scope filtering.

3. **`power_framework.core.searcher`:**
   - Updated `_DenseMatrixCacheKey` to include `scope_digest`, preventing cross-scope embedding cache poisoning.
   - Updated `_get_or_build_dense_matrix` to query chunks matching `chunk_sql`, avoiding loading out-of-scope embeddings. Returns empty matrix if scope has 0 notes.
   - Pushed scope into `_fts_search`, `_vector_search`, `_hybrid_search`, `_hybrid_reranked_search`, `_graph_assisted_search`, and `_scan_and_search`.
   - Removed legacy overfetch heuristic (`max(max_results * 5, 20)`), querying exact `max_results` directly.

---

## 4. Verification Receipts

- **Phase 5C Test Suite:**
  ```text
  tests/test_phase5c_search_scope.py::test_adversarial_domain_starvation_defect_reproduction PASSED
  tests/test_phase5c_search_scope.py::test_stage_materialization_counters_zero PASSED
  tests/test_phase5c_search_scope.py::test_dimension_single_domain_pushdown PASSED
  tests/test_phase5c_search_scope.py::test_dimension_multi_domain_union_pushdown PASSED
  tests/test_phase5c_search_scope.py::test_dimension_exact_file_path_prefix PASSED
  tests/test_phase5c_search_scope.py::test_dimension_directory_path_prefix PASSED
  tests/test_phase5c_search_scope.py::test_dimension_directory_prefix_collision_safety PASSED
  tests/test_phase5c_search_scope.py::test_dimension_wildcard_sql_escaping PASSED
  tests/test_phase5c_search_scope.py::test_dimension_source_types_single PASSED
  tests/test_phase5c_search_scope.py::test_dimension_source_types_multi PASSED
  tests/test_phase5c_search_scope.py::test_dimension_source_types_mismatch_zero_results PASSED
  tests/test_phase5c_search_scope.py::test_dimension_temporal_boundary_current_view PASSED
  tests/test_phase5c_search_scope.py::test_dimension_temporal_boundary_historical_view PASSED
  tests/test_phase5c_search_scope.py::test_dimension_temporal_boundary_all_view PASSED
  tests/test_phase5c_search_scope.py::test_dimension_temporal_starvation_elimination PASSED
  tests/test_phase5c_search_scope.py::test_dimension_archived_excluded_by_default PASSED
  tests/test_phase5c_search_scope.py::test_dimension_quarantine_excluded_by_default PASSED
  tests/test_phase5c_search_scope.py::test_security_unsupported_trust_states_fails_closed PASSED
  tests/test_phase5c_search_scope.py::test_security_unsupported_project_ids_fails_closed PASSED
  tests/test_phase5c_search_scope.py::test_security_unknown_domain_fails_closed PASSED
  tests/test_phase5c_search_scope.py::test_security_privileged_archive_without_policy_denied PASSED
  tests/test_phase5c_search_scope.py::test_security_privileged_archive_with_unprivileged_policy_denied PASSED
  tests/test_phase5c_search_scope.py::test_security_privileged_archive_with_valid_policy_allowed PASSED
  tests/test_phase5c_search_scope.py::test_security_privileged_quarantine_without_policy_denied PASSED
  tests/test_phase5c_search_scope.py::test_security_privileged_quarantine_with_unprivileged_policy_denied PASSED
  tests/test_phase5c_search_scope.py::test_security_privileged_quarantine_with_valid_policy_allowed PASSED
  tests/test_phase5c_search_scope.py::test_retrieval_modes_pushdown_all_modes PASSED
  tests/test_phase5c_search_scope.py::test_backward_compatibility_unscoped_search PASSED
  ============================= 28 passed in 26.93s ==============================
  ```

- **Regression & Quality Gates:**
  - `tests/test_searcher.py`: 103 passed.
  - `tests/test_phase5a_runtime_contracts.py` & `tests/test_phase5b_domain_routing.py`: 74 passed.
  - `ruff check src tests`: 0 issues found.
  - `mypy src/power_framework`: 0 issues found in 123 source files.
