# Phase 5C R1 Erratum — Historical Claims vs Corrected Evidence

```text
EVIDENCE_TYPE: phase5c_r1_erratum
CREATED_AT_UTC: 2026-09-16T12:30:00Z
BASE_SHA: a0ee8eea36ede547ef4196f4e54f3c3465de044a
STATUS: APPEND-ONLY CORRECTION (do not rewrite historical files)
```

Historical files (`PHASE_5C_BASELINE.md`, `PHASE_5C_REPORT.md`, old handoffs,
old evidence JSON) remain unchanged. This erratum explains what was wrong,
why, and what R1 corrects.

## Erratum A — PR-C merge SHA narrative typo

- Old claim (narrative): `319e610d4806a6c0c00b5220c3848b3b429ef9eb`.
- Live truth: `319e6101e6c96f04d532de67a6f9e8f2aee4fa73` (tree
  `1768fb1662dc968611b1e8ab7cbd31d2c5997747`, parents `294b483…` and `708b367…`).
- Root cause: reporting typo in chat/narrative, not a Git object.
- Impact: none on runtime; gate accounting must use live objects.
- Correction: PR-R1A records live tuple; CURRENT_STATE cites typo explicitly.

## Erratum B — required-check accounting

- Old claim: `12/12 SUCCESS including CodeRabbit`.
- Live truth: branch protection requires 11 contexts (no CodeRabbit):
  `test (3.13)`, `test (3.14)`, `security`, `package-smoke`,
  `upgrade-matrix (ubuntu-latest)`, `upgrade-matrix-aggregate`,
  `base-runtime-smoke`, `benchmark-integrity`, `analyze (python)`, `CodeQL`,
  `build`. PR-head runs show 11 required SUCCESS plus optional `deploy`
  SKIPPED (12 check-runs total, not 12 required).
- Root cause: conflated `total check-runs` with `required checks`.
- Impact: gate status was overstated; protection was still satisfied (11/11).
- Correction: R1 evidence reports REQUIRED / OPTIONAL / SKIPPED separately;
  never writes `12/12 required` because 12 runs happened to exist.

## Erratum C — baseline counters narrative

- Canonical JSON (`phase5c_baseline_evidence.json`): FTS 20, TF 30, Dense 30,
  Reranker 20, Fallback 30.
- Later narrative used 50 for several counters.
- Root cause: narrative drift from machine-readable evidence.
- Correction: resolve against committed JSON; JSON not rewritten.

## Erratum D — graph-zero claim without instrumentation

- Old claim: `OUT_OF_SCOPE_GRAPH_HOPS = 0` (and similar graph-zero claims).
- Committed `phase5c_post_fix_evidence.json` contains no measurable
  `out_of_scope_graph_hops`, `graph_nodes_considered/visited`, or
  `out_of_scope_graph_nodes_read`.
- Root cause: inferred zero from final result paths, not from traversal
  instrumentation. `_graph_assisted_search` scanned the entire vault via
  `suggest_related_v2`, built a global graph, ran global `weighted_bfs`, then
  discarded OOS yields — OOS nodes were already read, queued, traversed as
  potential bridges, and materialized.
- Correction: R1 implements scope-before-build/traversal plus real
  instrumentation (`phase5c_r1_verification.json` graph section) and
  adversarial bridge tests. Do not claim graph-zero until executable evidence
  proves it.

## R1 corrected behavior

- Scope algebra: OR within dimension, AND across dimensions; monotonic
  narrowing; digest distinguishes domain vs explicit path dimensions.
- Graph: eligible set derived before read; suggestions over eligible only;
  explicit OOS links dropped; BFS over eligible-only graph; OOS bridge cannot
  connect two in-scope nodes; OOS reads/hops = 0 by measurement.
- Fallback: source-type pre-check via safe index metadata before `read_source`;
  unknown types fail closed; no directory-name inference; OOS reads = 0.
- FTS/TF/Dense/Reranker: scoped SQL selection measured (selected OOS = 0),
  not just final results; defense-in-depth post-filters retained but not
  counted as pushdown.
