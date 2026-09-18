# POWER 3.8 Retrieval Eval — v1.3 (Blind Holdout)

Holdout-only revision for Phase 5E. Corpus and development split are verbatim copies of v1.1; holdout is 20 fresh queries.

## Contents

- `corpus/` — verbatim copy of v1.1 corpus (20 synthetic sources, preserved).
- `source_metadata.jsonl` — verbatim copy of v1.1 (20 lines).
- `queries.development.jsonl` + `ground_truth.development.jsonl` — verbatim copies of v1.1 development (20 each, `tuning_allowed: true`).
- `queries.holdout.jsonl` — 20 fresh holdout queries `p38-v13-h01..h20` (`tuning_allowed: false`, never tune on holdout).
- `ground_truth.holdout.jsonl` — matching GT with `expected_relevant_source_ids`, `expected_exclusion_source_ids`, `expected_authority_winner` where applicable, `graded_relevance`, `temporal_expectation`.
- `manifest.json` — v1.3 manifest with sealed digests; `supersedes_revision: v1.2`, `split_relation: disjoint`.
- `disjointness-proof.json` — zero shared IDs/texts vs v1.1/v1.2 (programmatic boolean-only check).
- `semantic-review-a-v1.3.json`, `semantic-review-b-v1.3.json` — two independent reviewer records with per-query approval and wording-originality attestation.
- `semantic-adjudication.json` / `.md` — adjudication (notes only, approve-all sealed).
- `holdout-access-receipt.json` — sealed receipt: no access before execution, benchmark not run, no tuning.

## Blind authorship

Author never saw development results, ranking errors, or `retrieval_planner.py`. Allowed sources only: v1.2 manifest schema, v1.2 holdout format samples (first 3 query lines + first 2 GT lines), v1.1 corpus file list, v1.1 metadata first 5 lines, fixture concept IDs + scoring_aliases for GT mapping. Corpus/development copies performed with `cp -p` without reading full prior query texts; disjointness verified with overlap counts only.

## Digest method (v1.3, transparent)

- `source_corpus_digest`: preserved `3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118` (corpus verbatim).
- `development_split.digest`: `sha256(queries.development.jsonl)`.
- `holdout_split.digest`: `sha256(queries.holdout.jsonl)`.
- `query_set_digest`: `sha256(queries.holdout.jsonl + ground_truth.holdout.jsonl)`.
- `ground_truth provenance_digest`: `sha256(ground_truth.holdout.jsonl)`.
- `disjointness_proof_digest`, `holdout_access_receipt_digest`, `semantic_adjudication_digest`, `semantic_adjudication_markdown_digest`: `sha256` of the respective files.
- `dataset_digest`: `sha256(source_metadata.jsonl + queries.holdout.jsonl + ground_truth.holdout.jsonl + queries.development.jsonl + ground_truth.development.jsonl)`.

## Status

Sealed before execution. Do NOT run the benchmark here. Do NOT tune on holdout. No push, no commit.
