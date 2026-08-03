# M2 annotation and adjudication protocol

The frozen v1 contract is preserved. The next annotation/evaluation run uses
the additive [protocol v2](annotation_protocol_v2.md), which moves abstention
to query level and adds field-wise agreement, confidence intervals, and a
calibration gate.

## Scope and privacy

Each corpus item must be de-identified before annotation. Do not include
credentials, personal data, private URLs, hostnames, or note content classified
as `sensitive`. Annotators receive a stable document identifier, the question,
and the candidate documents; they must not receive a retrieval-mode label.

## Splits and blinding

- **Development**: used to improve or configure a mode.
- **Sealed holdout**: its queries, judgments, and per-query results are not
  available to implementers until the release candidate is frozen.
- An item belongs to exactly one split. A document family or paraphrase must
  not cross the split boundary.
- A run may score the sealed split only with an explicit release-review action
  (`--allow-sealed`) and must emit a fresh manifest with hashes.
- Use a pooled candidate set from every compared mode, plus random negatives;
  never grade only a system's own top-ranked documents.

## Judgments

Two independent human annotators judge each `(query, document)` pair without
seeing each other's assessment. Relevance is ordinal:

- `2`: directly supports a correct answer;
- `1`: useful but incomplete context;
- `0`: does not support the answer;
- `-1`: misleading, stale for the requested time, or contradicts the evidence.

For every query, annotators also record:

- whether abstention is correct;
- which document IDs are acceptable citations;
- whether a cited fact is current, historical, or conflicted;
- the journey and question-taxonomy class.

## Adjudication

Compute agreement before reconciliation. Disagreements, including abstention
and temporal status, go to a third adjudicator who records a reason code:
`scope`, `temporal`, `provenance`, `partial`, `conflict`, or `other`.
The final qrel keeps both original judgments and the adjudicated decision;
adjudication never overwrites raw judgments.

## Reproducibility and reporting

Bind every result to exact corpus, queries, raw judgments and adjudicated qrels
SHA-256 values. Keep raw judgments and the agreement receipt, including the
chosen agreement statistic, with the final qrels. The corpus and qrels must be
evaluated together; do not reuse judgments after a content or de-identification
change. Report per-query results, confidence intervals and a paired comparison,
not only an aggregate winner.

These rules follow established TREC practice: human judgments are tied to the
specific document collection and qrels, graded relevance is valid for ranking,
and independent assessments surface disagreements for adjudication. See the
[TREC relevance-judgment guidance](https://trec.nist.gov/data/reljudge_eng.html),
[TREC Legal Track dual assessment](https://trec.nist.gov/pubs/trec19/papers/LEGAL10.OVERVIEW.pdf),
and [TREC 2024 RAG citation assessment](https://trec.nist.gov/data/rag2024.html).

## Pre-registered M2 gate

Before evaluating the sealed holdout, record thresholds for Recall@K, nDCG@K,
MRR, citation/provenance accuracy, stale-answer rate, abstention quality, and
latency. Report confidence intervals and every failed threshold. Compare
lexical, semantic, hybrid, reranked, and graph-assisted modes under the same
corpus hash and runtime manifest. Synthetic `power31` results remain CI-only.
