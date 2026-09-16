# Phase 5C (P38-WP01) Baseline Evidence & Defect Profile

```text
EVIDENCE_TYPE: phase5c_baseline
CREATED_AT_UTC: 2026-09-16T10:41:00Z
BASE_SHA: 6c247c7e4c1788a8bd5388b1327170a8e7493852
BASE_TREE: 09a6266d6e4336cd3d4c0b7e50561828ae8470af
PYTHON_VERSION: 3.13.5
SQLITE_VERSION: 3.46.1
PLATFORM: Linux-7.0.14-16-pve-x86_64-with-glibc2.41
DATASET_REVISION: v1.1 (benchmarks/power38/retrieval_eval/v1.1)
QUERY_SET_DIGEST: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
```

---

## 1. Adversarial Starvation Defect Profile (Empirical Reproduction)

The defect was reproduced under pytest on the unmodified PR-B parent commit:
- **Test:** `tests/test_phase5c_search_scope.py::test_adversarial_domain_starvation_defect_reproduction`
- **Failure output:**
  ```text
  AssertionError: Domain starvation defect reproduced: target was starved by out-of-scope candidates! Returned: []
  assert '01_Projects/quantum_project.md' in []
  ```
- **Mechanism:**
  1. Corpus contains 30 out-of-scope resource notes with high BM25 term density for `quantum`.
  2. Corpus contains 1 in-scope project note (`01_Projects/quantum_project.md`) with moderate BM25 term density.
  3. Query `quantum` executed with `domain="projects"` and `max_results=3`.
  4. Global candidate selection queries `fts_notes MATCH 'quantum*' ORDER BY score DESC LIMIT 20`.
  5. All 20 candidate rows are from `03_Resources/`.
  6. Post-filter `_filter_domain_results` discards all 20 rows.
  7. Result set is empty (`[]`). **In-scope target is starved with 100% recall loss.**

---

## 2. Baseline Out-Of-Scope Materialization Counters

On the parent commit `6c247c7e4c1788a8bd5388b1327170a8e7493852`:

| Stage | Baseline Behavior | Out-Of-Scope Materialized | Target Invariant for Phase 5C |
|---|---|---|---|
| FTS Candidate Selection | Global query `LIMIT 20`, domain post-filtered | 20 / 20 candidates out-of-scope | `0` |
| TF-Vector Selection | `SELECT ... FROM tf_vectors JOIN fts_notes` loads entire vault | 30 / 31 rows out-of-scope | `0` |
| Dense Embedding Scoring | `SELECT chunk_id, rel_path, embedding FROM chunk_embeddings` loads all chunks into numpy matrix | 30 / 31 chunks out-of-scope | `0` |
| Reranker Input Pool | Candidates fused globally, top-20 sent to cross-encoder | 20 / 20 documents out-of-scope | `0` |
| Graph-Assisted Expansion | BFS traversal and `suggest_related_v2` run unconstrained | Out-of-scope neighbours traversed | `0` |
| Fallback Scan | `iter_vault_markdown_files` calls `read_source` on all files | 30 / 31 disk reads out-of-scope | `0` |
| Semantic Lexical Guard | Auxiliary `_fts_search` runs without scope | Unscoped lexical lookup | `0` out-of-scope candidates |

---

## 3. Required Implementation Architecture

To eliminate starvation and enforce zero out-of-scope materialization:
1. `SearchScope` resolution transforms request constraints into canonical SQL/projection filters.
2. FTS pushes scope into the SQL query:
   ```sql
   WHERE fts_notes MATCH ? AND (<scope_conditions>)
   ORDER BY score DESC LIMIT ?
   ```
3. TF-Vector pushes scope into `tf_vectors` selection:
   ```sql
   WHERE (<scope_conditions>)
   ```
4. Dense scoring queries only chunks of eligible notes:
   ```sql
   WHERE chunk_embeddings.rel_path IN (SELECT rel_path FROM source_metadata WHERE <scope_conditions>)
   ```
5. Reranker processes only the already-scoped candidate pool.
6. Graph BFS hops verify node eligibility before traversal or reading.
7. Fallback scan filters relative paths before calling `read_source`.
8. Final post-filtering retained strictly as defense-in-depth.
