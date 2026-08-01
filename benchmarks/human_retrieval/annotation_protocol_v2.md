# M2 annotation and adjudication protocol v2

This protocol is a new pre-registration for the next development run. It does
not rewrite or reinterpret frozen v1 qrels, raw judgments, or receipts.

## Query-level abstention

Annotators record `query_abstention_correct` once per query, not once per
query-document form. Query taxonomy is also recorded once. Flattened
adjudicated qrels may repeat these values on each query-document row for tool
compatibility, but every repeated value must be identical. A v2 evaluator may
read frozen v1's per-document `abstention_correct` only as a compatibility
fallback; inconsistent values are an evidence-contract error.

## Cross-field validity

An `acceptable_citation` must have relevance of at least `1`. For an
answerable `current_fact` query, at least one candidate must simultaneously be
relevant, citation-acceptable, and `temporal_status=current`. This preflight
rule prevents citation accuracy and stale-answer rate from demanding mutually
exclusive top results. An abstention query has no acceptable citation and is
excluded from the citation-accuracy denominator.

## Agreement receipt

Before adjudication, the receipt reports independent agreement separately for
each field: ordinal relevance, query-level abstention, acceptable citation
set, temporal status, and taxonomy. It includes exact-match rate and sample
count for every field, plus an ordinal weighted Cohen's kappa for relevance.
All reported proportions include a deterministic 95% bootstrap confidence
interval over independent annotation units. Raw responses remain outside the
framework working copy.

Generate the de-identified receipt before adjudication:

```bash
python benchmarks/human_retrieval/scripts/compute_agreement.py \
  --input /restricted/raw-judgments.jsonl \
  --output /restricted/agreement-v2.json \
  --protocol-version 2.0
```

## Calibration rule

The two annotators must complete a blinded calibration packet before the next
production packet. The calibration packet is scored with the same field-wise
receipt, and disagreements are discussed without changing already-frozen v1
data. The new run may proceed only when the pre-registered calibration rule
passes: query-level abstention exact agreement is at least 0.80 and the lower
95% confidence bound for relevance weighted kappa is at least 0.60. If the
rule fails, recalibrate and issue a new v2 pre-registration receipt; do not
open the sealed holdout and do not alter v1.

## Evaluation boundary

The v2 development evaluation compares lexical, semantic, hybrid, reranked,
and graph-assisted retrieval under one corpus, query, qrel, runtime, and
framework commit binding. Every unavailable comparator or failed threshold
keeps the sealed holdout decision at `do_not_open`. Before retrieval, run
`validate_human_evidence.py`; inconsistent query-level labels or a joint
current/citation contradiction fail the manifest. Frozen v1 remains historical
evidence and cannot satisfy the v2 calibration gate.
