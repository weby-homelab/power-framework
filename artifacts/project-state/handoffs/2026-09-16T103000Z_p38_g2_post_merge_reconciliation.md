# POWER 3.8 — Gate P38-G2 Post-Merge Closure & Phase 5C Admission Reconciliation Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T10:30:00Z
GATE: P38-G2 (Post-Merge Reconciliation & Closure) -> Phase 5C (SearchScope Pushdown Admission)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-pre-5c-admission-reconciliation
BASE_SHA: 7546ff86bd5debdd23c9e5a08cddc7b10224b850
BASE_TREE: 2e3e0233639270df5e92d1b348873c0fd6194b38
```

---

## 1. Executive Summary & Gate Progression

This handoff establishes authoritative post-merge closure evidence for **Gate P38-G2** (Product Identity & Documentation Rebaseline) and executes the **Phase 5C (P38-WP01 — SearchScope Pushdown) Admission Audit**.

Live remote GitHub verification on 2026-09-16 confirms:
- **Gate P38-G0:** CLOSED / MERGED / VERIFIED (PR #429)
- **Gate P38-G1:** CLOSED / MERGED / VERIFIED (PR #430)
- **Gate P38-G2:** CLOSED / MERGED / VERIFIED (PR #431)
- **Current Live Main:** `7546ff86bd5debdd23c9e5a08cddc7b10224b850` (Tree: `2e3e0233639270df5e92d1b348873c0fd6194b38`)
- **Last Closed Gate:** `P38-G2`
- **Next Authorized Gate:** `P38-WP01 / Phase 5C SearchScope Pushdown`
- **Phase 5C Admission Status:** `ADMITTED / NOT STARTED`

---

## 2. Verified Gate Tuples (Live GitHub Truth)

### Gate P38-G0 (Governance Rebaseline)
- **Pull Request:** #429 (`docs/p38-g0-governance-rebaseline`)
- **Base SHA:** `3cb94ff7f82d18c0f77b336848d1c34f220e58a3`
- **Candidate Head:** `de808efffadab767c7797c69d8325dc557675086`
- **Candidate GPG:** Verified valid (key `2D49E810C7F2527E`)
- **Merge SHA:** `df813f4263e472ee4ca9cce6373bf122ec8af5c5`
- **Merge Tree:** `099796bdd4d27d6456f35b6791a10830b87df56d`
- **Merge Parents:** `3cb94ff7f82d18c0f77b336848d1c34f220e58a3`, `de808efffadab767c7797c69d8325dc557675086`
- **Merge Signature:** Verified valid (GitHub web-flow)
- **Required Checks:** 11/11 PASS
- **Status:** `CLOSED / MERGED / VERIFIED`

### Gate P38-G1 (North-Star Architecture Alignment)
- **Pull Request:** #430 (`docs/p38-g1-north-star-architecture`)
- **Base SHA:** `df813f4263e472ee4ca9cce6373bf122ec8af5c5`
- **Candidate Head:** `1788605f4d4f21a772e8d6305eda57116c1dffa1`
- **Candidate GPG:** Verified valid (key `2D49E810C7F2527E`)
- **Merge SHA:** `38f656b50da3b2307456f673ed1f77e01e907470`
- **Merge Tree:** `ac7c62872f0fe9d1de6d5d0b232aa24ea58509c0`
- **Merge Parents:** `df813f4263e472ee4ca9cce6373bf122ec8af5c5`, `1788605f4d4f21a772e8d6305eda57116c1dffa1`
- **Merge Signature:** Verified valid (GitHub web-flow)
- **Required Checks:** 11/11 PASS
- **Status:** `CLOSED / MERGED / VERIFIED`

### Gate P38-G2 (Product Identity & Documentation Rebaseline)
- **Pull Request:** #431 (`docs/p38-g2-product-identity-documentation`)
- **Base SHA:** `38f656b50da3b2307456f673ed1f77e01e907470`
- **Base Tree:** `ac7c62872f0fe9d1de6d5d0b232aa24ea58509c0`
- **Candidate Head:** `0d46e12be25d6e0936c6e6512980564061979497`
- **Candidate Tree:** `2e3e0233639270df5e92d1b348873c0fd6194b38`
- **Candidate Parents:** `38f656b50da3b2307456f673ed1f77e01e907470`
- **Candidate GPG:** Verified valid (`166E0A4F873E897A8060DD38DD92FC45BD1D6C30` / `2D49E810C7F2527E`, Weby Homelab)
- **Merge SHA:** `7546ff86bd5debdd23c9e5a08cddc7b10224b850`
- **Merge Tree:** `2e3e0233639270df5e92d1b348873c0fd6194b38`
- **Merge Parents:** `38f656b50da3b2307456f673ed1f77e01e907470`, `0d46e12be25d6e0936c6e6512980564061979497`
- **Merge Signature:** Verified valid (GitHub web-flow `B5690EEEBB952194`)
- **Required Check Set (11/11 SUCCESS):**
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
  11. `build` — SUCCESS
- **Non-Required Checks:**
  - `deploy` (Docs) — SUCCESS
  - `update-uv-graph` — SUCCESS
  - `Dependabot` — FAILURE (investigated & dispositioned below)
- **Status:** `CLOSED / MERGED / VERIFIED`

---

## 3. Post-Merge Dependabot Failure Disposition

- **Observed:** Action run `35076361715`, job `104729611939` (`Dependabot`) reported `failure` on `main` at commit `7546ff86bd5debdd23c9e5a08cddc7b10224b850`.
- **Annotation:** Path `.github`, line 3718: `Dependabot encountered an error performing the update`.
- **Classification:** **`C: NON-REQUIRED DEPENDENCY UPDATE ATTEMPT FAILURE`**.
- **Evidence & Rationale:**
  1. `Dependabot` is **not** a required status check in branch protection contexts (the 11 required contexts are strictly enumerated above).
  2. The job is an automated external dynamic update runner attempting to parse and generate PRs for maintenance groups.
  3. All 11 required CI/CD checks, CodeQL, security audits, and package build checks passed without error on the exact tree.
  4. Dependabot subsequently generated and opened PR #432 (`dependabot/uv/maintenance-eef1a41d26`).
  5. The current tree integrity of `main` is completely healthy and uncompromised.
- **Disposition:** **`NON-BLOCKING / EXPLICITLY DISPOSITIONED`**. Does not impede Phase 5C admission.

---

## 4. SearchScope Capability Map (Pre-Implementation Contract)

Every dimension of `SearchScope` (`src/power_framework/core/context_contracts.py`) is mapped against canonical architecture sources:

| Dimension | Canonical Source of Truth | Current Representation | Execution-Stage Enforcement | SQL/Projection Enforcement | Fallback Enforcement | Authorization Requirement | Supported? | Reason / Implementation Semantics |
|---|---|---|---|---|---|---|---|---|
| `domain_ids` | Domain Policy v2 (`domains.yaml` / `DomainRegistry`) | `list[Identifier]` | Candidate pre-selection before ranking | Domain path matching via `source_metadata` or configured domain path prefixes | Evaluated before reading files | None (public parameter) | **YES** | Multi-domain union/intersection semantics supported via Domain Policy v2 path selectors. |
| `path_prefixes` | Vault filesystem hierarchy / `source_metadata.rel_path` | `list[SourceReference]` | Candidate pre-selection before LIMIT/scoring | Parameterized SQL `LIKE ? ESCAPE '\'` on `rel_path` with wildcard escaping (`%`, `_`) and boundary slash normalization | Evaluated before file read in fallback scan | None | **YES** | Exact directory/file boundary enforcement preventing partial name collision (e.g. `01_Projects/A` cannot match `01_Projects/AnotherProject`). |
| `source_types` | OKF `NoteType` enum (Project, Area, Resource, Daily Log, Archive, System Guide) | `list[Identifier]` | Candidate pre-selection before LIMIT/scoring | Parameterized SQL `note_type IN (...)` on `source_metadata` / `fts_notes` | Filtered before content read / scoring | None | **YES** | Maps directly to canonical OKF note types. |
| `trust_states` | OKF v0.2 `MemoryMetadata` / `TrustState` | `list[TrustState]` | Boundary validation | None in current SQLite index schema | None | None | **NO (FAIL CLOSED)** | No indexed column for `trust_states` exists in current generation database. Non-empty `trust_states` must fail closed (`UnsupportedSearchScopeError`) rather than silently being ignored. |
| `temporal_boundary` | `temporal_records` table / OKF timestamps via `temporal.py` | `TemporalBoundary(as_of, include_historical)` | Candidate pre-selection before top-K truncation | Query eligible paths via `load_temporal_records` before LIMIT | Filter via `scan_temporal_records` before scoring | None | **YES** | Temporal status resolution runs prior to candidate truncation so current notes are not starved by historical top-ranked notes. Defense-in-depth post-filter retained. |
| `project_ids` | Project Event Stores (`.power/projects/prj_*`) / `project_state.db` | `list[Identifier]` | Boundary validation | None in knowledge vault `source_metadata` | None | None | **NO (FAIL CLOSED)** | Vault notes currently have no searchable project-to-note association in the search index. Non-empty `project_ids` must fail closed (`UnsupportedSearchScopeError`) rather than being ignored. |
| `include_archived` | OKF `NoteStatus.ARCHIVED` / `04_Archive` | `StrictBool` (default `False`) | Excluded from candidate generation by default | Exclude paths starting with `04_Archive/` and `note_type='Archive'` | Skip before reading content | Server-issued `AccessPolicy` with `raw_access="privileged"` and valid `approval_ref` | **YES** | Defaults to `False` (safe). Caller setting `True` without server-derived authority fails closed (`AccessDeniedError` / denied). |
| `include_quarantine` | Quarantine storage / `TrustState.QUARANTINED` | `StrictBool` (default `False`) | Excluded from candidate generation by default | Exclude quarantined paths | Skip before reading content | Server-issued `AccessPolicy` with `quarantine_access="privileged"` and valid `approval_ref` | **YES** | Defaults to `False` (safe). Caller setting `True` without server-derived authority fails closed (`AccessDeniedError` / denied). |

---

## 5. Current Retrieval-Path Audit & Defect Profile

Audit of current `src/power_framework/core/searcher.py`:
1. **FTS (`_fts_search`):** Currently queries `fts_notes MATCH ? ORDER BY score DESC LIMIT ?` globally without scope pushdown. Post-filters domain and temporal status after candidate truncation.
2. **TF-Vector (`_vector_search`):** Currently executes `SELECT ... FROM tf_vectors JOIN fts_notes` loading the **entire corpus** into Python memory before computing cosine similarity.
3. **Dense (`_semantic_search`):** Loads **all** rows from `chunk_embeddings` into a single global matrix. Out-of-scope embeddings are materialized and scored globally.
4. **Dense Cache:** Keyed only by vault and generation identity, with no scope awareness.
5. **Reranker (`_hybrid_reranked_search`):** Collects candidates globally, merges them, and selects top-20 candidates for cross-encoder reranking before domain/scope post-filtering.
6. **Graph-Assisted (`_graph_assisted_search`):** Expands graph hops using `suggest_related_v2` without scoping anchor or traversed neighbour paths.
7. **Fallback Scan (`_scan_and_search`):** Iterates vault files and calls `read_source` **before** checking domain/scope eligibility.
8. **Semantic Lexical Guard:** Calls `_fts_search` without scope, potentially introducing out-of-scope candidates.

**Defect Impact (Starvation):**
When out-of-scope documents have higher global BM25 or vector similarity than the in-scope target, global top-K truncation starves the in-scope target, causing 0 results even when relevant in-scope documents exist.

---

## 6. Phase 5C Implementation Invariants & Verification Contract

1. `SCOPE BEFORE CANDIDATES`: Scope resolution happens before any candidate selection, LIMIT, or scoring.
2. `CANDIDATES BEFORE EXPENSIVE MODELS`: Expensive cross-encoders and dense models only process already-scoped candidate documents.
3. `ZERO OUT-OF-SCOPE CANDIDATES`:
   - `OUT_OF_SCOPE_CANDIDATES_AT_STAGE_BOUNDARY = 0`
   - `OUT_OF_SCOPE_TF_ROWS_MATERIALIZED = 0`
   - `OUT_OF_SCOPE_DENSE_ROWS_MATERIALIZED = 0`
   - `OUT_OF_SCOPE_RERANK_DOCUMENTS = 0`
   - `OUT_OF_SCOPE_GRAPH_HOPS = 0`
   - `OUT_OF_SCOPE_FALLBACK_SOURCE_READS = 0`
4. `DEFENSE IN DEPTH`: Retain final `_filter_domain_results` and `_filter_temporal_results` as secondary safeguards.
5. `BACKWARD COMPATIBILITY`: Unscoped legacy calls (`search_vault(vault_dir, query, mode=...)`) maintain 100% behavioral parity.
6. `FAIL-CLOSED PRIVILEGE`: Setting `include_archived=True` or `include_quarantine=True` without server-issued `AccessPolicy` fails closed.
7. `UNSUPPORTED SCOPE FAIL CLOSED`: Non-empty `project_ids` or `trust_states` fail closed with explicit typed error.

---

## 7. Explicit Non-Scope for Phase 5C

The following items belong to subsequent phases (5D+) and are strictly forbidden in Phase 5C:
- `RetrievalPlanner` implementation (Phase 5D)
- `ContextPackCompiler` / runtime packaging (Phase 5D)
- New MCP context tools or Context Broker (Phase 5D/5G)
- Automatic capture or persistent `IndexWorkQueue` (Phase 6)
- Dirty-set Phase 5F redesign
- EvidenceGraph / Apache AGE / pgvector / PostgreSQL (Phase 7)
- Agent-to-Agent (A2A) protocol
- POWER version bump or public release tag

---

## 8. Admission Decision

**GATE P38-G2:** CLOSED / VERIFIED
**GATE PHASE 5C (P38-WP01):** **`ADMITTED / NOT STARTED`**
Implementation authorized under PR-B on branch `feat/p38-wp01-search-scope-pushdown` following protected merge of PR-A.
