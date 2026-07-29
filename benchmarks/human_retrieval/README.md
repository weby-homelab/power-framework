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

The corpus owner must create `dataset/v1/manifest.json` from
`manifest.template.json`, retain raw annotations outside the development
working copy, and publish only de-identified, review-approved material.
`scripts/validate_human_evidence.py` validates the manifest contract. It
refuses to validate the sealed holdout unless `--allow-sealed` is explicitly
supplied.

No human qrels, metrics, thresholds, or release-quality claim are present yet.
Until independent annotators complete the protocol, M2 remains **in progress**.
