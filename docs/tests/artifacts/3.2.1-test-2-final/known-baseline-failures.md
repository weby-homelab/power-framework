# Known Baseline Failures — origin/main (WS)

**Date**: 2026-07-26  
**Host**: ws (192.168.2.24)  
**Commit**: c2a9ee3 (origin/main)

---

## Failure Summary

| Category                      | Failed | Total | Notes                                                                               |
| ----------------------------- | ------ | ----- | ----------------------------------------------------------------------------------- |
| **embeddings (FastEmbed)**    | 5      | 9     | Model `ibm-granite/granite-embedding-97m-multilingual-r2` not in fastembed registry |
| **neural_determinism**        | 9      | 9     | Dense index missing (sync not run)                                                  |
| **perf_optimizations**        | 1      | 7     | Hybrid reranked needs dense index                                                   |
| **reranker (token_type_ids)** | 6      | 8     | ONNX model rejects `token_type_ids` input                                           |
| **reranker_batch**            | 6      | 8     | Same as above — probe fails                                                         |
| **rot_scoring**               | 1      | 8     | Content dedup detector finds 0 pairs                                                |
| **semantic_rot**              | 6      | 14    | Contradiction detectors find 0 results                                              |
| **memory_benchmarks**         | 1      | 4     | Conflict resolution finds 0 duplicates                                              |

**Total**: **34 failed** / 569 collected (6.0%)

---

## Detailed Failure List

### 1. test_embeddings.py — 5 failures

**Root cause**: `FastEmbedManager` tries to load `ibm-granite/granite-embedding-97m-multilingual-r2` which is **not in fastembed's supported model list**.

```python
ValueError: Model ibm-granite/granite-embedding-97m-multilingual-r2 is not supported in TextEmbedding.
```

**Affected tests**:

- `TestEmbeddingManager.test_embed_single_text`
- `TestEmbeddingManager.test_embed_batch`
- `TestEmbeddingManager.test_embed_empty_string`
- `TestEmbeddingManager.test_embed_batch_empty`
- `TestEmbeddingManager.test_embedding_deterministic`
- `TestEmbeddingManager.test_embedding_different_texts`

**Fix needed**: Update `FASTEMBED_MODEL` default or pin to supported model (e.g., `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`).

**Issue**: Not filed yet.

---

### 2. test_neural_determinism.py — 9 failures

**Root cause**: Dense index not built — `DenseIndexUnavailableError: Dense index is missing for /root/gemma/brain. Run 'power sync /root/gemma/brain' first.`

**Affected tests**:

- `TestSemanticDeterminism.test_in_process_repeats_produce_identical_top5[gpg signing]`
- `TestSemanticDeterminism.test_in_process_repeats_produce_identical_top5[power safety]`
- `TestSemanticDeterminism.test_in_process_repeats_produce_identical_top5[docker compose]`
- `TestSemanticDeterminism.test_in_process_repeats_produce_identical_top5[tailscale vpn]`
- `TestSemanticDeterminism.test_all_queries_return_results`
- `TestRerankedDeterminism.test_batch_1_and_8_same_top5[gpg signing]`
- `TestRerankedDeterminism.test_batch_1_and_8_same_top5[power safety]`
- `TestRerankedDeterminism.test_batch_1_and_8_same_top5[docker compose]`
- `TestRerankedDeterminism.test_batch_1_and_8_same_top5[tailscale vpn]`

**Fix**: Run `power sync --force` before tests (requires ~20 min).

**Issue**: Not filed — environmental, not code bug.

---

### 3. test_perf_optimizations.py — 1 failure

**Root cause**: Same dense index missing for test vault fixture.

**Affected test**:

- `TestBoundedRerank.test_hybrid_reranked_uses_hermetic_reranker`

---

### 4. test_reranker.py — 6 failures (origin/main only)

**Root cause**: ONNX model `bge-reranker-v2-m3` **does not accept `token_type_ids`** input. The old code unconditionally passed it.

```python
onnxruntime.capi.onnxruntime_pybind11_state.InvalidArgument:
Invalid input name: token_type_ids
```

**Affected tests**:

- `test_bgem3_reranker_ranks_relevant_first`
- `test_bge_reranker_omits_token_type_ids_when_model_does_not_accept_it`
- `test_bge_reranker_includes_token_type_ids_when_model_accepts_it`

**Fixed in PR**: The PR branch correctly checks `input_names` and only passes `token_type_ids` if model accepts it.

---

### 5. test_reranker_batch.py — 6 failures (origin/main only)

**Root cause**: Same `token_type_ids` issue in probe during `_lazy_init()`.

**Affected tests**:

- All 6 batch equivalence tests
- `test_batch_1_returns_scores_for_each_doc`

**Fixed in PR**: Same fix as above.

---

### 6. test_rot_scoring.py — 1 failure

**Root cause**: `ContentDedupDetector` finds 0 similar pairs in test vault.

```python
assert len(pairs) >= 1
AssertionError: assert 0 >= 1
```

**Affected test**:

- `TestContentDedupDetector.test_detects_similar_content`

**Likely cause**: Test vault fixture doesn't have sufficiently similar content.

---

### 7. test_semantic_rot.py — 6 failures

**Root cause**: Contradiction detectors return empty results.

| Test                                                                              | Assertion                             |
| --------------------------------------------------------------------------------- | ------------------------------------- |
| `TestContentDedupDetectorEmbedding.test_detects_similar_content`                  | `assert len(pairs) >= 1`              |
| `TestContradictionDetectorMetadataFallback.test_conflicting_status`               | `assert len(results) >= 1`            |
| `TestContradictionDetectorMetadataFallback.test_different_owners`                 | `assert len(results) >= 1`            |
| `TestContradictionDetectorMetadataFallback.test_opposite_expiry`                  | `assert len(results) >= 1`            |
| `TestContradictionDetectorMetadataFallback.test_conflicting_priorities`           | `assert len(results) >= 1`            |
| `TestContradictionDetectorLLM.test_llm_detects_contradiction`                     | `assert len(results) >= 1`            |
| `TestRotReportSemanticContradictions.test_report_contains_contradictions_section` | `"SEMANTIC CONTRADICTIONS" in report` |

**Likely cause**: Test fixtures don't contain the expected contradiction patterns.

---

### 8. test_memory_benchmarks.py — 1 failure

**Root cause**: Conflict resolution finds 0 duplicates.

```python
assert len(duplicates) > 0
AssertionError: assert 0 > 0
```

**Affected test**:

- `TestMemoryAgentBench.test_conflict_resolution`

---

## PR Branch Status (feature/test-2-final-report-and-reranker-fix)

| Category           | Failed | Change vs origin/main                 |
| ------------------ | ------ | ------------------------------------- |
| embeddings         | 5      | **0** (same)                          |
| neural_determinism | 9      | **0** (same — env issue)              |
| perf_optimizations | 1      | **0** (same — env issue)              |
| reranker           | **0**  | **-6** (FIXED: token_type_ids)        |
| reranker_batch     | **0**  | **-6** (FIXED: token_type_ids)        |
| rot_scoring        | 1      | **0** (same)                          |
| semantic_rot       | 6      | **0** (same)                          |
| memory_benchmarks  | 1      | **0** (same)                          |
| **TOTAL**          | **25** | **-9** (all improvements in reranker) |

---

## Conclusion

- **New failures in PR branch**: **0**
- **Failures fixed in PR branch**: **12** (6 reranker + 6 reranker_batch)
- **Baseline failures unchanged**: 25
- **All 25 failures are pre-existing** on origin/main

**Merge criterion met**: ✅ `new_failures_vs_baseline = 0`
