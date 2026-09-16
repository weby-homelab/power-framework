# Phase 5C (P38-WP01) Closure Correction Admission — P38-WP01-R1 (PR-R1A)

```text
EVIDENCE_TYPE: phase5c_r1_admission
CREATED_AT_UTC: 2026-09-16T12:00:00Z
BASE_SHA: 319e6101e6c96f04d532de67a6f9e8f2aee4fa73
BASE_TREE: 1768fb1662dc968611b1e8ab7cbd31d2c5997747
BASE_PARENTS: 294b48319fdcd3dd3bc030a940bda64f7583889f, 708b3677e97b91ef1748d62fce79c7b642b1419d
PUBLIC_STABLE: v3.7.13
POWER_3_8_0: NO-GO
STATUS: P38-WP01-R1 IN PROGRESS / FORENSIC ADMISSION
```

## 1. Gate status

```text
Phase 5C: CLOSURE CORRECTION ADMITTED (PR #434 superseded for closure)
P38-WP01-R1: IN PROGRESS (PR-R1A admission; PR-R1B runtime correction pending)
Phase 5D / P38-WP02: BLOCKED BY P38-WP01-R1 / NOT STARTED
POWER 3.8.0: NO-GO
```

Phase 5D runtime (`RetrievalPlanner`, `ContextPackCompiler`, Phase 5E shadow
evaluation, Phase 5F dirty-set work, new MCP ContextPack tools, capture, A2A,
AGE, pgvector, PostgreSQL, version bump, tag, release) is forbidden until
P38-WP01-R1 is protected-merged and post-merge verified.

This PR-R1A branch is docs/governance/errata only. No runtime changes.

## 2. Live starting state (independently re-fetched)

```text
LIVE MAIN: 319e6101e6c96f04d532de67a6f9e8f2aee4fa73
LIVE MAIN TREE: 1768fb1662dc968611b1e8ab7cbd31d2c5997747
LIVE MAIN PARENTS: 294b48319fdcd3dd3bc030a940bda64f7583889f, 708b3677e97b91ef1748d62fce79c7b642b1419d
PR-A #433 merge: 6c247c7e4c1788a8bd5388b1327170a8e7493852
PR-B #434 candidate: a643e25a5a761a892ef69b910fb82c66a8a29e99
PR-B #434 merge: 294b48319fdcd3dd3bc030a940bda64f7583889f
PR-C #435 candidate: 708b3677e97b91ef1748d62fce79c7b642b1419d
PR-C #435 merge: 319e6101e6c96f04d532de67a6f9e8f2aee4fa73
REQUIRED MAIN CONTEXTS: 11
PUBLIC STABLE: v3.7.13
```

Required contexts (live branch protection, 11):

```text
test (3.13), test (3.14), security, package-smoke,
upgrade-matrix (ubuntu-latest), upgrade-matrix-aggregate,
base-runtime-smoke, benchmark-integrity, analyze (python), CodeQL, build
```

PR head `708b367` check-runs: 12 total = 11 required SUCCESS + `deploy` SKIPPED.
`CodeRabbit` is not a required context. Historical `12/12 SUCCESS including
CodeRabbit` claims are incorrect; see erratum B.

## 3. Reporting errata admitted (verify, do not trust old narratives)

### Erratum A — PR-C merge SHA

Old narrative used `319e610d4806a6c0c00b5220c3848b3b429ef9eb`.
That object does not exist (`git cat-file -t` fails).
Live GitHub merge is `319e6101e6c96f04d532de67a6f9e8f2aee4fa73`.
Old chat history is not edited; this admission records the correction.

### Erratum B — required checks

Historical Phase 5C closure evidence claimed `12/12 SUCCESS including CodeRabbit`.
Live protection requires 11 contexts (enumerated above). `CodeRabbit` is not
required. PR-head runs show 11 required SUCCESS plus optional `deploy` SKIPPED.
`total check-runs == required checks` is false unless GitHub policy says so.
Future R1 evidence must report REQUIRED / OPTIONAL / INFORMATIONAL / SKIPPED /
EXTERNAL AUTOMATION separately.

### Erratum C — baseline counters

Canonical `phase5c_baseline_evidence.json` records:

```text
FTS OOS candidates: 20
TF OOS rows: 30
Dense OOS rows: 30
Reranker OOS docs: 20
Fallback OOS reads: 30
```

Later narratives using 50 for several counters are resolved against the
committed machine-readable JSON above. Historical JSON is not rewritten.

### Erratum D — graph metric

Committed `phase5c_post_fix_evidence.json` contains no measurable
`out_of_scope_graph_hops`. Do not claim `OUT_OF_SCOPE_GRAPH_HOPS = 0` until
executable instrumentation proves it in PR-R1B (`phase5c_r1_verification.json`).

## 4. Suspected runtime gaps admitted for PR-R1B reproduction

All three findings are suspected and must be reproduced against exact current
`main` before runtime correction. Executable behavior wins over old CLOSED claims.

- **R1 scope algebra:** `compile_search_scope()` flattens explicit
  `path_prefixes` and domain-derived prefixes into one OR list. Domain +
  narrower path may widen instead of intersecting. Least-privilege contract for
  R1B: OR within one dimension, AND across independent dimensions; monotonic
  narrowing `eligible(scope + restriction) ⊆ eligible(scope)`.

- **R2 graph scope:** `_graph_assisted_search → suggest_related_v2 → vault scan /
  WeightedKnowledgeGraph → weighted_bfs → scope check` enforces scope only after
  global scan, global suggestion construction, and global BFS traversal.
  Insufficient: OOS nodes may already have been read, queued, traversed as
  bridges, or materialized. R1B target: scope before graph materialization and
  traversal; OOS bridge must not connect two in-scope nodes; instrument
  `graph_nodes_considered/visited`, `out_of_scope_graph_nodes_read/hops`.

- **R3 source-type fallback:** `_scan_and_search` and `_scan_and_vector_search`
  use path-only pre-checks; note type is learned only after `read_source`.
  R1B target: source-type constrained fallback must not read excluded sources;
  reuse safe projection/metadata boundary or fail closed; never infer type from
  directory name.

`trust_states` / `project_ids` non-empty remain `UnsupportedSearchScopeError`
fail-closed. `include_archived=False` / `include_quarantine=False` defaults and
privileged-override gates are retained. No SearchScope v3 unless contract
evidence proves necessity. Public SearchScope v2 DTO is not broken.

## 5. Mutable documentation corrected in PR-R1A

Current mutable projections that still said Phase 5C is `ready for admission`
or `unstarted` despite PR #434 are corrected with historical-note
clarifications. Historical handoffs, baseline/report markdown, and old evidence
JSON are append-only and are not rewritten. Corrections live in this admission,
PR-R1B runtime evidence, and PR-R1C closure reconciliation.

## 6. Next gate

```text
PR-R1A: docs/governance/errata only (this branch)
PR-R1B: runtime + tests + machine evidence (separate branch, exact main after PR-R1A)
PR-R1C: docs/governance closure reconciliation (after PR-R1B protected merge)
Phase 5D: BLOCKED until P38-WP01-R1 CLOSED / MERGED / VERIFIED
POWER 3.8.0: NO-GO
```
