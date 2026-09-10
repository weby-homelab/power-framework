# POWER 3.8 Retrieval Evaluation Corpus v1.1

This is the corrected, immutable semantic revision of the Phase 5A synthetic
evaluation corpus. It keeps the `power.retrieval-eval.v1` schema and supersedes
`v1/` for future Phase 5B–5E evaluation. The original `v1/` directory remains
available as historical admitted evidence; its bytes and digests are unchanged.

## Contents

- `corpus/` — the same 20 byte-identical synthetic Markdown sources as v1.
- `source_metadata.jsonl` — source identity, metadata, lifecycle, and digest.
- `queries.development.jsonl` — 20 development queries.
- `queries.holdout.jsonl` — 20 corrected content-sealed holdout queries.
- `ground_truth.development.jsonl` and `ground_truth.holdout.jsonl` — graded
  evidence, with the q19 infrastructure target corrected.
- `semantic-adjudication.json` — bounded machine-readable adjudication receipt
  for all 40 queries.
- `semantic-review-a-v1.1.json` and `semantic-review-b-v1.1.json` — bounded
  receipts for the two independent pre-adjudication review inputs.
- `disjointness-proof.json` — exact split proof without raw query text.
- `holdout-access-receipt.json` — bounded integrity-read receipt.
- `manifest.json` — explicit `v1.1` identity and active-revision digests.

## Semantic corrections

The holdout wording for `p38-ho-q06`, `p38-ho-q11`, and `p38-ho-q16` now asks
for the current, real project, and curated winners respectively. Their
authoritative ground-truth rows are retained; the accidental diagnostic
inversion was in the query wording.

Both q19 ground-truth rows now identify `p38-src-infra-current`, because that
fixture directly states the host-neutral resource-profile and deployment-only
host-facts rule. The prior cross-domain label was not entailed by either q19
wording.

`p38-*-q20` now names the verified cross-domain admission-package projection;
the declared `cross_domain` intent, task/project categories, source metadata,
and ground-truth reason remain bound to that answer. Quarantine queries use
`not_applicable` temporal expectation because they ask about handling, not source
time; the source metadata `temporal_state: unknown` is preserved.

## Adjudication boundary

Two independent read-only semantic reviews were compared and adjudicated from
the primary query, source, metadata, scenario-family, and ground-truth files.
No router, retrieval score, embedding, model, threshold, or metric influenced
the decision. Structural digest verification is necessary but cannot prove
natural-language entailment; semantic adjudication is a separate acceptance
evidence layer.

## Digest contract

`source_corpus_digest` is unchanged from v1 because all 20 source bytes and
source metadata are unchanged. The v1.1 `dataset_digest` covers sorted source
identities, canonical source metadata, canonical ground truth, the complete
`semantic-adjudication.json` object, and the exact SHA-256 of the Markdown
rationale. Each v1.1 ground-truth `provenance_digest` uses the canonical payload
`{revision, ground_truth-without-provenance_digest}`. The query-set, split, proof,
semantic, rationale, and source digests are independently bound in `manifest.json`.

All logical digests use compact UTF-8 JSON, sorted object keys, stable values,
and SHA-256. JSONL order is normalized by stable IDs. Source fixtures and
content-addressed adjudication/receipt evidence are checked as raw bounded
bytes; query and ground-truth JSONL are checked through their canonical logical
digests.

## Holdout policy

The holdout is content-sealed, not confidential. Integrity verification may
read it and records bounded access metadata; tuning tooling loads development
records only. `no_tuning_on_holdout=true`, `real_vault_ingestion=false`, and
shared read-only source-corpus mode remain explicit invariants.

## Verification

From the repository root:

```bash
uv run --offline python scripts/verify_retrieval_eval.py \
  benchmarks/power38/retrieval_eval/v1 \
  --expected-revision v1

uv run --offline python scripts/verify_retrieval_eval.py \
  benchmarks/power38/retrieval_eval/v1.1 \
  --expected-revision v1.1
```

The command is offline, model-free, network-free, and fails closed. It reports
the historical v1 as structurally valid but superseded, and v1.1 as the active
revision with semantic adjudication `PASS`.

This corpus is an integrity and semantic-adjudication substrate for later
Phase 5B–5E work. It does not publish Recall@K, MRR, MAP, nDCG, router quality,
dense performance, or any other retrieval-quality result.
