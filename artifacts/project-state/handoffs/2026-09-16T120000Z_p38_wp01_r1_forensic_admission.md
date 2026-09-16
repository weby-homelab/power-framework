# POWER 3.8 — P38-WP01-R1 Forensic Admission Handoff (PR-R1A)

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T12:00:00Z
GATE: P38-WP01-R1 Phase 5C SearchScope Closure Correction (PR-R1A admission)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-wp01-r1-phase5c-correction-admission
BASE_SHA: 319e6101e6c96f04d532de67a6f9e8f2aee4fa73
BASE_TREE: 1768fb1662dc968611b1e8ab7cbd31d2c5997747
STATUS: IN PROGRESS / FORENSIC ADMISSION
```

## 1. Executive summary

Phase 5C closure is under correction. PR #434 runtime is suspected to leave
scope-enforcement gaps (algebra OR-widening, graph post-filtering, fallback
source-type reads). PR-R1A admits the errata, blocks Phase 5D, and authorizes
only a bounded runtime correction in PR-R1B. No Phase 5D code in this gate.

```text
Phase 5C: CLOSURE CORRECTION ADMITTED
P38-WP01-R1: IN PROGRESS
Phase 5D / P38-WP02: BLOCKED BY P38-WP01-R1
POWER 3.8.0: NO-GO
```

## 2. Live verification (re-fetched, not copied)

- Live main `319e6101e6c96f04d532de67a6f9e8f2aee4fa73`, tree
  `1768fb1662dc968611b1e8ab7cbd31d2c5997747`, parents `294b483…` and `708b367…`.
- PR #433 merge `6c247c7…`, PR #434 candidate `a643e25…` and merge `294b483…`,
  PR #435 candidate `708b367…` and merge `319e6101…`.
- Narrative `319e610d…` does not exist as a Git object.
- Branch protection requires 11 contexts (no CodeRabbit). PR-head runs show 11
  required SUCCESS plus `deploy` SKIPPED. Historical `12/12 including CodeRabbit`
  is incorrect.
- Canonical baseline JSON uses 20/30/30/20/30 counters; narratives using 50 are
  resolved against the JSON. Post-fix JSON has no `out_of_scope_graph_hops`.
- Public stable `v3.7.13`; POWER 3.8.0 NO-GO.

## 3. Changed artifacts (docs/governance only)

- `docs/plans/POWER_3.8_CURRENT_STATE.md`: R1 status, live snapshot `319e610`,
  PR #435 tuple and SHA typo erratum, Phase 5D blocked, stale unstarted line fixed.
- `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`: R1 table/status, historical-note
  fixes for stale unstarted lines, Phase 5D blocked.
- `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`: R1 gate block, Phase 5D blocked.
- `docs/plans/README.md`: R1 status, Phase 5D blocked.
- `artifacts/project-state/phase-5c/PHASE_5C_R1_ADMISSION.md`: this admission.
- This handoff: append-only, no history rewrite.

## 4. Next authorized work

PR-R1B (`fix/p38-wp01-r1-searchscope-closure`, base = exact protected main
after PR-R1A) must reproduce R1/R2/R3 with failing tests first, implement the
minimum correction (search_scope, searcher, relations only if required,
projection helper only if strictly required), add machine evidence
`phase5c_r1_verification.json`, and pass full validation plus two independent
reviews before protected merge. PR-R1C reconciles closure docs only.
