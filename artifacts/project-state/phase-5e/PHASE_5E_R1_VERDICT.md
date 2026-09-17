# POWER 3.8 — Phase 5E / P38-WP03-R1 Verdict (FAILED VERIFICATION)

```text
P38-WP03-R1: OPEN / FAILED VERIFICATION (RUNTIME DEFECT, NO RUNTIME FIX IN R1)
PHASE_5E: OPEN / FAILED VERIFICATION
PHASE_5F: BLOCKED
POWER_3_8_0: NO-GO
HOLDOUT_PREVIOUSLY_EXPOSED = TRUE
RUNTIME_TUNING_AFTER_HOLDOUT = FALSE
```

## 1. Corrected development result (20 queries, v1.1)

- Recall@5 1.0 (>=0.70 PASS), MRR 0.585 (>=0.50 PASS), nDCG@10 0.8077 (>=0.60 PASS).
- Context Precision 0.0850 (frozen formula hits/K, K=10).
- Exclusion leaks 5 (not PASS; classified below).
- `authority outranked by relevance = 9` (FAIL).
- `authority provenance failures = 9` (FAIL, all winners `unverified`, no `CANONICAL_LEDGER`).
- `winner_missing = 0`, `scope_escape = 0` (measured), `query_side_writes = 0`,
  `default_switches = 0` (measured), `determinism = 0`, latency/token/byte PASS.
- Regression case: `decision-old` rank 1 outranks `decision-current` rank 3 (p38-dev-q03) — FAIL.

## 2. Holdout reconciliation (20 queries, v1.1, previously exposed)

- Not a new sealed unseen holdout. Re-evaluated only because R1 changed harness,
  not runtime (`src/` diff empty).
- Same pattern: outranked 9, provenance failures 9, leaks 5, scope/writes/default/determinism PASS.
- Cannot serve as independent admission evidence for any runtime tuning.
  A future fresh evaluation epoch is required outside this correction.

## 3. Authority-sensitive cases (9/9 FAIL provenance)

- All 9 expected winners present but `unverified` without canonical basis.
- Examples: q02 project-current rank2 behind raw-chat; q03 decision-current rank3
  behind decision-old; q06 infra-current rank2 behind infra-stale; q11 project-current
  rank2 behind hard-negative; q13 project-current rank3 behind superseded;
  q16 research-curated rank2 behind research-unverified.

## 4. Remaining exclusion leaks (5, all FAIL per contract)

- q03 `decision-old` (verified SUPERSEDED stale) above `decision-current` — superseded — FAIL.
- q06 `infra-stale` (curated ARCHIVED stale) above `infra-current` — stale — FAIL.
- q11 `hard-negative` (curated current) above `project-current` — hard-negative — FAIL.
- q13 `project-superseded` (verified SUPERSEDED stale) above `project-current` — superseded — FAIL.
- q16 `research-unverified` (unverified PROPOSED) above `research-curated` — other/unverified — FAIL.
- Binding Gate 5E requires `authority outranked by relevance = 0`; 5 leaks cannot be called PASS.
  Any authority-sensitive expected exclusion above winner is FAIL.

## 5. Next gate

```text
PHASE_5E: OPEN / FAILED VERIFICATION
PHASE_5F (Incremental Dense Validity / dirty-set behavior): BLOCKED
POWER_3_8_0: NO-GO
NEXT: separate development-only runtime correction (not holdout-tuned), then fresh epoch.
LIVE_MAIN_REVALIDATION_REQUIRED: YES (snapshot-base is pre-merge where recorded)
```
