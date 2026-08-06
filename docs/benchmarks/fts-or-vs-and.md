# FTS Operator A/B: SQLite FTS5 OR vs AND

## Status

- Date: 2026-08-06
- Commit: `55a0a843072c50482ca9c19dcc01ad3eef5e4a66`
- P.O.W.E.R. version: 3.3.2
- Conclusion: **OR preferred** — `DEFAULT_FTS_OPERATOR = "OR"` in
  `src/power_framework/core/searcher.py` remains unchanged. No code change is
  recommended based on this evidence.

## Why this benchmark exists

P.O.W.E.R.'s FTS search reads the boolean operator from `POWER_FTS_OPERATOR`
(`OR` or `AND`, default `OR`). Before this benchmark there was **no evidence**
for the default: no committed artifacts, no ground truth, and no comparison
procedure. Historical checks (e.g. the lexical term-AND ground truth in
`scripts/check_search_quality.py`) were diagnostics, not operator benchmarks.
This work adds a reproducible, hermetic, methodologically guarded A/B harness.

## How to reproduce

```bash
python benchmarks/fts_operator/scripts/run_benchmark.py \
  --dataset benchmarks/power31/dataset/v1 \
  --provenance benchmarks/fts_operator/fixtures/ground_truth_provenance.json \
  --output benchmarks/fts_operator/results/run-<date> \
  --samples 10000
```

The run writes `manifest.json`, `per_query.csv`, `summary.csv`,
`comparison.json`, `comparison.md`, `bootstrap.json`, `failures.json` into the
output directory. Exit code 0 means the run completed and artifacts were
written; the conclusion is data driven and may be "no clear winner" or
"insufficient evidence".

## Methodology (what changed between variants)

1. **One immutable index** — the corpus is materialised into a temporary vault
   and the FTS index is synced exactly once (`_sync_vault_to_db(..., sync_embeddings=False)`)
   before either variant runs. The index does not differ between OR and AND.
2. **Only the operator changes** — `POWER_FTS_OPERATOR` is switched with a
   scoped context manager that restores the previous environment afterwards
   (unlike `benchmarks/power31/scripts/evaluation/run_release_evaluation.py`,
   which mutates `POWER_SEARCH_DB` without restoring it).
3. **Fixed variables** — SQLite FTS5 `unicode61` tokenizer, query preprocessing
   (quoted phrases, hyphenated identifiers, stopword filtering, prefix
   wildcards), BM25 weights `{title: 10.0, tags: 5.0, description: 3.0,
content: 1.0}`, `max_results=10`, deterministic local synonym expansion, one
   search mode (`fts`), temporal view `all`.
4. **Independent ground truth** — qrels from the frozen synthetic
   `benchmarks/power31/dataset/v1` dataset (100 corpus documents, 228 queries,
   416 graded relevance judgments by topic-membership rule,
   `synthetic-generator-v1`). They are not derived from FTS output, not from
   any lexical term-AND rule, and not from OR/AND operator runs. Provenance is
   enforced at load time by the harness (`ground_truth.py`) — a qrels file
   without the independence declaration is rejected.
5. **Paired design** — every query is scored under both operators; metrics are
   compared per query; significance via paired bootstrap (10,000 resamples,
   fixed seed 20260801) with a 95% CI on each Δ.
6. **Zero-result diagnostics** — AND is blocked from being declared the winner
   if it raises the zero-result rate by more than +0.05 or lowers recall@10
   (RAG candidate retrieval must not silently drop queries).

## Results (synthetic development evidence)

| Metric           |     OR |    AND | Δ AND−OR | Winner               |
| ---------------- | -----: | -----: | -------: | -------------------- |
| nDCG@5           | 0.6069 | 0.0821 |  −0.5249 | OR                   |
| nDCG@10          | 0.6223 | 0.0821 |  −0.5402 | OR                   |
| Recall@5         | 0.5614 | 0.0570 |  −0.5044 | OR                   |
| Recall@10        | 0.6250 | 0.0570 |  −0.5680 | OR                   |
| MRR@5            | 0.6374 | 0.0987 |  −0.5387 | OR                   |
| MRR@10           | 0.6407 | 0.0987 |  −0.5420 | OR                   |
| Precision@5      | 0.2342 | 0.0788 |  −0.1554 | OR                   |
| Precision@10     | 0.1734 | 0.0778 |  −0.0956 | OR                   |
| HitRate@5        | 0.8772 | 0.1096 |  −0.7675 | OR                   |
| HitRate@10       | 0.8991 | 0.1096 |  −0.7895 | OR                   |
| zero-result rate | 0.0263 | 0.8246 |  +0.7982 | OR (lower is better) |

- Queries: 228 (multi-term ≥ 2). Failures: 0.
- AND returned **zero results for 82.5%** of queries vs 2.6% for OR; 182
  queries were "newly lost" by AND (OR found relevant documents, AND returned
  nothing).
- Wins/ties for recall@10: AND 0 / OR 188 / ties 40. Bootstrap 95% CI for
  Δ recall@10 ∈ [−0.6118, −0.5241] — entirely on the OR side.
- Conclusion: OR favors 4/4 primary metrics (nDCG@5, Recall@10, MRR@5,
  zero-result).

Interpretation: multi-term queries (2–9 terms in this dataset) almost always
contain a term that fails under strict AND with the `unicode61` tokenizer
(stopwords, inflected Ukrainian/English tokens, phrase quoting), so AND
degenerates to empty results. OR with BM25 ranking surfaces the relevant
document instead.

## Limitations and claims policy

- The qrels are **synthetic, machine-assigned development evidence**
  (`human_judged: false`). They are not human judgments and cannot certify
  production-quality behaviour on a real vault.
- This benchmark does **not** evaluate hybrid/reranked modes, vector search,
  or the real `/root/gemma/brain` vault (empty at the time of writing; human
  M2 qrels remain private/sealed).
- Per the claim policy, this result only justifies keeping the current OR
  default; it is not a claim that OR is optimal for every corpus. For real
  bilingual vaults, run the harness on your own corpus before changing
  anything.

## Harness layout

- `benchmarks/fts_operator/scripts/run_benchmark.py` — single-command runner.
- `benchmarks/fts_operator/scripts/ground_truth.py` — qrels loading + independence guard.
- `benchmarks/fts_operator/scripts/metrics.py` — nDCG/Recall/MRR/Precision/HitRate, first-rank, zero-result.
- `benchmarks/fts_operator/scripts/bootstrap.py` — paired bootstrap CI (deterministic seed).
- `benchmarks/fts_operator/scripts/compare.py` — paired comparison, conclusion policy, markdown report.
- `benchmarks/fts_operator/configs/{fts_or,fts_and}.yaml` — variant configs (operator only).
- `benchmarks/fts_operator/fixtures/ground_truth_provenance.json` — mandatory provenance fixture.
- `tests/test_fts_operator_benchmark.py` — 36 hermetic regression tests (operator semantics, env scoping, GT guard, bias demo, metrics, paired comparison, bootstrap determinism, e2e run).
- `benchmarks/fts_operator/results/run-20260806/` — committed artifacts of the canonical run.
