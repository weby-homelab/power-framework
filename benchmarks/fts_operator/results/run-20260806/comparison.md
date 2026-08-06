# POWER FTS Operator A/B Benchmark

## Purpose

Compare SQLite FTS5 boolean operators OR and AND on the same corpus, query set, qrels, tokenizer, BM25 weighting and index; the only independent variable is `POWER_FTS_OPERATOR`.

## Methodology

Paired A/B: every query is evaluated under both operators with identical preprocessing (quoted phrases, prefix wildcards, stopword filtering, hyphenated identifier quoting), identical BM25 weights and one immutable FTS index (synced once before both variants). Environment is switched with a scoped `POWER_FTS_OPERATOR` context; provenance is recorded in `manifest.json`.

## Ground truth provenance

Qrels: `/root/geminicli/projects/P.O.W.E.R/benchmarks/power31/dataset/v1/qrels.synthetic.jsonl` (sha256 `e550f7863685...`). Provenance: `benchmarks/fts_operator/fixtures/ground_truth_provenance.json` (sha256 `121187187c42...`). The qrels are assigned by topic membership (synthetic-generator-v1, rubric 1.0), not by FTS output, not by any lexical term-AND rule, and not by OR/AND operator runs. They are SYNTHETIC development evidence; they are not human judgments and not a production-quality certification.

## Corpus

- Snapshot: `/root/geminicli/projects/P.O.W.E.R/benchmarks/power31/dataset/v1/corpus` (hash `e80778a480cdc99360c99c2ae017a5813318299a31ec89904d0d3e77617858d4`)
- Documents: 100

## Query set

- Total queries: 228
- UA: 0
- EN: 114
- ua_to_ua: 59
- en_to_en: 59
- ua_to_en: 55
- en_to_ua: 55
- Multi-term (>= 2 meaningful FTS terms): 228

## Fixed variables

tokenizer (unicode61), query preprocessing, stopwords, BM25 weights {'title': 10.0, 'tags': 5.0, 'description': 3.0, 'content': 1.0}, max_results=10, query expansion (deterministic local synonyms), index generation (single sync), Python/SQLite runtime. See `manifest.json`.

## Independent variable

`POWER_FTS_OPERATOR`: `OR` (variant `fts_or`) vs `AND` (variant `fts_and`).

## Metrics

nDCG@5/10, Recall@5/10, MRR@5/10, Precision@5/10, HitRate@5/10, zero-result rate, result counts, per-query deltas, wins/ties, paired bootstrap 95% CI.

## Overall results

| Metric | OR | AND | Δ AND-OR | Winner |
|--------|----:|----:|---------:|--------|
| ndcg@5 | 0.6069 | 0.0821 | -0.5249 | OR |
| recall@5 | 0.5614 | 0.0570 | -0.5044 | OR |
| precision@5 | 0.2342 | 0.0788 | -0.1554 | OR |
| mrr@5 | 0.6374 | 0.0987 | -0.5387 | OR |
| hit_rate@5 | 0.8772 | 0.1096 | -0.7675 | OR |
| relevant_hits@5 | 1.1009 | 0.1140 | -0.9868 | OR |
| ndcg@10 | 0.6223 | 0.0821 | -0.5402 | OR |
| recall@10 | 0.6250 | 0.0570 | -0.5680 | OR |
| precision@10 | 0.1734 | 0.0778 | -0.0956 | OR |
| mrr@10 | 0.6407 | 0.0987 | -0.5420 | OR |
| hit_rate@10 | 0.8991 | 0.1096 | -0.7895 | OR |
| relevant_hits@10 | 1.2193 | 0.1140 | -1.1053 | OR |
| first_relevant_rank | 1.6184 | 0.1316 | -1.4868 | OR |
| zero_result | 0.0263 | 0.8246 | +0.7982 | AND |
| result_count | 7.4386 | 0.3333 | -7.1053 | OR |

## Zero-result analysis

- OR zero-result rate: 0.0263 (mean result count 7.44, median 8.50)
- AND zero-result rate: 0.8246 (mean result count 0.33, median 0.00)
- Absolute zero-result difference: +0.7982

- Queries newly lost by AND (OR found relevant docs, AND returned zero): 182
  - QUU0001 (`як оптимізувати Docker образи через multi-stage build`) — OR relevant hits@10: 2, AND: 0
  - QEE0001 (`how to optimize Docker images with multi-stage build`) — OR relevant hits@10: 2, AND: 0
  - QUE0001 (`як оптимізувати Docker образи через multi-stage build`) — OR relevant hits@10: 2, AND: 0
  - QEU0001 (`how to optimize Docker images with multi-stage build`) — OR relevant hits@10: 2, AND: 0
  - QUU0002 (`як налаштувати Docker Compose мережі та volumes`) — OR relevant hits@10: 2, AND: 0
  - QEE0002 (`how to configure Docker Compose networks and volumes`) — OR relevant hits@10: 2, AND: 0
  - QUE0002 (`як налаштувати Docker Compose мережі та volumes`) — OR relevant hits@10: 2, AND: 0
  - QEU0002 (`how to configure Docker Compose networks and volumes`) — OR relevant hits@10: 2, AND: 0
  - QUU0003 (`як розгорнути Kubernetes кластер з k3s`) — OR relevant hits@10: 2, AND: 0
  - QEE0003 (`how to deploy Kubernetes cluster with k3s`) — OR relevant hits@10: 2, AND: 0

## OR wins / AND wins / ties

| Metric | AND wins | OR wins | Ties |
|--------|---------:|--------:|-----:|
| ndcg@5 | 0 | 182 | 46 |
| ndcg@10 | 0 | 188 | 40 |
| recall@5 | 0 | 182 | 46 |
| recall@10 | 0 | 188 | 40 |
| mrr@5 | 0 | 175 | 53 |
| mrr@10 | 0 | 180 | 48 |

## Paired bootstrap (10,000 resamples, fixed seed)

| Metric | Δ AND-OR | 95% CI |
|--------|---------:|--------|
| ndcg@5 | -0.5249 | [-0.5664, -0.4821] |
| recall@5 | -0.5044 | [-0.5461, -0.4627] |
| recall@10 | -0.5680 | [-0.6118, -0.5241] |
| mrr@5 | -0.5387 | [-0.5885, -0.4884] |

## Query-class results

| Group | n | Recall@10 OR | Recall@10 AND | Δ | Zero% OR | Zero% AND |
|-------|--:|-------------:|--------------:|--:|---------:|----------:|
| all | 228 | 0.6250 | 0.0570 | -0.5680 | 0.0263 | 0.8246 |
| uk | 114 | 0.5965 | 0.0219 | -0.5746 | 0.0526 | 0.9298 |
| ua_to_ua | 59 | 0.6186 | 0.0339 | -0.5847 | 0.0508 | 0.9322 |
| long_queries | 182 | 0.6484 | 0.0357 | -0.6126 | 0.0000 | 0.8901 |
| en | 114 | 0.6535 | 0.0921 | -0.5614 | 0.0000 | 0.7193 |
| en_to_en | 59 | 0.7034 | 0.1441 | -0.5593 | 0.0000 | 0.7288 |
| ua_to_en | 55 | 0.5727 | 0.0091 | -0.5636 | 0.0545 | 0.9273 |
| en_to_ua | 55 | 0.6000 | 0.0364 | -0.5636 | 0.0000 | 0.7091 |
| short_queries | 46 | 0.5326 | 0.1413 | -0.3913 | 0.1304 | 0.5652 |

## Example queries where OR wins

- QEE0004 (`what is Kubernetes networking and Ingress`): Recall@10 OR 1.00 vs AND 0.50
- QEU0004 (`what is Kubernetes networking and Ingress`): Recall@10 OR 1.00 vs AND 0.50
- QUU0005 (`як налаштувати CI/CD пайплайн з GitHub Actions`): Recall@10 OR 0.50 vs AND 0.00
- QEE0005 (`how to set up CI/CD pipeline with GitHub Actions`): Recall@10 OR 0.50 vs AND 0.00
- QUE0005 (`як налаштувати CI/CD пайплайн з GitHub Actions`): Recall@10 OR 0.50 vs AND 0.00
- QEU0005 (`how to set up CI/CD pipeline with GitHub Actions`): Recall@10 OR 0.50 vs AND 0.00
- QUU0006 (`що таке Terraform Infrastructure as Code`): Recall@10 OR 0.50 vs AND 0.00
- QUE0006 (`що таке Terraform Infrastructure as Code`): Recall@10 OR 0.50 vs AND 0.00
- QUU0007 (`як автоматизувати конфігурацію серверів з Ansible`): Recall@10 OR 0.50 vs AND 0.00
- QEE0007 (`how to automate server configuration with Ansible`): Recall@10 OR 0.50 vs AND 0.00

## Example queries where AND wins


## Failure analysis

No query-level failures.

## Conclusion

**OR preferred** — OR favors 4/4 primary metrics

## Limitations

- Synthetic corpus (100 generated documents, 50 bilingual topics); relevance is rule-assigned by topic membership, not human judgments.
- The canonical human M2 qrels are private and were not used; results are development evidence only and are not a production-quality certification.
- The query set has no single-term queries (OR == AND there by construction), so the comparison concentrates on multi-term behavior.
- Commit: 55a0a843072c50482ca9c19dcc01ad3eef5e4a66; POWER 3.3.2; Python 3.13.5; SQLite 3.46.1
