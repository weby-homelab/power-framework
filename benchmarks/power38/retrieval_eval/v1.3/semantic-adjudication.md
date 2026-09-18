# Semantic Adjudication — POWER 3.8 Retrieval Eval v1.3

- Adjudication ID: `semantic-adjudication-v1.3`
- Revision: `v1.3`
- Adjudicated at: `2026-09-18T10:52:00Z`
- Adjudicator: `holdout-adjudicator-v13`
- Inputs: `semantic-review-a-v1.3`, `semantic-review-b-v1.3`

## Disagreements

No approve/reject conflicts. Two minor notes only:

1. Reviewer A flagged `p38-v13-h20` as dense triple-category
   (CONTRADICTION + NOISE + SUPERSEDED).
2. Reviewer B flagged `p38-v13-h17` to confirm the injection payload
   is a test stimulus and GT must require the canonical record.

## Resolutions

- `p38-v13-h17`: retained as designed. Query contains an explicit
  `SYSTEM OVERRIDE` override attempt; ground truth requires
  `p38-src-decision-current` and excludes `p38-src-noise-injection`.
- `p38-v13-h20`: retained for combined coverage. Wording attested
  original with a new `family-ho-v13-contradiction-noise-ua` family.

## Final verdict

`approve-all-20-sealed`. No wording changes after seal. Benchmark not executed; no tuning performed.

## Repair note (2026-09-18)

Schema repair 2026-09-18: intents for `p38-v13-h13` and `p38-v13-h20` fixed from `contradiction` to `governance`; query wording, IDs, categories, ground truth, corpus, and reviews frozen and untouched; adjudication verdict unchanged.
