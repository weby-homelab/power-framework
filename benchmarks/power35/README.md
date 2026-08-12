# POWER 3.5 Phase 8 technical outcome benchmark

`scripts/run_outcome_benchmark.py` runs 20 deterministic temporary-vault
workflows across static state, dynamic state, workflow knowledge, environment
gotchas, and blocked human decisions. It compares the shared application service with a declared
no-POWER baseline consisting of repository-only text scanning and an
unstructured handoff. The corpus has English/Ukrainian strata and five
false-premise cases plus one historical/current supersession case; POWER must
abstain without unsafe action and filter stale state. Both `fts` and `auto` are
exercised, and `auto` must expose its FTS fallback.

The report is content-free: it contains workflow identifiers, relative source
paths, hashes, and aggregate metrics, never fixture text or queries. In
addition to completion/continuity/safety, it records median latency, peak RSS,
disk footprint, evidence recall/use, and whether the blocked workflow reached
an explicit abstention state. Resource values are runner observations, not
frozen performance claims. Blind scoring, tokenization, false-premise scoring,
feedback reuse, human-quality certification, real-vault evidence,
LongMemEval/StreamMemBench scoring, and a production-quality claim remain
outside this synthetic runner.

```bash
python benchmarks/power35/scripts/run_outcome_benchmark.py \
  --output /tmp/power35-outcome.json
```

The release gate remains closed until real-vault/sealed-dataset and blind
human outcome evidence are independently available.

`scripts/run_continuity_benchmark.py` is the separate Phase 8.2 technical
receipt. It runs 20 code, ops, research, note-mutation, and blocked-decision
handoffs through 60 independent worker processes, compares durable resume with
a plain handoff, and checks resume/replay idempotency, proof-carrying source
revision, blocked human decisions, and source preservation. It is still synthetic and does not certify
human quality or real-vault outcomes.
