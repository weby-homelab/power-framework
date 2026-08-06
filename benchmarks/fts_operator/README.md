# POWER FTS Operator A/B Benchmark (OR vs AND)

Методологічно коректний, відтворюваний парний (paired) benchmark, який
порівнює SQLite FTS5 булеві оператори `OR` і `AND` на одному corpus snapshot,
одному query set і **незалежному** qrels set.

## Правило № 1: жодного circular evaluation

Канонічні qrels **не можуть** будуватися за правилом `all(term in document)` —
це AND-подібне lexical правило, яке робить порівняння операторів циклічним
(evaluation leakage). Усі qrels читаються лише з frozen fixture через
`ground_truth.load_qrels`, який вимагає явного `independence_declaration`
і відмовляє (fail-closed), якщо provenance не доводить незалежність від FTS,
lexical term-AND або OR/AND runs.

## Ground truth

Використовується frozen synthetic dataset `benchmarks/power31/dataset/v1`:

- corpus: 100 документів (50 тем × UA/EN), закомічені, з sha256 у `corpus-manifest.json`;
- queries: 228 (страти `ua_to_ua`, `en_to_en`, `ua_to_en`, `en_to_ua`; 208 answerable + 20 no-answer);
- qrels: 416 записів, призначені **topic-membership правилом**
  (`synthetic-generator-v1`, rubric 1.0) — не FTS-виводом, не lexical term-AND,
  не OR/AND runs;
- provenance: `fixtures/ground_truth_provenance.json` (обов'язковий для runner).

Dataset **синтетичний** — це development evidence, не human-quality
certification. Приватні human M2 qrels та sealed holdout цим harness ніколи
не використовуються.

## Запуск (один command)

```bash
python benchmarks/fts_operator/scripts/run_benchmark.py \
  --dataset benchmarks/power31/dataset/v1 \
  --provenance benchmarks/fts_operator/fixtures/ground_truth_provenance.json \
  --output benchmarks/fts_operator/results/run-20260806 \
  [--top-k 10] [--seed 20260801] [--samples 10000]
```

Runner:

1. матеріалізує vault у temp-директорії;
2. синхронізує **один** FTS-індекс (обидва variants використовують той самий index);
3. виконує `search_vault(mode="fts")` під `POWER_FTS_OPERATOR=OR`, потім `=AND`
   (scoped env context — жодного leakage між variants);
4. рахує метрики, paired deltas, paired bootstrap 95% CI, win/tie counts;
5. генерує артефакти.

## Артефакти (на кожен run)

```text
manifest.json      — commit, POWER/Python/SQLite версії, corpus/query/qrels sha256,
                     variants, BM25 weights, code_changed_between_variants
per_query.csv      — query × OR/AND діагностика (result counts, top10, hits, ranks, ...)
summary.csv        — агрегати по всіх метриках і групах запитів
comparison.json    — метрики, deltas, wins/ties, zero-result, висновок
comparison.md      — human-readable звіт
bootstrap.json     — paired bootstrap CI для primary метрик
failures.json      — query-level failures (якщо є)
```

## Метрики

`nDCG@5/10`, `Recall@5/10`, `MRR@5/10`, `Precision@5/10`, `HitRate@5/10`,
`zero-result rate`, `result count` (mean/median). Primary метрики для
висновку: `nDCG@5`, `Recall@10`, `MRR@5`, `zero-result rate`.

## Політика висновків

Висновок детермінований (`compare.derive_conclusion`):

- `OR preferred` / `AND preferred` — лише за узгодженості ≥ 3 з 4 primary метрик;
- `no clear winner` — різниці в межах practical delta (0.02);
- `insufficient evidence` — sample < 20;
- AND **блокований** як default, якщо він погіршує `Recall@10` або підвищує
  `zero-result` (RAG candidate-retrieval policy).

`DEFAULT_FTS_OPERATOR` у `searcher.py` цим benchmark не змінюється — зміна
production default є окремим architecture/release рішенням.

## Тести

```bash
pytest tests/test_fts_operator_benchmark.py -v
```

Покриття: operator semantics, env isolation, ground-truth guard, bias
demonstration (alpha/beta/gamma), метрики, paired deltas, zero-result,
bootstrap determinism, end-to-end hermetic run на мініатюрному corpus.

## Ліміти

- Синтетичний corpus — результати є development evidence, не production quality.
- У query set немає single-term запитів (там OR == AND за конструкцією).
- Human M2 qrels приватні та недоступні для цього harness.
