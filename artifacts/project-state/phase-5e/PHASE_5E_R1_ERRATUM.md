# POWER 3.8 — Phase 5E / P38-WP03-R1 Erratum (Benchmark Closure Correction)

```text
CORRECTION_ID: P38-WP03-R1
START_MAIN_SHA: df41cc9f6d5b007995972bf4274beccb9e008732
START_MAIN_TREE: 2e69d9439608946a9984033953b79fcc24bb6b63
PHASE_5E: CLOSURE CORRECTION REQUIRED
PHASE_5F: BLOCKED
POWER_3_8_0: NO-GO
```

## 1. Live forensic admission (fresh GitHub readback)

- `main` SHA `df41cc9f6d5b007995972bf4274beccb9e008732`, tree `2e69d9439608946a9984033953b79fcc24bb6b63`.
- PR #445 final head `746be1b7d40d62f3da3440573f6ca18754277de8`, merge `b651eb94ff0074472004c83f343342a279935fdd`
  with parents `5bcec9cc2c0db27e142f8c5c7c30bdcfa57137d2` and `746be1b7d40d62f3da3440573f6ca18754277de8`.
- PR #447 head `13d253742674aafb7ab8b91cd2e7b50d7b973850`, merge `df41cc9f6d5b007995972bf4274beccb9e008732` (MERGED).
- Live branch protection: 11 required contexts
  (`test (3.13)`, `test (3.14)`, `security`, `package-smoke`, `upgrade-matrix (ubuntu-latest)`,
  `upgrade-matrix-aggregate`, `base-runtime-smoke`, `benchmark-integrity`, `analyze (python)`,
  `CodeQL`, `build`), `strict: true`, `enforce_admins: true`. Not 12.
- Binding source for Phase 5F canonical name:
  `artifacts/project-state/planning/phase5-9-acceptance-gates.md`, Gate 5F:
  `Incremental Dense Validity and dirty-set behavior`.

## 2. Governance errata fixed in R1

- `PHASE_5E_REPORT.md` left PR #447 `PENDING`; live truth is MERGED (`df41cc9f`).
- Current-state snapshot after #447 is stale: `SNAPSHOT_BASE_SHA 6eebd43b6e55b10fd414e86ba98b2620f108157f`,
  `CURRENT_LIVE_MAIN 6eebd43b...` with `LIVE_MAIN_REVALIDATION_REQUIRED: NO` while live main is `df41cc9f`.
  Self-reference fixed in R1 verdict: pre-merge base may be recorded, but then
  `LIVE_MAIN_REVALIDATION_REQUIRED: YES`.
- Phase 5F canonical name corrected from `Context Memory / Stateful Multi-Turn Context`
  to `Incremental Dense Validity / dirty-set behavior` per binding acceptance contract.

## 3. Benchmark harness defects reproduced (EVIDENCE > REPORT)

- `compute_context_precision` divided by `len(returned)` instead of frozen `hits / K` (K=10).
- Authority metric was not ground-truth-aware: ignored `expected_authority_winner`,
  passed vacuously when all items were `authority=unverified`.
- No canonical fixture projection: synthetic `project state / Task / Decision` fixtures
  were never checked against real runtime owners (`ProjectStateService`, `TaskService/Store`,
  `DecisionService`); `UNVERIFIED != CANONICAL`.
- `scope_escape` was never measured (`total_scope_escapes` never incremented).
- `default_switches = 0` was hard-coded, never measured.

## 4. R1 correction scope (harness only, no runtime)

- `scripts/benchmark_phase5e_shadow.py`: frozen `hits/K`, frozen fixture-owner map
  (query-independent, ground-truth-independent, no promotion), ground-truth-aware
  winner presence/rank/exclusions-above/provenance check, real vault containment,
  measured served/default boundary, `HOLDOUT_PREVIOUSLY_EXPOSED=TRUE`,
  `RUNTIME_TUNING_AFTER_HOLDOUT=FALSE`.
- `tests/test_benchmark_phase5e_r1_correction.py`: 6 regression tests (all PASS).
- Machine evidence: `phase5e_development_r1_corrected.json`,
  `phase5e_holdout_r1_reconciliation.json`.
- Runtime diff: `git diff --name-only -- src/` is empty. No `RetrievalPlanner` /
  `ContextPack` / ranking change after the previous holdout.

## 5. Invariants

```text
EVIDENCE > REPORT
GROUND TRUTH SCORES OUTPUT; GROUND TRUTH DOES NOT DRIVE OUTPUT
CANONICAL AUTHORITY MUST COME FROM REAL RUNTIME PROVENANCE
UNVERIFIED != CANONICAL
A ZERO COUNTER THAT WAS NEVER MEASURED IS NOT EVIDENCE
HARD-CODED PASS IS NOT VERIFICATION
AUTHORITY OUTRANKED BY RELEVANCE = FAIL
NO HOLDOUT-DRIVEN RUNTIME TUNING
PHASE 5F BLOCKED UNTIL R1 CLOSES
POWER 3.8.0 = NO-GO
```
