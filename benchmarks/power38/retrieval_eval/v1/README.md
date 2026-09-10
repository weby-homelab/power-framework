# POWER 3.8 Retrieval Evaluation Corpus v1

This is a small, repository-owned, synthetic fixture for Phase 5A contract and
integrity verification. It is not a retrieval-quality result and it contains no
private vault, chat history, production log, credential, or model output.

## Contents

- `corpus/` — 20 human-reviewable synthetic POWER/OKF-compatible Markdown
  sources. The same read-only source corpus is available to both splits.
- `source_metadata.jsonl` — sidecar semantic/trust/authority/temporal/noise
  metadata; it is benchmark truth, not current production state.
- `queries.development.jsonl` — 20 development queries.
- `queries.holdout.jsonl` — 20 content-sealed holdout queries.
- `ground_truth.jsonl` — deterministic synthetic graded evidence and bounded
  authority/disposition expectations for every query.
- `manifest.json` — runtime `power.retrieval-eval.v1` manifest.
- `disjointness-proof.json` — machine-readable exact split proof without raw
  query text.
- `holdout-access-receipt.json` — bounded integrity-read receipt with no raw
  query or corpus content.

## Coverage

Each split contains `UA`, `EN`, and `MIXED_UA_EN` queries. Across the corpus the
semantic categories are:

`EXACT_LOOKUP`, `PROJECT_STATE`, `DECISION`, `TASK`, `CODE`,
`INFRASTRUCTURE`, `RESEARCH`, `CROSS_DOMAIN`, `HISTORICAL_STALE`,
`SUPERSEDED`, `CONTRADICTION`, `NOISE`, `PROMPT_INJECTION`, `HARD_NEGATIVE`,
and `AUTHORITY_CONFLICT`.

Both splits independently include the high-risk categories: project state,
decision, task, supersession, contradiction, prompt injection, hard negative,
and authority conflict.

The fixtures include canonical-vs-raw authority conflicts, superseded records,
contradictory records, inert prompt-injection text, and lexical hard negatives.
Prompt-injection text is data only; the verifier does not execute Markdown,
subprocesses, models, or network requests.

## Digest contract

All canonical logical digests use compact UTF-8 JSON with sorted object keys,
stable enum values, UTC-aware datetime normalization, omitted optional `None`
fields, and SHA-256. JSONL order is normalized by stable IDs before logical
digests are computed. Exact artifact bytes remain separately checked by the
verifier.

`dataset_digest` covers:

1. sorted source identities;
2. each corpus file's relative identity, byte size, and SHA-256 of its exact
   bytes;
3. canonical source sidecar metadata; and
4. canonical ground-truth records.

`query_set_digest` covers canonical development and holdout query records,
sorted by `query_id`. `development_split.digest` and `holdout_split.digest`
cover the corresponding sorted query records plus their ground-truth records.
`disjointness_proof_digest` covers the canonical proof object itself.

## Holdout policy

The holdout is **content-sealed, not confidential**. The files are visible in a
public repository; sealing means immutable/content-addressed/governed after
admission, not cryptographic secrecy.

- Integrity verification may read holdout metadata and records and must emit a
  bounded `holdout-access-receipt.json`-shaped receipt.
- Tuning tooling must load only development queries. The official helper
  rejects a holdout tuning request before loading it.
- `no_tuning_on_holdout=true`, `real_vault_ingestion=false`, and shared source
  corpus mode are explicit manifest invariants.
- The verifier proves disjoint query IDs, scenario families, and normalized
  exact query text. Shared source document IDs are allowed and expected.

## Verification

From the repository root:

```bash
uv run --offline python scripts/verify_retrieval_eval.py \
  benchmarks/power38/retrieval_eval/v1
```

Valid fixtures exit `0`. Digest mismatch, schema mismatch, missing source,
split overlap, unsafe reference, unknown category, malformed JSON, or a
holdout tuning request exits non-zero with a bounded error code.

This corpus is an integrity substrate for later Phase 5B–5E work. Phase 5A
does not claim Recall@K, MRR, nDCG, planner quality, router quality, dense
performance, or any other retrieval-quality improvement.
