# M2 independent human-annotation handoff

The generated `annotation-packets/annotator-a-*.jsonl` and
`annotation-packets/annotator-b-*.jsonl` contain the same pooled candidates
but no retrieval-mode labels, source locations, hostnames, personal data, or
sealed qrels. Give exactly one packet to each independent annotator.

Store completed responses **outside the framework working copy**, for example
in a restricted evidence store. Each response contains the opaque `query_id`,
document-level relevance (`-1`, `0`, `1`, `2`), acceptable citation IDs and
temporal classification. Record `query_abstention_correct` and taxonomy once
per query. Do not modify the corpus or queries after annotation begins.

Before a new production packet, the same two annotators complete a blinded
calibration packet and `compute_agreement.py --protocol-version 2.0` must pass
the pre-registered gate. Before reconciliation, calculate and retain the
production agreement receipt. Send every disagreement to a third person, who
records `scope`, `temporal`, `provenance`, `partial`, `conflict`, or `other`;
final qrels retain both original judgments. Run `validate_human_evidence.py`
before retrieval. Only then may a fresh adjudicated manifest include
`status: adjudicated`, the two-annotator count, calibration and agreement
receipts, and the pre-registered thresholds.

No generated pending file is a human judgment, qrel, adjudication or release
claim.
