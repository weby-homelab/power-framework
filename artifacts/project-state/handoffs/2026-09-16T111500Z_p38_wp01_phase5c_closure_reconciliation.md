# POWER 3.8 — Phase 5C (P38-WP01 SearchScope Pushdown) Post-Merge Closure Reconciliation Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T11:15:00Z
GATE: Phase 5C (P38-WP01 — SearchScope Pushdown Post-Merge Closure Reconciliation)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-wp01-phase5c-closure
BASE_SHA: 294b48319fdcd3dd3bc030a940bda64f7583889f
BASE_TREE: a22f9267e4ddc626f38e05b23dbdfd6abadd91da
STATUS: CLOSED_AND_VERIFIED
```

---

## 1. Executive Summary & Gate Progression

This handoff documents the authoritative post-merge closure evidence for **Phase 5C / P38-WP01 — SearchScope Pushdown** in `power-framework`.

Live remote GitHub verification on 2026-09-16 confirms the complete 3-PR progression:
- **PR-A (Post-G2 Governance & Phase 5C Admission):** CLOSED / MERGED / VERIFIED (PR #433, merge `6c247c7e4c1788a8bd5388b1327170a8e7493852`)
- **PR-B (Phase 5C Runtime Implementation & Evidence):** CLOSED / MERGED / VERIFIED (PR #434, merge `294b48319fdcd3dd3bc030a940bda64f7583889f`)
- **PR-C (Post-Merge Closure Reconciliation):** Current branch `docs/p38-wp01-phase5c-closure` (reconciles governance state, roadmap, protocol, and planning index)
- **Current Live Main:** `294b48319fdcd3dd3bc030a940bda64f7583889f` (Tree: `a22f9267e4ddc626f38e05b23dbdfd6abadd91da`)
- **Last Closed Gate:** `Phase 5C / P38-WP01 SearchScope Pushdown (main, PR #434)`
- **Next Authorized Gate:** `Phase 5D / P38-WP02 Multi-Domain Union & Conflict Resolution / ContextPack Vertical Slice`

---

## 2. Verified Gate Tuples (Live GitHub Truth)

### PR-A: Phase 5C Admission & Governance Reconciliation
- **Pull Request:** #433 (`docs/p38-pre-5c-admission-reconciliation`)
- **Base SHA:** `7546ff86bd5debdd23c9e5a08cddc7b10224b850`
- **Merge SHA:** `6c247c7e4c1788a8bd5388b1327170a8e7493852`
- **Merge Tree:** `09a6266d6e4336cd3d4c0b7e50561828ae8470af`
- **Status:** `CLOSED / MERGED / VERIFIED`

### PR-B: Phase 5C Runtime Implementation & Evidence
- **Pull Request:** #434 (`feat/p38-wp01-search-scope-pushdown`)
- **Base SHA:** `6c247c7e4c1788a8bd5388b1327170a8e7493852`
- **Candidate Head:** `a643e25a5a761a892ef69b910fb82c66a8a29e99`
- **Candidate Parents:** `842a22df1488c039db130761352eefec7c8b0561`
- **Merge SHA:** `294b48319fdcd3dd3bc030a940bda64f7583889f`
- **Merge Tree:** `a22f9267e4ddc626f38e05b23dbdfd6abadd91da`
- **Merge Parents:** `6c247c7e4c1788a8bd5388b1327170a8e7493852`, `a643e25a5a761a892ef69b910fb82c66a8a29e99`
- **Merge GPG Signature:** Verified valid (GitHub web-flow)
- **Required Check Set (12/12 SUCCESS):**
  1. `test (3.13)` — SUCCESS
  2. `test (3.14)` — SUCCESS
  3. `security` — SUCCESS
  4. `package-smoke` — SUCCESS
  5. `upgrade-matrix (ubuntu-latest)` — SUCCESS
  6. `upgrade-matrix-aggregate` — SUCCESS
  7. `base-runtime-smoke` — SUCCESS
  8. `benchmark-integrity` — SUCCESS
  9. `analyze (python)` — SUCCESS
  10. `CodeQL` — SUCCESS
  11. `build` (Docs) — SUCCESS
  12. `CodeRabbit` — SUCCESS
- **Merged At:** `2026-09-16T11:13:23Z`
- **Status:** `CLOSED / MERGED / VERIFIED`

---

## 3. Implementation Verification & Defect Resolution Summary

Phase 5C runtime implementation strictly adhered to the "SCOPE BEFORE CANDIDATES" architecture principle:

1. **Defect Resolution:**
   - Pre-fix baseline reproduced candidate starvation where top-K unconstrained candidates completely crowded out in-scope target notes (in-scope recall: `0.0`).
   - Post-fix pushdown ensures only in-scope candidates are retrieved, resulting in perfect in-scope recall (`1.0`).

2. **Stage Invariants (Zero Out-of-Scope Materialization):**
   - **FTS Search:** 0 out-of-scope rows materialized via SQL path / note type constraints.
   - **TF Vector Search:** 0 out-of-scope rows materialized via SQL path pushdown.
   - **Dense Semantic Embeddings:** 0 out-of-scope embeddings computed/loaded via new SQLite index `idx_chunk_embeddings_rel_path ON chunk_embeddings(rel_path)`.
   - **Reranker Pool:** 0 out-of-scope candidates fed to reranking pipeline.
   - **Graph BFS Traversal:** 0 out-of-scope hops explored outside resolved scope.
   - **Fallback Scan:** 0 out-of-scope files read from disk.

3. **Security Boundaries & Invariants:**
   - `trust_states`: Fails closed (`UnsupportedSearchScopeError`) since column is unindexed.
   - `project_ids`: Fails closed (`UnsupportedSearchScopeError`) since note-project link is unindexed.
   - `include_archived` & `include_quarantine`: Default to `False`. Privileged access strictly gated behind server-issued `AccessPolicy` with valid `approval_ref`.

4. **Hermetic Testing & CodeQL Cleanliness:**
   - Module cyclic dependency between `search_scope.py` and `searcher.py` was fully decoupled, satisfying CodeQL taint analysis.
   - Neural reranking in test environment utilizes `DummyReranker` protocol mock to guarantee zero-network hermetic execution in offline CI runners.

---

## 4. Next Authorized Work: Phase 5D (P38-WP02)

With Phase 5C closed and verified on `main`, the next sequential runtime gate is:
- **P38-WP02 / Phase 5D:** Multi-Domain Union & Conflict Resolution / RetrievalPlanner / ContextPack Vertical Slice.
- **Rule:** Phase 5D must follow the same strict preflight admission, TDD defect reproduction, and dual-side diff audit standards.
