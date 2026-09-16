# Phase 5C R1 Report — SearchScope Closure Correction (PR-R1B)

```text
EVIDENCE_TYPE: phase5c_r1_report
CREATED_AT_UTC: 2026-09-16T12:30:00Z
BASE_SHA: a0ee8eea36ede547ef4196f4e54f3c3465de044a
BASE_TREE: 629688d882acd241c5e95679f418d60cac736825
STATUS: RUNTIME CORRECTION CANDIDATE (pending protected merge + post-merge readback)
```

## 1. Findings and root causes

- **R1 algebra:** `compile_search_scope()` flattened explicit and domain prefixes
  into one OR list (`path_prefixes`). `is_path_in_scope()` and SQL enforced OR,
  so `domain=projects` + `path=01_Projects/RestrictedProject` matched
  `01_Projects/AnotherProject`. Root cause: missing dimension separation.
  Fix: `explicit_path_prefixes` + `domain_path_prefixes` stored separately;
  OR inside, AND across; SQL emits AND of two OR groups; digest includes both.

- **R2 graph:** scope enforced only after global vault scan, global suggestions,
  global BFS. OOS nodes were read, queued, traversed, bridged, materialized,
  then discarded. Root cause: scope-after-materialization.
  Fix: `_eligible_graph_paths()` before read; `suggest_related_v2(allowed_paths)`
  skips OOS before `read_file_content` and drops OOS explicit links; graph
  contains eligible only; BFS defense-in-depth plus eligible-set gate; bridge
  impossible.

- **R3 fallback:** path-only pre-check, type learned after `read_source`.
  Source-type constrained fallback read excluded sources then discarded.
  Root cause: missing safe metadata pre-check.
  Fix: `_scoped_note_type_from_index()` (fts_notes/source_metadata, no body
  read); pre-check before `read_source`; unknown types fail closed; no
  directory-name inference. Applied to both `_scan_and_search` and
  `_scan_and_vector_search`.

`trust_states`/`project_ids` remain fail-closed. Archive/quarantine defaults
and privileged gates retained. No SearchScope v3; public v2 DTO unbroken.

## 2. Tests (29, all PASS locally)

- 1–8: algebra intersection/union/monotonic/digest/SQL (incl. triple).
- 9–12: graph no OOS reads, no queue, bridge impossible, hops 0.
- 13–14: fallback source-type no OOS reads (scan + TF).
- 15–18: FTS/TF/Dense/Reranker selected OOS = 0 (real SQLite rows, not just results).
- 19–23: archive/quarantine/trust/project/unknown-domain fail-closed.
- 24–25: unscoped legacy, deterministic ordering.
- Plus: property monotonicity, read-only invariant, semantic guard, query
  expansion, security widening-denied.

Focused: `test_phase5c_r1_closure` 29 passed; `test_phase5c_search_scope` 28
passed; `test_searcher` + `test_perf_optimizations` 176 passed with R1;
`test_phase5a/b` 74 passed; relations 50 passed.

## 3. Machine evidence

See `phase5c_r1_verification.json` (adversarial 30+1 quantum fixture):

```text
FTS selected 1 / OOS 0 (was 20/20)
TF selected 1 / OOS 0 (was 30 OOS)
Dense selected 0 / OOS 0 (hermetic, scoped SQL)
Reranker input 1 / OOS 0 (was 20/20)
Graph considered 1, visited 1, OOS reads 0, OOS hops 0
Fallback reads 1 / OOS 0 (was 30 OOS)
Recall 1.0 (was 0.0)
p50 5.58ms / p95 8.5ms / peak 40.77MB (single-query; full-suite peak differs)
```

No invented counters. Historical JSON not rewritten.

## 4. Security and invariants

- Additional restriction never widens access (monotonicity tested).
- SQL uses parameterized LIKE with wildcard escaping; no injection.
- Path traversal/encoded traversal rejected by SearchScope validators.
- Scope digest distinguishes combined scopes (cache collision denied).
- Graph escape/bridge denied by eligible-only build + BFS gate.
- Fallback metadata leakage denied by pre-read index check + fail-closed.
- Unauthorized archive/quarantine denied; caller-created AccessPolicy rejected
  by authorization-boundary token.
- Query expansion keeps identical resolved scope.
- Read-only: vault files unmutated (tested); PSE/Task/Decision/proposals/
  generation pointer untouched (search is read-only; temp-state fixtures only
  where existing test contract allows).

## 5. Performance

Correctness/security beat synthetic latency. R1 single-dimension SQL is
equivalent to PR434; combined scopes narrow (fewer candidates/reads).
Reported p50/p95/peak above on same fixture. No hard threshold per contracts.

## 6. What R1 does NOT do

No RetrievalPlanner, ContextPackCompiler, Context Broker, new MCP tools, noise
planner, FAST/BALANCED/DEEP execution, capture, A2A, AGE, pgvector, PostgreSQL,
version bump, tag, or release. Phase 5D remains blocked until R1 closed.
