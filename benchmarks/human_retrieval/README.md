# POWER M2 Human Retrieval Evidence

> **M2-v1 відкликано.** Попередній англомовний і суперечливий packet є лише
> audit-only історією. Для нових учасників використовується тільки
> україномовний M2-v2 після реальної calibration.

This directory is the evidence contract for M2. It is deliberately separate
from `benchmarks/power31`: the latter is a synthetic CI regression benchmark
and cannot be used as human-quality or production evidence.

M2 evaluates five real knowledge-worker journeys:

1. locate a current operational fact;
2. recover an historical or superseded fact as of a stated date;
3. trace a claim to its cited source and provenance;
4. decide that a question has no supported answer and abstain; and
5. retrieve a cross-note relationship without treating candidates as authority.

For a frozen v1 audit, use `manifest.template.json`; it must never be promoted
to a quality gate. Every new run uses `manifest.v2.template.json`,
`annotation_protocol_v2.md` and the short Ukrainian handoff in
`ANNOTATOR_INSTRUCTIONS_UK.md`; the third person uses
`ADJUDICATOR_INSTRUCTIONS_UK.md`. Schema v2 starts as `pending_calibration` and
cannot become annotation-ready until a blinded calibration packet passes and
its de-identified agreement receipt is bound by SHA-256. Retain raw annotations
outside the development working copy and publish only de-identified,
review-approved material.

`scripts/validate_annotation_packet.py` checks the human-facing packet before
delivery: Ukrainian text, exactly four candidates, no hidden journey or
answerability fields, no sensitive data and no malformed response contract.
`scripts/compute_agreement.py` produces field-wise agreement without copying
participant identities or labels. `scripts/validate_human_evidence.py` checks
artifact hashes, agreement-receipt path/SHA bindings and joint metric
feasibility. It refuses the sealed holdout
unless `--allow-sealed` is explicit. Private human qrels and result receipts
are intentionally absent from this repository; their existence elsewhere is
not, by itself, an M2 pass or release claim.

The retrieval evaluator gates only the five preregistered comparators:
`lexical`, `semantic`, `hybrid`, `reranked` and `graph_assisted`. The optional
`vector` mode remains in every receipt as a diagnostic, but its threshold
failures cannot silently block or open the M2 gate. Omitting a preregistered
mode is fail-closed as `unavailable`.

## M2-v2.1 after the independent architecture test

The current v2 receipt remains an honest **FAIL** because its preregistered
lexical recall is `0.75` against `0.80`; that result is not changed by this
document. The independent test showed that lexical FTS cannot be treated as a
semantic synonym engine, so a new human run must use the separate
`m2-v2.1-preregistration.json` policy. It keeps lexical and vector as visible
diagnostics, gates semantic/hybrid/reranked/graph-assisted, and freezes a pool
from every comparator plus random negatives before any new judgment.

The policy is not issued to participants while its status is
`pending_curator_approval`. Validate it before creating any packet:

```bash
python3 benchmarks/human_retrieval/scripts/validate_preregistration.py \
  benchmarks/human_retrieval/m2-v2.1-preregistration.json
```

No qrel-specific synonym, fuzzy threshold, tokenizer change or frozen-qrel
rewrite is permitted. A new Ukrainian query set, fresh calibration and a
hash-bound de-identified receipt are required before production access.

After curator approval changes the policy status to
`pre_registered_before_human_calibration`, freeze the candidate pool from the
same receipt before producing any human packet:

```bash
python3 benchmarks/human_retrieval/scripts/build_candidate_pool.py \
  --policy m2-v2.1-preregistration.json \
  --corpus development/corpus.jsonl \
  --queries development/queries.jsonl \
  --receipt development/evaluation-v2.1.json \
  --output development/candidate-pool.v1.json
```

The builder binds policy, corpus, queries and receipt SHA-256 values, requires
every gated and diagnostic comparator to be completed, takes the preregistered
top-k per comparator and deterministic random negatives, and writes the pool
with mode `0600`. A pending policy, sealed document, missing comparator or
unknown document ID fails closed.
