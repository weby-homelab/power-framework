# Phase 5D R1 Runtime Closure Correction Report

**Work Package:** P38-WP02-R1  
**Phase:** Phase 5D — RetrievalPlanner / ContextPack Read-Only Vertical Slice  
**Base SHA:** `2a7784625552ac2a7e7aba71a1e5e272f96948d6` (PR-R1A merge commit)  
**PR Boundary:** PR-R1B (`fix/p38-wp02-r1-phase5d-runtime-closure`)  
**Status:** CLOSED / VERIFIED AFTER R1 CORRECTION  

---

## 1. Executive Summary

Phase 5D originally merged under PR #440 with several critical runtime and forensic defects that violated core framework invariants:
- Unsupported `project_ids` search scopes were caught and degraded rather than failing closed.
- Scope compilation errors were swallowed, permitting unauthenticated reads.
- Malformed domain policies were silently swallowed, returning empty default registries.
- Ordinary PARA-path notes and dense vector hits were automatically granted `Authority.CURATED`.
- Temporal freshness and contradiction states were invented (`Freshness.CURRENT`, `ContradictionState.NONE`).
- Stages without runtime execution (`GRAPH_ASSISTED`, `RERANK`, `RAW_FALLBACK`, and unavailable `SEMANTIC`) were marked `ATTEMPTED`.
- Cross-domain deduplication cross-contaminated candidate scores, provenances, and authorities.
- Documentation drifted between 256,000 and 2,000,000 byte limits.

In work package **P38-WP02-R1**, all 13 defects were reproduced via strict tests in PR-R1A (PR #442) and remediated with zero-mutation, fail-closed runtime code in PR-R1B.

---

## 2. Invariants Corrected & Forensic Audit

| # | Defect / Invariant | Pre-Fix Behavior (PR #440) | Post-Fix Behavior (PR-R1B) | Verification Evidence |
|---|---|---|---|---|
| 1 | `SCOPE FAILURE = FAIL CLOSED` | `project_ids` was caught and degraded into generic search | Raises `UnsupportedSearchScopeError` before reading any task, decision, or note | `test_r1_project_ids_unsupported_fails_closed_before_reads` |
| 2 | `SCOPE COMPILATION INTEGRITY` | `compile_search_scope` error was caught and logged as degraded | Calls `compile_search_scope` fail-closed before any candidate read | `test_r2_invalid_search_scope_stops_retrieval_before_reads` |
| 3 | `DOMAIN CONFIG INTEGRITY` | `_get_domain_registry` caught all exceptions and returned empty fallback | Direct call to `load_domain_policy` raises `DomainConfigError` on malformed config | `test_r3_malformed_domain_policy_fails_closed` |
| 4 | `PATH != AUTHORITY` | PARA path prefix automatically granted `Authority.CURATED` | FTS lexical search assigns `Authority.UNVERIFIED`, `TrustState.PROPOSED` | `test_r4_ordinary_para_path_fts_does_not_become_curated` |
| 5 | `RETRIEVAL STAGE != AUTHORITY` | Dense vector hits automatically granted `Authority.CURATED` | Vector search assigns `Authority.UNVERIFIED`, `TrustState.PROPOSED` | `test_r5_dense_hit_does_not_become_curated` |
| 6 | `NO INVENTED TEMPORAL STATE` | Assigned `Freshness.CURRENT` without date proof | Notes without validated dates assign `Freshness.UNKNOWN` | `test_r6_unknown_temporal_metadata_not_automatically_current` |
| 7 | `NO INVENTED CONTRADICTION STATE` | Assigned `ContradictionState.NONE` without detector | Notes without contradiction check assign `ContradictionState.UNKNOWN` | `test_r7_unknown_contradiction_state_not_automatically_none` |
| 8 | `ATTEMPTED MEANS EXECUTED` (Graph) | Marked `attempted_stages` without graph expansion | Marked `skipped_stages` with explanatory decision | `test_r8_graph_unavailable_skipped_not_attempted` |
| 9 | `ATTEMPTED MEANS EXECUTED` (Rerank) | Marked `attempted_stages` without reranker model | Marked `skipped_stages` with explanatory decision | `test_r9_reranker_unavailable_skipped_not_attempted` |
| 10 | `ATTEMPTED MEANS EXECUTED` (Raw) | Marked `attempted_stages` without raw fallback call | Marked `skipped_stages` with explanatory decision | `test_r10_raw_fallback_unavailable_skipped_not_attempted` |
| 11 | `ATTEMPTED EXECUTION BOUNDARY` | DEEP plan marked unexecuted stages as attempted | Only stages with real executed boundaries (`PROJECT_STATE`, `FTS`, ready `SEMANTIC`) in `attempted_stages` | `test_r11_attempted_stages_reflect_actual_execution_boundary` |
| 12 | `AUTHORITY BOUND TO PROVENANCE` | Dedup merged max score onto canonical item | Dedup preserves winning item's score, provenance, and authority intact | `test_r12_dedup_authority_remains_bound_to_supporting_provenance` |
| 13 | `MAX_CONTEXT_PACK_BYTES TRUTH` | Docs stated 256,000 bytes; runtime was 2,000,000 | Reconciled to runtime truth `2_000_000` bytes across contracts, compiler, and docs | `test_r13_runtime_byte_limit_matches_compiler_and_reported` |

---

## 3. Test Suite Matrix

```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-8.3.5
collected 66 items

tests/test_phase5d_application_service.py ...............                [ 22%]
tests/test_phase5d_authority_security.py ..............                  [ 43%]
tests/test_phase5d_context_compiler.py ...........                       [ 60%]
tests/test_phase5d_dense_prerequisite.py ...                             [ 65%]
tests/test_phase5d_r1_closure.py .............                           [ 84%]
tests/test_phase5d_retrieval_planner.py ..........                       [100%]

======================== 66 passed, 1 warning in 70.96s ========================
```

---

## 4. Verification Commands & Static Analysis

1. **Ruff Linter:**
   ```bash
   ruff check src/power_framework/core/retrieval_planner.py src/power_framework/core/application.py tests/test_phase5d_r1_closure.py tests/test_phase5d_authority_security.py tests/test_phase5d_retrieval_planner.py
   # Output: All checks passed!
   ```

2. **Ruff Formatter:**
   ```bash
   ruff format --check src/power_framework/core/retrieval_planner.py src/power_framework/core/application.py tests/test_phase5d_r1_closure.py tests/test_phase5d_authority_security.py tests/test_phase5d_retrieval_planner.py
   # Output: 5 files already formatted
   ```

3. **Workspace Integrity:**
   ```bash
   ./verify.sh
   # Output: ✅ Workspace validation completed successfully.
   ```

---

## 5. Branch Protection Contexts Required (11 Total)

All 11 required status checks on branch `main` are green and fully satisfied:
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
