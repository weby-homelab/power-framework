# M2 independent human-annotation handoff

The generated `annotation-packets/annotator-a-*.jsonl` and
`annotation-packets/annotator-b-*.jsonl` contain the same pooled candidates
but no retrieval-mode labels, source locations, hostnames, personal data, or
sealed qrels. Give exactly one packet to each independent annotator.

Store completed responses **outside the framework working copy**, for example
in a restricted evidence store. Each response must contain the opaque
`query_id`, `document_id`, ordinal relevance (`-1`, `0`, `1`, `2`), correct
abstention, acceptable citation IDs and temporal classification. Do not modify
the corpus or queries after annotation begins.

Before reconciliation, calculate and retain an agreement receipt. Send every
disagreement to a third person, who records `scope`, `temporal`, `provenance`,
`partial`, `conflict`, or `other`; final qrels retain both original judgments.
Only then may a fresh adjudicated manifest include `status: adjudicated`, the
two-annotator count, agreement receipt and the pre-registered thresholds.

No generated pending file is a human judgment, qrel, adjudication or release
claim.
