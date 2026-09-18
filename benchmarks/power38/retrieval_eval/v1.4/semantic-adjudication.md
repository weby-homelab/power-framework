# Semantic adjudication — retrieval evaluation v1.4

This is the human-readable companion to `semantic-adjudication.json`. It is
content-addressed by the active manifest's `semantic_adjudication_digest` and
is included in the active `dataset_digest` through that JSON artifact.

## Method and decision rules

- Reviewer A and Reviewer B independently read the 40 queries, 40 ground-truth
  records, all 20 source bodies, source metadata, scenario families, and the
  Phase 5 planning contracts. They did not see each other's verdicts.
- Their bounded input receipts are `semantic-review-a-v1.4.json` and `semantic-review-b-v1.4.json`.
- The orchestrator compared both reports with the primary fixtures.
- No search result, score, embedding, model, router, threshold, or retrieval
  metric was used. The adjudication happened before one-shot holdout execution.
- Quarantine cases have `temporal_expectation: not_applicable` because they ask
  about handling/disposition, not source time.
- Authority ordering does not erase query intent.

## Rationale reference map

- `adjudication-v14-r01`: p38-dev-q01 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r02`: p38-dev-q02 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r03`: p38-dev-q03 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r04`: p38-dev-q04 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r05`: p38-dev-q05 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r06`: p38-dev-q06 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r07`: p38-dev-q07 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r08`: p38-dev-q08 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r09`: p38-dev-q09 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r10`: p38-dev-q10 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r11`: p38-dev-q11 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r12`: p38-dev-q12 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r13`: p38-dev-q13 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r14`: p38-dev-q14 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r15`: p38-dev-q15 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r16`: p38-dev-q16 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r17`: p38-dev-q17 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r18`: p38-dev-q18 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r19`: p38-dev-q19 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r20`: p38-dev-q20 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r21`: p38-ho-q01 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r22`: p38-ho-q02 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r23`: p38-ho-q03 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r24`: p38-ho-q04 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r25`: p38-ho-q05 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r26`: p38-ho-q06 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r27`: p38-ho-q07 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r28`: p38-ho-q08 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r29`: p38-ho-q09 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r30`: p38-ho-q10 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r31`: p38-ho-q11 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r32`: p38-ho-q12 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r33`: p38-ho-q13 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r34`: p38-ho-q14 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r35`: p38-ho-q15 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r36`: p38-ho-q16 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r37`: p38-ho-q17 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r38`: p38-ho-q18 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r39`: p38-ho-q19 reviewed and adjudicated with verdict PASS.
- `adjudication-v14-r40`: p38-ho-q20 reviewed and adjudicated with verdict PASS.
