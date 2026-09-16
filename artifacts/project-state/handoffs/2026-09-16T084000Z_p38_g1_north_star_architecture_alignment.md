# POWER 3.8 — Gate P38-G1 North-Star Architecture Alignment Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T08:40:00Z
GATE: P38-G1 (North-Star Architecture Alignment)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-g1-north-star-architecture
BASE_SHA: df813f4263e472ee4ca9cce6373bf122ec8af5c5
BASE_TREE: 099796bdd4d27d6456f35b6791a10830b87df56d
```

---

## 1. Objective & Architectural Alignment

Gate **P38-G1** freezes the product and architectural direction for POWER 3.8 without
introducing runtime code or premature dependency changes:

- **Target Direction:** POWER is established as a local-first control plane for verifiable
  AI-assisted software engineering and Linux infrastructure operations ([ADR-0007](../../../docs/adr/0007-power-3.8-north-star-control-plane-architecture.md)).
- **Substrate Role:** Knowledge management and Second Brain capabilities are repositioned as a
  supported data substrate and operational context layer rather than the sole product identity.
- **The POWER Proof Chain:** Explicit lifecycle `Goal → Evidence → Plan → Authority → Action → Verification → Receipt → Canonical State`. Terminology uses `verifiable`, `evidence-backed`, `traceable`, and `governed`.
- **The Three Authorities:** Truth Authority, Action Authority, and Completion Authority are
  strictly decoupled. Invariant: `LLM OUTPUT NEVER GRANTS AUTHORITY`.
- **Canonical vs. Derived State:** PSE ledger, ProjectStateService, TaskStore, DecisionService,
  and receipts are canonical owners. Indexes, embeddings, EvidenceGraph, ExecutionGraph,
  and materialized views are rebuildable. Invariant: `DERIVED STATE MUST NEVER SILENTLY BECOME CANONICAL AUTHORITY`.
- **EvidenceGraph:** Typed, bounded, rebuildable, provenance-preserving projection over canonical
  evidence. Apache AGE is not mandatory.
- **ExecutionGraph:** Derived view over existing canonical authority (`PowerTask`, dependencies,
  open gates, receipts). No second planning database.
- **ContextPack:** Bounded, explainable, proof-carrying context compiler. Semantic similarity
  never overrides authority ordering.
- **Observation Contract:** `power.observation.v1` schema with privacy, retention, and sensitivity bounds.
  `RawEvent != Knowledge`, `Agent output != Fact`, `Conversation != Canonical state`, `Embedding != Authority`.
- **Interoperability:** MCP for tools/resources, A2A only when justified by a concrete consumer,
  OpenTelemetry-compatible telemetry, POWER as control plane.
- **Artifact Storage:** Vendor-neutral `ArtifactStore`. Default Edge: `LocalCASArtifactStore`.
- **Edge First:** Default is local-first (Python, SQLite, filesystem, FTS, stdio MCP).
  Optional Hub (PostgreSQL, AGE, pgvector, S3) requires benchmark proof + ADR.
- **Real-Work Validation & Zero-Explanation Handoff:** Synthetic tests are insufficient. Mandatory
  benchmark: Agent B continues from POWER canonical state alone with zero prior chat, zero private memory.
  Outcomes: `DUPLICATE_EFFECTFUL_ACTIONS = 0`, `UNAUTHORIZED_MUTATIONS = 0`, `FALSE_DONE = 0`.

---

## 2. Invariants & Distinctions

- **Runtime changes:** NONE.
- **Dependencies/schemas:** NONE modified.
- **Release discipline:** Stable public release remains `v3.7.13` (on `release/3.7`); development `main` package metadata remains `3.7.11`.
- **Phase progression:** P38-G1 closes architecture. Next authorized gate is **P38-G2 (Product Identity & Documentation Rebaseline)**.
- **Phase 5C readiness:** `READY FOR SEPARATE ADMISSION / NOT STARTED` (strictly gated until G2 closes).
- **POWER 3.8.0:** `NO-GO`.

---

## 3. Exact Files Modified

1. `docs/adr/0007-power-3.8-north-star-control-plane-architecture.md` (new file)
2. `mkdocs.yml` (nav addition under Architecture Decisions)
3. `docs/plans/POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md` (executive summary aligned)
4. `artifacts/project-state/handoffs/2026-09-16T084000Z_p38_g1_north_star_architecture_alignment.md` (this file)

---

## 4. Candidate Tuple

- **Branch:** `docs/p38-g1-north-star-architecture`
- **Base SHA:** `df813f4263e472ee4ca9cce6373bf122ec8af5c5`
- **Base Tree:** `099796bdd4d27d6456f35b6791a10830b87df56d`
- **Candidate Head SHA:** (resolved upon signed commit)
- **Candidate Tree:** (resolved upon signed commit)
- **Candidate Parent:** `df813f4263e472ee4ca9cce6373bf122ec8af5c5`
- **Target PR:** (to be opened against main)
