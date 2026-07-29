# POWER 3.2.0 release evidence

POWER 3.2.0 implements the July 2026 remediation plan. It remains beta: the
release record distinguishes completed code changes from release gates that
still require measured evidence.

## Remediation summary

| WTF                          | Status        | Change                                                                                                                                                                                  |
| :--------------------------- | :------------ | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #1 Fake UDCG                 | **Partial**   | Curated bilingual semantic GT and graded nDCG are implemented. `udcg_real.py` is not yet an independently validated EACL-2026 UDCG implementation, so no UDCG production claim is made.        |
| #2 CC-BY-NC reranker default | **Fixed**     | Default switched to `BGEM3Reranker` (MIT ONNX). Jina requires `POWER_RERANKER=jina AND POWER_ALLOW_NONCOMMERCIAL_MODELS=1`.                                                             |
| #3 Silent fallback on TF     | **Fixed**     | Unknown `POWER_EMBED_PROVIDER` raises `RuntimeError`. Fallback permitted only with `POWER_ALLOW_DENSE_FALLBACK=1` env gate; contract recorded in `SearchResult.retrieval_contract`.     |
| #4 OKF description ≤150      | **Fixed**     | `max_length` removed from Pydantic schema. Truncation applied only in catalog render (`index.md`/`_index.md`).                                                                          |
| #5 Half-manual Graph RAG     | **Foundation only** | Auto-triplet extraction (`graph_extraction.py`) uses a deterministic regex-based extractor. M1.2 stores its output as reviewable SQLite candidates; only explicit approval writes accepted `relations`. Semantic suggest remains available via `suggest_related_semantic`. |
| #6 SQLite locks              | **Fixed**     | Single-writer `asyncio.Queue` worker (`write_queue.py`). Write operations serialized; reads parallel.                                                                                   |
| Memory contract ≤12 GB       | **Pending**   | Model SHA pins and bounded runtime configuration are present; an RSS measurement on the target hardware is still required.                                                                 |

## What is pinned

| Artifact                  | Location                                                                                   |
| :------------------------ | :----------------------------------------------------------------------------------------- |
| Canonical embedding model | `release/models.lock.json` → `canonical_embedding` (bge-m3-onnx, MIT)                      |
| Canonical reranker model  | `release/models.lock.json` → `canonical_reranker` (bge-reranker-v2-m3-onnx, MIT)           |
| Optional reranker         | `release/models.lock.json` → `optional_reranker` (jina-reranker-v2, CC-BY-NC-4.0)          |
| Semantic ground truth     | Packaged `power_framework/data/semantic_gt.json` — 16 bilingual UA+EN queries with graded relevance (0–3); evaluation scripts accept an explicit fixture path for governed holdouts |
| ADR baseline              | `docs/adr/0001-power-3.1-trust-release-baseline.md`                                        |

## Benchmark status

The semantic GT (`--gt-mode semantic`) replaces the legacy term-AND proxy for
production quality claims. The lexical mode (`--gt-mode lexical`) is retained as
a deprecated diagnostic.

## Release gates

Per [ADR 0001](adr/0001-power-3.1-trust-release-baseline.md):

- **P0 — `ruff check src tests`**: All checks passed
- **P0 — `mypy src/power_framework`**: Success, 0 errors (33 source files)
- **P0 — `pytest`**: 532 passed, 2 skipped, ~72% coverage
- **P0 — `power lint brain`**: exit 0 (clean)
- **P1 — quality gate**: run the curated bilingual GT on the target vault with
  the pinned models and archive raw output. This has not been run for 3.2.0.
- **P1 — memory gate**: measure peak RSS with the pinned models on target
  hardware. The ≤12 GB contract is not confirmed until this artifact exists.

Run the release evaluation:

```bash
cd /root/geminicli/projects/P.O.W.E.R

# Full test suite (≥70% coverage, no bench)
pytest -q --no-cov

# Semantic quality gate (requires brain vault + models)
python scripts/check_search_quality.py --vault /root/gemini/brain --gt-mode semantic

# Verify vault health
power lint brain

# Lint + typecheck
ruff check src tests
mypy src/power_framework
```
