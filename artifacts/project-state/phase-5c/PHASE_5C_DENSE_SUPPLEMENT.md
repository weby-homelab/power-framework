# Phase 5C Evidence Supplement: Hermetic Non-Empty Dense Row Selection & Matrix Materialization

## 1. Context & Purpose

During P38-WP01-R1 closure verification (PR #437 / PR #438), the hermetic fixture ran with `sync_embeddings=False`, resulting in:
```text
dense.selected_total = 0
dense.out_of_scope = 0
```
While this honestly reflected an empty `chunk_embeddings` table, it left an evidence gap regarding whether `SearchScope` pushdown to SQLite `chunk_embeddings` and runtime matrix materialization (`_get_or_build_dense_matrix`) correctly and strictly selects in-scope rows when rows are present.

As mandated by Phase 5D Precondition B, this prerequisite evidence supplement hermetically verifies non-empty dense selection and materialization without model downloads, network calls, or BGE dependencies.

Historical R1 evidence in `artifacts/project-state/phase-5c/phase5c_r1_verification.json` and `PHASE_5C_R1_REPORT.md` remains unmodified as historical truth.

---

## 2. Test Execution & Methodology

Test module: `tests/test_phase5d_dense_prerequisite.py`

### Mechanism:
1. Vault initialized with configured domains: `projects` (`01_Projects`), `areas` (`02_Areas`), `research` (`03_Resources`).
2. Notes written across domains: `01_Projects/target.md`, `03_Resources/oos.md`, etc.
3. Vault synchronized atomically via `sync_vault_atomically(vault, sync_embeddings=False)`.
4. Deterministic synthetic float32 embeddings inserted directly into `chunk_embeddings` with valid timestamps and chunk IDs.
5. Generation state re-hashed in `generation-state.db` so the active generation cryptographic integrity contract (`resolve_active_generation`) is preserved.
6. `SearchScope` compiled for domain `projects`.
7. Direct SQLite chunk condition query executed with `chunk_sql, chunk_params = resolved_scope.build_chunk_condition("chunk_embeddings")`.
8. Runtime matrix materialization executed via `_get_or_build_dense_matrix(vault, db_path, dim, resolved_db, resolved_scope=resolved_scope)`.

---

## 3. Empirical Verification Results

```text
======================================================================
DENSE METRIC                               VALUE      REQUIREMENT
======================================================================
DENSE_ROWS_AVAILABLE                       2          > 0 (PASS)
IN_SCOPE_DENSE_ROWS_SELECTED               1          > 0 (PASS)
OUT_OF_SCOPE_DENSE_ROWS_SELECTED           0          == 0 (PASS)
OUT_OF_SCOPE_DENSE_ROWS_MATERIALIZED       0          == 0 (PASS)
IN_SCOPE_DENSE_ROWS_MATERIALIZED           1          > 0 (PASS)
MATERIALIZED_VECTOR_EXACT_MATCH            TRUE       TRUE (PASS)
EMPTY_SCOPE_MATRIX_SHAPE                   (0, 384)   (0, dim) (PASS)
MULTI_CHUNK_PROJECT_SELECTED               3          == 3 (PASS)
MULTI_CHUNK_OOS_SELECTED                   0          == 0 (PASS)
MULTI_DOMAIN_UNION_SELECTED                4          == 4 (PASS)
MULTI_DOMAIN_UNION_OOS_SELECTED            0          == 0 (PASS)
======================================================================
```

---

## 4. Disposition

The non-empty dense prerequisite test PASSES unconditionally across both direct SQL pushdown and runtime matrix materialization paths.

Precondition B is fully satisfied.
Phase 5C evidence gap is formally closed.
