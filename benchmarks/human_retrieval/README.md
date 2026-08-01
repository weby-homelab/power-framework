# POWER M2 Human Retrieval Evidence

This directory is the evidence contract for M2. It is deliberately separate
from `benchmarks/power31`: the latter is a synthetic CI regression benchmark
and cannot be used as human-quality or production evidence.

M2 evaluates five real knowledge-worker journeys:

1. locate a current operational fact;
2. recover an historical or superseded fact as of a stated date;
3. trace a claim to its cited source and provenance;
4. decide that a question has no supported answer and abstain; and
5. retrieve a cross-note relationship without treating candidates as authority.

For a frozen v1 audit, use `manifest.template.json`. Every new run uses
`manifest.v2.template.json` and the additive `annotation_protocol_v2.md`.
Schema v2 is invalid until a blinded calibration packet passes and its
de-identified agreement receipt is bound by SHA-256. Retain raw annotations
outside the development working copy and publish only de-identified,
review-approved material.

`scripts/compute_agreement.py` produces field-wise agreement without copying
participant identities or labels. `scripts/validate_human_evidence.py` checks
artifact hashes, query-level consistency, and joint metric feasibility. It
refuses the sealed holdout unless `--allow-sealed` is explicit. Private human
qrels and result receipts are intentionally absent from this repository;
their existence elsewhere is not, by itself, an M2 pass or release claim.
