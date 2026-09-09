# POWER 3.8 — Context / Memory / Retrieval Architecture

> **Architecture status:** APPROVED PLANNING DIRECTION
>
> **Publication class:** Versioned pre-implementation architecture plan
>
> **Implementation status:** NOT IMPLEMENTED
>
> **Canonical status:** CANONICAL PLANNING after the protected merge of the
> planning PR. The plan is provisional while its PR is open.

This document is the human-readable architecture contract for POWER 3.8
context, memory, and retrieval work. It is deliberately a planning artifact,
not a Phase 5 implementation report. It records what already exists, what must
be reused, what must be built later, which phase owns each capability, and the
evidence required before a phase can advance.

The plan records a governance snapshot based on protected `main` SHA
`a386858a45489eb5db213d42ffe773db9134ff88` observed during the final
integration gate on 2026-09-09. Mutable GitHub state, PR status, branch policy,
and check results must be revalidated by every future agent before action.

## 1. Executive Summary

POWER 3.8 will extend the existing POWER engine with bounded, hierarchical,
domain-aware retrieval and governed context assembly. The target is a system
that can move from captured evidence to typed semantic candidates, select
existing authoritative knowledge at a controlled cost, and return a bounded
`ContextPack` whose provenance, trust, authority, freshness, contradictions,
noise decisions, and token cost are visible to the caller.

The architecture has four non-negotiable properties:

1. **Reuse before invention.** Existing search, domain, chunking, model,
   project-state, task, decision, memory, maintenance, and index boundaries
   remain the only canonical owners of their concerns.
2. **Authority is explicit.** Raw events, model output, retrieved Markdown,
   projections, and caches are evidence or derived data; they cannot grant
   themselves canonical authority.
3. **Cost is progressive.** Exact/state and sparse retrieval precede dense,
   reranking, graph expansion, and raw fallback. A normal query must not trigger
   a global reindex or the most expensive retrieval profile by default.
4. **Evidence is retained.** Noise suppression changes retrieval disposition,
   not source existence. Raw evidence is append-only, privacy-bounded, and
   recoverable according to an explicit retention policy.

The Controlled Dependency Refresh is closed at final integration. The next
runtime gate is Pre-Phase-5 Foundation Hardening; it is planned and not
started. This plan does not start Foundation Hardening, Actions #396, Phase 5,
capture, migration, a release, or a public version change.

## 1A. Course-correction reconciliation

This section is a planning contract, not runtime evidence. The corrections are
explicit so a future agent cannot infer implementation from the architecture
diagram:

| Correction | Previous planning risk | Current planning rule | Implemented? |
|---|---|---|---|
| Retention | Audit metadata could be confused with indefinite payload retention | `RetentionClass`, `SensitivityClass`, `PayloadRetentionPolicy`, and bounded tombstone/deletion receipts separate payload action from append-only audit evidence | PLANNING ONLY |
| Time | One timestamp could conflate delayed capture and validity | Keep `observed_at` and `recorded_at` distinct; add optional `valid_from`/`valid_to` only when meaningful | PLANNING ONLY |
| Evidence ordering | Semantic similarity could outrank canonical authority | Apply access, authority, temporal/supersession, contradiction, relevance, reranking, then diversity/token packing as explainable stages | PLANNING ONLY |
| Resources | PRXMX-01 or another host could become a framework invariant | Use abstract `ResourceProfile`/`HostCapabilityProfile`; machine facts belong to deployment and benchmark evidence | PLANNING ONLY |
| Budgets | FAST/BALANCED/DEEP numbers could become eternal constants | Use structural ceilings, resource defaults, domain caps, and caller-lower-only hints; calibrate in Phase 5 shadow | PLANNING ONLY |
| Retries | High retry counts could create retry storms | Use a small bounded retry budget, exponential/backoff, dead-letter, and explicit review before requeue | PLANNING ONLY |
| Evaluation | Tuning and holdout integrity were underspecified | Freeze a versioned manifest with category coverage, digests, provenance, development/holdout splits, and no holdout tuning | PLANNING ONLY |
| Queue ownership | A diagram could make a persistent queue a Phase 5 prerequisite | Phase 5 proves only the minimum dirty-set/index-validity substrate; Phase 6 owns persistent `IndexWorkQueue` unless an ADR proves earlier need | PLANNING ONLY |
| Broker | A façade could be built for its own sake | Context Broker is optional and requires multiple real consumers demonstrating orchestration value beyond existing compiler/service/views | PLANNING ONLY |

The machine-readable v2 contract is
`artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json`.
The evaluation manifest contract is
`artifacts/project-state/planning/retrieval-eval-v1.schema.json`. Both are
planning-only and not consumed by the current runtime.

## 2. Scope / Non-Scope

### In scope for this planning gate

- The logical capture, knowledge, index, retrieval, context, and governed
  mutation architecture.
- Versioned planning contracts for intent, routing, retrieval stages, noise,
  context packs, index work, cost, and memory actions.
- Domain Policy v2 as a backward-compatible planning direction over domain v1.
- Phase 5A–5H and the architectural scope of Phases 6–9.
- Acceptance evidence, shadow mode, migration ordering, and anti-goals.
- Repository-native documentation and pre-implementation artifacts only.

### Explicitly out of scope

- Any Phase 5 source implementation or runtime parser.
- Changes to `src/power_framework/core/searcher.py`, `domains.py`,
  `index_sync.py`, `generation_index.py`, `chunker.py`, `embeddings.py`,
  `reranker.py`, or any other source module.
- Changes to tests, dependencies, lock files, workflows, public version, tags,
  or releases.
- Modification or merge of Actions #396.
- Capture adapters, automatic agent capture, conversation bulk ingestion, or a
  production reindex migration.
- A new vector database, ANN service, MCP network plane, or parallel authority
  store.

The words **planned**, **approved planning direction**, and **not implemented**
refer to future runtime behavior. They must not be reported as `IMPLEMENTED`
or `VALIDATED` until the corresponding phase has passed its evidence gate.

## 3. Verified Existing Foundation

The following table is based on the source tree at the plan-start SHA. A
documentation claim is not treated as proof when the source behavior is
different.

| Capability | Actual component/path | Current status | Reuse strategy | Future gap |
|---|---|---|---|---|
| FTS5 / BM25 | `src/power_framework/core/db.py`, `src/power_framework/core/searcher.py` | IMPLEMENTED | Reuse the existing FTS schema, weighted BM25 query, source-read boundary, and fallback envelope | Add scope pushdown and stable bounded candidate contracts |
| Sparse TF vector | `src/power_framework/core/index_sync.py`, `searcher.py` | IMPLEMENTED, lexical | Reuse normalized term-frequency projection and sparse scoring | Make scope and candidate budgets explicit before candidate generation |
| Hybrid / RRF | `src/power_framework/core/searcher.py` (`SEARCH_MODE_REGISTRY`, `_rrf_merge_many`) | IMPLEMENTED, with a defined limitation | Reuse existing sparse RRF; preserve its evidence-backed ordering while specifying dense fusion deliberately | Define three-way fusion and domain-aware candidate bounds without silently changing legacy quality |
| Dense semantic search | `src/power_framework/core/searcher.py`, `chunk_embeddings` | IMPLEMENTED, optional | Reuse the verified generation resolver, dense validation, matrix cache, and provenance envelope | Replace global matrix scanning with pushed-down scope/candidate selection and dirty-set validity |
| Local embedding backend | `src/power_framework/experimental/embeddings.py` (`BGEM3OnnxManager`) | IMPLEMENTED, optional and fail-closed | Reuse BGE-M3 direct ONNX Runtime, tokenizer, pinned model policy, hashes, lazy/eager probe, and CPU bounds | Add versioned per-chunk identity and cost-aware queueing; do not add a second loader |
| Local reranker | `src/power_framework/experimental/reranker.py` (`BGEM3Reranker`) | IMPLEMENTED, optional | Reuse the BGE ONNX reranker, pinned assets, batch bounds, and existing opt-in policy | Make reranking a budgeted planner stage with explicit fallback and telemetry |
| Semantic chunking | `src/power_framework/core/chunker.py` (`SemanticChunker`) | STRUCTURAL / CONTEXTUAL IMPLEMENTED | Reuse header, paragraph, fixed modes and document context prefixes | Version any future semantic-boundary strategy; do not claim embedding-based segmentation exists |
| Domain registry | `src/power_framework/core/domains.py`, `.power/domains.yaml` | DOMAIN V1 IMPLEMENTED, opt-in | Evolve `DomainRegistry` backward-compatibly; keep legacy P.A.R.A. behavior when absent | Add multi-match routing, traversal, trust policy, index priority, and pushdown scope |
| Temporal views | `src/power_framework/core/temporal.py` and `searcher.py` | IMPLEMENTED as lifecycle/status views | Reuse deterministic `current`, `historical`, `all`, and `as_of` resolution | Push temporal constraints into candidate selection; do not imply a document version store |
| Graph-assisted retrieval | `src/power_framework/core/searcher.py`, `src/power_framework/experimental/relations.py` | PARTIAL / EXPERIMENTAL | Reuse persisted source projections where valid and keep graph hops as ranking signals | Replace repeated all-pairs suggestion work with reviewed, bounded, domain-specific traversal |
| Atomic index generations | `src/power_framework/core/generation_index.py` | IMPLEMENTED | Reuse staged SQLite generations, snapshot validation, integrity checks, atomic pointer publication, and retention | Add per-source/per-chunk validity and an explicit `IndexWorkQueue` |
| Incremental sync | `src/power_framework/core/index_sync.py` | IMPLEMENTED, file/mtime oriented | Reuse batch embedding and low-RAM controls as a compatibility baseline | Content-hash dirty chunks, exact coverage, model identity, and no normal global rebuild |
| Project semantic compiler | `src/power_framework/core/semantic_compiler.py`, `semantic_models.py` | PHASE 3 CLOSED / FROZEN; candidate/proposal producer | Reuse the existing Project Semantic Compiler role and its provenance-bound candidates | Do not use it as a context assembler; close remaining authority concerns in its own governed work |
| Project state authority | `src/power_framework/core/state_service.py`, `state_reducer.py`, `project_store.py` | PHASE 4 CLOSED / FROZEN | Read authoritative state only through `ProjectStateService` and its Task/Decision federation | Expose bounded read-only context inputs without bypassing the service boundary |
| Tasks and decisions | `src/power_framework/core/task_service.py`, `task_store.py`, `decision_service.py` | IMPLEMENTED, canonical owners | Reuse existing TaskService/TaskStore and DecisionService receipts and lifecycle rules | Add no ContextTask or second approval store |
| Transactional memory | `src/power_framework/core/memory_api.py`, MCP memory tools | IMPLEMENTED, proposal/apply workflow | Reuse content-addressed proposals, preimage/postimage hashes, idempotency, rollback, index, lint, and receipts | Add disposition/promotion planning without bypassing proposal/apply |
| Session synthesis | `src/power_framework/core/synthesize.py`, MCP `synthesize_session` | IMPLEMENTED direct ingest path | Treat it as a legacy explicit write surface; future capture must use raw/working/proposal boundaries | Prevent “every message becomes canonical” behavior in the capture architecture |
| Maintenance | `src/power_framework/core/maintenance.py` | IMPLEMENTED, preview-first repair | Reuse hash-bound safe repairs, backups, and plan classes | Govern semantic repair, durable receipts, crash recovery, and post-repair synchronization |
| Raw evidence | `src/power_framework/core/project_ingestion.py` | IMPLEMENTED for selected privacy modes | Reuse redaction, local permissions, idempotency, TTL, and path containment | Define append-only capture event storage, backpressure, session identity, and retention policy |
| Materialized source projection | `src/power_framework/core/source_projection.py`, `project_ingestion.py` | IMPLEMENTED as derived projection | Reuse rebuildable source metadata/links and generation identity | Add broker-owned view contracts without a parallel source of truth |
| MCP surfaces | `src/power_framework/mcp/power_server.py` | IMPLEMENTED for existing search/memory/maintenance surfaces | Extend through `ApplicationService` and a small number of typed tools | Add context/explainability/index-cost read surfaces only after Phase 5 contracts |
| Vector database / ANN | No mandatory component in the current tree | NOT REQUIRED | Benchmark existing SQLite/scope/dirty-set path first | A future `VectorIndexBackend` requires benchmark, ADR, supply-chain admission, and operational-cost proof |

Important source-name clarification: the Phase 3 contract describes the
**Project Semantic Compiler** role, while the current Python class is named
`SemanticCompiler`. POWER 3.8 must not create a generic `SemanticCompiler`
alias, rename it opportunistically, or place context assembly inside it. The
future read-only assembler is explicitly named `ContextPackCompiler`.

## 4. Architectural Problems / Gaps

These are planning inputs, not authorization to fix source code in this gate.

### P0 — blockers to a safe future implementation

1. **The v2 runtime contract is not implemented yet.** The planning v2 schema
   now names authority, retention, bitemporal, resource, retry, budget, and
   evaluation boundaries; runtime validation remains a future Phase 5A task.
2. **The current gate is not Phase 5.** Pre-Phase-5 Foundation Hardening is the
   next runtime admission and Phase 5 implementation remains
   `BLOCKED / NOT STARTED`.
3. **Authority must remain separate from integrity.** Canonical ledger
   membership, model extraction, caller approval, and retrieved evidence cannot
   be collapsed into one boolean or one domain field.

### P1 — architecture, I/O, and lifecycle gaps

1. Current semantic search reads all `chunk_embeddings` rows into a NumPy
   matrix before domain filtering (`searcher.py`), so domain scope is not yet
   pushed into candidate generation.
2. The current FTS-only path invalidates the global dense manifest after a
   source change (`index_sync.py`). The next dense sync can therefore reset
   mtimes and re-embed the full corpus. The future dirty-set contract must make
   ordinary source edits local.
3. Dense validity is presently organized around a global manifest and
   file/mtime-oriented change detection; model identity, exact chunk coverage,
   and per-chunk pending work must become explicit.
4. Existing graph-assisted retrieval repeatedly constructs dynamic suggestions
   and is not yet a persisted reviewed graph traversal contract.
5. `SemanticCompiler` produces candidates and contradiction proposals, while
   `ProjectStateService` is the authoritative state composition boundary. A
   context plan must consume existing authority, not duplicate either pipeline.
6. Existing explicit agent-facing ingest paths can write notes through the
   shared mutation path. Future capture must not turn that behavior into
   automatic canonical promotion or unbounded embedding.
7. Maintenance has useful hash-bound safe repair primitives, but semantic
   repair, durable receipts, actor identity, crash recovery, and authority
   approval need a single governed boundary.

### P2 — quality and documentation debt

1. Current structural chunking is contextual rather than embedding-based
   semantic segmentation.
2. Temporal filtering and domain filtering occur after portions of candidate
   generation in current search paths; the plan must require quality tests for
   under-retrieval.
3. Existing compatibility shims, legacy handoff/control-plane paths, and
   historical phase namespaces must be treated as evidence, not copied as new
   authorities.

## 5. Architectural Principles

The following rules are binding for future implementation:

- Architecture first; mass capture and migration later.
- Reuse existing canonical components before introducing any new abstraction.
- Semantic domain and trust/lifecycle state are orthogonal dimensions.
- Raw source is append-only evidence; canonical ledgers and approved notes are
  governed source truth.
- Curated semantic entities are derived projections unless promoted through a
  declared authority workflow.
- Indexes, caches, materialized views, embeddings, and reranker outputs are
  rebuildable and never authoritative.
- Cheap exact/state and sparse retrieval precede expensive neural and graph
  work.
- Scope is resolved before dense matrix construction and before reranking.
- Ordinary source edits must not require global re-embedding by design.
- Noise suppression is non-destructive and never deletes raw evidence.
- Model output is untrusted input and cannot self-promote to canonical status.
- Context assembly is read-only and cannot mutate PSE, TaskService,
  DecisionService, memory, the vault, or index state.
- Contracts are versioned before runtime code consumes them.
- Shadow mode must pass before a new retrieval planner becomes default.
- Every expensive index action has a cost estimate and a policy outcome.
- Every mutating semantic repair is proposal-first, approval-bound,
  idempotent, verifiable, and receipted.

## 6. Target End-to-End Architecture

The following logical architecture is planned. It is not a statement that all
boxes or arrows already exist in the source tree.

```text
                         CAPTURE PLANE
 Agents / CLI / MCP / Codex / OpenCode / integrations
                              │
                              ▼
                       Append-only Raw Events
                              │
                              ▼
                    Normalization / Noise Gate
                       ┌──────┴──────┐
                       ▼             ▼
                  Quarantine     Candidates
                                      │
                                      ▼
                       ProjectSemanticCompiler
                                      │
                           typed + provenance-bound
                                      │
              ┌───────────────────────┴──────────────────────┐
              │                 KNOWLEDGE PLANE               │
              │ PSE / Tasks / Decisions                      │
              │ Durable Knowledge                             │
              │ Working Memory                                │
              │ Conversation Memory                           │
              └───────────────────────┬──────────────────────┘
                                      ▼
                         Semantic Domain Membership
                                      │
              ┌───────────────────────┴──────────────────────┐
              │                   INDEX PLANE                 │
              │ FTS / BM25                                    │
              │ TF vectors                                    │
              │ Dense BGE-M3                                  │
              │ Graph                                          │
              │ Materialized Views                             │
              └───────────────────────┬──────────────────────┘
                                      ▼
                             RetrievalPlanner
                                      │
                         Domain-specific traversal
                                      │
                         Candidate Fusion / RRF
                                      │
                            Noise / Trust Gate
                                      │
                         Local BGE-M3 Reranker
                                      │
                           ContextPackCompiler
                                      │
                              Context Broker
                                      │
                                    Agent
                                      │
                              MemoryActionPolicy
                                      │
                 ┌──────────┬─────────┼──────────┬──────────┐
                 ▼          ▼         ▼          ▼          ▼
                NOOP       INDEX   PROPOSE    REPAIR     DEFER
                                      │          │
                                      └────┬─────┘
                                           ▼
                                  Governed Mutation
```

The `ProjectSemanticCompiler` and `ContextPackCompiler` have different
directions of travel:

```text
ProjectSemanticCompiler:
raw/canonical events → semantic knowledge candidates/entities

ContextPackCompiler:
query/intent → select existing knowledge → bounded context pack
```

The latter must not compile new semantic entities during every query.

## 7. Semantic Domain Axis

Every source, candidate, projection, and context item may belong to one or
more semantic domains. The domain answers **what the information is about**;
it does not answer whether the information is authoritative.

Initial planning vocabulary:

```text
project_state
projects
decisions
tasks
code
infrastructure
research
documentation
operations
agent_conversations
governance
handoffs
dependencies
logs
knowledge
```

Domain membership may be derived from path selectors, validated tags, note
types, project IDs, structured event types, and explicit reviewed membership.
The derivation must be deterministic or explainable; an LLM classification is
a candidate signal, not authority.

The existing v1 registry remains valid. Domain Policy v2 adds retrieval and
lifecycle policy without requiring all vaults to adopt it. A vault with no v2
policy retains legacy P.A.R.A. placement and current behavior.

## 8. Trust / Lifecycle Axis

Trust and lifecycle answer **how the information may be used**. They are
independent of the semantic domain.

```text
RAW
PROPOSED
CURATED
VERIFIED
CANONICAL
SUPERSEDED
ARCHIVED
QUARANTINED
NOISE
```

Binding rules:

- `domain != authority` and `domain != lifecycle`.
- `path != trust`; a file path is a routing signal, not proof of authority.
- `chat` is not untrusted forever, but it is not canonical merely because it
  was captured. Promotion needs provenance, policy, and evidence.
- `archive` is a lifecycle state, not a semantic domain.
- `QUARANTINED` and `NOISE` remain discoverable for diagnostics and retention
  policy, but are excluded or downranked from normal retrieval by default.
- A canonical item may be superseded or archived without deleting its
  provenance or historical link.

## 9. Domain Policy v2

Domain v2 is a planning contract and a backward-compatible evolution, not a
runtime parser in this gate. The example is in
`artifacts/project-state/planning/domain-policy-v2.example.yaml`.

The planned shape combines:

- selectors: paths, tags, and types;
- retrieval stages and candidate budgets;
- index priority and dense eagerness;
- noise suppression policy;
- authority preference ordering;
- optional traversal and temporal hints.

Example shape:

```yaml
version: 2

domains:
  - name: projects
    selectors:
      paths:
        - 01_Projects/**
      tags:
        - project
      types:
        - project
        - decision
    retrieval:
      stages:
        - project_state
        - fts
        - semantic
        - rerank
      max_candidates: 60
      rerank_top_k: 15
      budget_class: BALANCED
      escalation:
        budget_class: DEEP
        stages:
          - graph_assisted
    index:
      priority: HOT
      dense: eager
    noise:
      suppress:
        - superseded
        - trivial
        - duplicate
    authority:
      prefer:
        - canonical
        - verified
        - proposed
```

This example is intentionally not consumed by the current runtime. Unknown
v2 fields, precedence rules, and policy merge semantics remain open decisions
until the Phase 5 contract gate.

## 10. Multi-Domain Routing

The planner must return zero or more domain matches, not force a query into a
single domain:

```text
query
  ↓
DomainMatch[]
  ├─ project_state   0.97  reasons: ["current project", "state term"]
  ├─ governance      0.93  reasons: ["roadmap", "handoff"]
  ├─ dependencies    0.81  reasons: ["dependency term"]
  └─ handoffs        0.72  reasons: ["next gate"]
```

`DomainMatch` contains `domain`, a bounded `score` in `[0, 1]`, and
explainable `reasons`. A source may have multiple memberships; a future
`ContextItem.domain` is its primary selected domain and
`ContextItem.domains` carries the full bounded membership set. The planner
allocates work by confidence:

- top domain: full domain-specific traversal;
- secondary domains: bounded traversal within the remaining budget;
- low-confidence domains: cheap probe or skip;
- no match: legacy global policy, subject to the selected retrieval budget.

Routing must not use a path, tag, or model score as a substitute for trust
state or authority.

## 11. Domain-Specific Traversal

The following matrix is the minimum traversal policy. Each stage is bounded by
the request budget and `SearchScope`.

| Domain | Traversal |
|---|---|
| Project State | PSE → Tasks → Decisions → semantic entities → event/history → docs fallback |
| Decisions | exact/current decisions → supersession chain → semantic match → raw provenance |
| Tasks | active/ready/blocked canonical TaskService → related decisions → semantic context |
| Code | path/symbol/FTS → relations → dense → rerank |
| Infrastructure | structured/config exact → FTS → relations → semantic |
| Research | FTS + dense → RRF → rerank |
| Agent Conversations | session metadata → extracted entities/summary → relevant turns → raw transcript fallback |
| Logs | time range → structured/lexical; dense normally disabled |
| Archive (lifecycle view) | cheap FTS first; dense only on escalation |
| Quarantine (trust view) | excluded by default; diagnostic-only |
| Governance | current state → roadmap → protocol → latest handoff → GitHub live facts |

Traversal must call existing authorities and source-read boundaries. It must
not directly read a caller-supplied task, decision, or project-state object as
if it were canonical.

### Stage naming

The planning contracts use these stable stage names:

| Planning stage | Existing/runtime meaning |
|---|---|
| `semantic` | Local dense semantic retrieval using the existing BGE-M3-capable backend |
| `graph_assisted` | Existing graph-assisted ranking/traversal mode; future reviewed traversal remains bounded |
| `tf` | Existing local sparse TF-vector retrieval stage |
| `rerank` | Local cross-encoder reranking stage; the existing complete mode is `reranked` |
| `rrf` | Candidate fusion stage, including existing sparse RRF |
| `temporal` | Current/historical/as-of lifecycle filtering and future pushed-down temporal scope |

`dense` and `graph` may describe implementation components in prose, but they
are not alternate public names for the planning stages above. `Domain Policy
v2` must use the stable names and mark expensive stages as explicit escalation
when the selected budget does not allow them.

## 12. Retrieval Budgets

Every request resolves to one of three planning profiles.

| Profile | Planned stages | Default use |
|---|---|---|
| `FAST` | PSE/state, metadata, FTS/BM25, TF, temporal filtering, cheap noise gate, materialized views | Low latency, bootstrap, normal exact/state queries; no model load required |
| `BALANCED` | `FAST` plus selected-domain dense and a small reranker pool | Default target for a normal AI query |
| `DEEP` | Multi-domain FTS, semantic, graph-assisted, temporal, contradiction-aware retrieval, rerank, raw fallback | Explicit deep request, complex cross-domain intent, or low confidence after `BALANCED` |

Budgets are caps, not suggestions. They bound candidate count, reranker pool,
tokens, graph hops, domains, raw fallback, and index work. `DEEP` is not a
silent default. Numeric FAST/BALANCED/DEEP defaults are planning hypotheses,
not eternal product constants.

The effective profile is selected and enforced at the server/application
boundary through four separate layers:

```text
structural absolute safety ceiling
        ↓
ResourceProfile calibrated default
        ↓
domain policy cap
        ↓
caller hint (lower-only)
```

For every bounded dimension, the effective limit is the minimum of the
applicable layers. Caller hints may only lower a cap and may never raise it.
Profile flags override caller hints and domain-policy requests. A domain stage
that is not allowed by the effective profile must be rejected or represented as
explicit escalation, never silently clamped or run anyway. FAST/BALANCED/DEEP
defaults must be calibrated in the Phase 5 shadow benchmark for the declared
resource profile.

Each effective `RetrievalBudget` carries its ordered allowed stages, model-load
policy, candidate/token/domain/hop caps, and dense/rerank/graph/raw flags. The
structural contract and the cost policy are admission guards; they are not
caller-controlled permission to exceed the server-selected profile.

## 12A. Evidence ordering and authority-sensitive retrieval

For `project_state`, `decision`, `task`, and `governance` intents, retrieval
must not collapse authority and semantic relevance into one opaque score. The
planning order is:

```text
access policy
        ↓
authority policy
        ↓
temporal validity
        ↓
supersession
        ↓
contradiction state
        ↓
semantic relevance
        ↓
reranking
        ↓
diversity / token packing
```

Canonical authority may therefore outrank a more semantically similar raw chat.
Each stage must remain explainable in the future `ContextPack`; cosine, RRF, or
reranker scores cannot erase an authority or supersession decision. The v2
`EvidenceOrderingPolicy` remains planning-only.

## 13. Retrieval Escalation

The planner escalates only when the current stage cannot meet the request's
confidence or coverage condition:

```text
cheap exact/state lookup
        ↓
sufficient confidence? ── YES → return bounded result
        │ NO
        ↓
FTS / sparse
        ↓
sufficient? ──────────── YES → return bounded result
        │ NO
        ↓
selected-domain dense
        ↓
ambiguous? ────────────── NO → return bounded result
        │ YES
        ↓
local rerank
        ↓
optional graph/deep expansion or raw fallback
```

The escalation reason, stages attempted, skipped stages, model loads, token
cost, and index work are part of `ContextPack`. A failed optional neural stage
must be explicit and fail closed with the existing retrieval contract; it must
not masquerade as a successful dense result.

## 14. Search Scope Pushdown

Scope pushdown is a mandatory Phase 5 scalability requirement. The current
anti-pattern is:

```text
global candidate generation → over-fetch → domain filtering
```

The target is:

```text
Domain/Scope Router
        ↓
SearchScope
        ↓
FTS scope / TF scope / Dense scope / Graph scope
        ↓
candidate generation only inside allowed scope
```

Planning contract:

```text
SearchScope:
  domain_ids
  path_prefixes
  source_types
  trust_states
  temporal_boundary
  project_ids
  include_archived
  include_quarantine
```

The scope must enter SQL/projection selection, sparse candidate generation,
dense matrix construction, graph traversal, and raw fallback. Post-filtering
may remain as a defense-in-depth check, but it is not sufficient for the
acceptance gate.

## 15. ContextPack Contract

Future retrieval output is a bounded `ContextPack`, not an untyped
`list[SearchResult]`. The active machine-readable planning contract is
`artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json`.
The v1 schema remains retained historical evidence and is not the future
implementation contract.

Minimum pack fields:

```text
request_id
query
intent
budget_class
domains
retrieval_plan
items
excluded
budget
explainability
retrieval_status
fallback_reason
policy_revision
generation_revision
access_policy
implementation_status
```

Each `ContextItem` carries:

```text
source_id
source_type
authority
trust_state
domain
domains
score
retrieval_stage
provenance
freshness
contradiction_state
noise_state
token_cost
excerpt
content_kind
redaction_status
```

The pack is:

- bounded by token and item budgets;
- deterministic when inputs, source revisions, model revisions, and policies
  are deterministic;
- explainable by domain, stage, score, exclusion, and cost;
- provenance- and authority-aware;
- safe to pass to an agent as untrusted data;
- free of implicit mutation side effects.

The pack must expose source, policy, generation, retrieval status, and fallback
revisions sufficiently for a future caller to detect stale or degraded context.
`excerpt` is bounded; `content_kind=reference` is allowed when content cannot be
released. Raw or quarantined material requires a privileged, explicitly
authorized read boundary. `access_policy` is server-derived and binds the
authorization-boundary origin, actor, capability ID, expiry, raw/quarantine
mode, and mandatory redaction; privileged access also requires an approval
reference. The normal ContextPack must not include secrets, raw credentials, or
instructions that bypass application-level authorization.

## 16. Noise Taxonomy

Noise recognition is a first-class policy subsystem. It is not source deletion.

### Layer 1 — deterministic cheap noise, before embeddings

```text
empty
near-empty
heartbeat
tool boilerplate
repeated system prompt
duplicate event
status spam
temporary progress
known template
generated catalog/index
```

### Layer 2 — semantic noise

```text
near duplicate
low information density
repeated paraphrase
superseded fact
stale fact
semantic duplicate
```

### Layer 3 — unsafe / quarantine

```text
prompt injection
secret leakage
authority spoof
corrupted provenance
untrusted instruction escalation
```

The assessment must distinguish evidence from instruction. Retrieved or
captured text is never executable merely because a model labels it useful.

## 17. Raw Capture / Promotion

Future Phase 6 capture follows this order:

```text
adapter
  ↓
raw capture
  ↓
append-only storage
  ↓
session segmentation
  ↓
cheap noise classification
  ↓
semantic compilation
  ↓
domain membership
  ↓
MemoryDisposition
  ↓
IndexWorkQueue
```

Capture must be lossless with respect to the declared privacy/retention
contract. Redaction and retention are policy transformations with evidence;
they are not permission to silently drop source events.

### Retention, sensitivity, and deletion evidence

Retention is not one indefinite payload switch. Future planning uses separate
`RetentionClass`, `SensitivityClass`, and `PayloadRetentionPolicy` values. An
append-only audit metadata record may remain after an eligible payload expires
or is deleted; audit metadata retention is not indefinite payload retention.

```text
payload eligibility decision
        ↓
bounded payload action
        ↓
TombstoneReceipt (`receipt_kind=DELETION` for deletion)
        ↓
retained, secret-free audit metadata
```

Noise classification alone never authorizes source deletion. Any deletion or
expiry must use an explicit policy revision, preserve a bounded digest-bound
receipt, and respect sensitivity/authorization controls.

### Bitemporal evidence

Applicable evidence distinguishes:

```text
observed_at  — when the fact was observed
recorded_at  — when POWER recorded it
valid_from   — optional beginning of a meaningful validity interval
valid_to     — optional end of a meaningful validity interval
```

`valid_from`/`valid_to` are omitted when a fact has no meaningful validity
interval. Delayed capture and correction use the observation/recording pair and
an explicit correction/supersession reference; they must not overwrite the
original observation as if it had been recorded on time. The v2 bitemporal
contract is planning-only and does not add fields to current runtime models.

Promotion path:

```text
RAW
  ↓
SESSION LOCAL
  ↓
WORKING MEMORY
  ↓
DURABLE CANDIDATE
  ↓
VERIFIED / CANONICAL
```

Promotion considers meaningfulness, repetition, authority, provenance, domain,
freshness, user intent, project relevance, and contradiction state. No adapter
may promote every message, embed every message, or write a canonical durable
note without the relevant governed boundary.

Required capture controls include backpressure, idempotent session identity,
adapter isolation, restart recovery, privacy boundary enforcement, bounded
queues, and explicit retention/forgetting behavior. A raw-transcript fallback
is an explicit DEEP-only operation: it requires a separate capability,
mandatory redaction, sensitivity/retention checks, and an opaque local evidence
reference. Governance "GitHub live facts" are control-plane evidence, not an
arbitrary URL-fetch instruction; any future external source must use the
existing egress/allowlist/SSRF boundary.

## 18. MemoryDisposition

The future capture/semantic boundary returns one explicit disposition:

```text
NOOP
RAW_ONLY
SESSION
WORKING
DURABLE_PROPOSAL
CORRECTION_PROPOSAL
QUARANTINE
ARCHIVE_CANDIDATE
```

`MemoryDisposition` is a recommendation or governed workflow state, not an
authorization token. `DURABLE_PROPOSAL` and `CORRECTION_PROPOSAL` must enter
the existing proposal/apply path or a formally approved extension of it.
The future approval contract must bind actor identity, target/source revision,
before/after digests, evidence references, expiry, rollback, and replay-safe
receipt. Until that contract is closed, a caller-supplied `approved=true` is
not sufficient human authority for semantic or authority repair.

## 19. AI Repair Classes

AI-assisted repair is split into three classes.

### Class A — deterministic safe derived repair

Examples: index rebuild, cache repair, projection regeneration, and known
formatting/frontmatter normalization. A later policy may allow selected
auto-repair only with hash preconditions, rollback, and a receipt.

### Class B — semantic repair

Examples: merging duplicate knowledge, marking stale, superseding a fact,
resolving contradiction, rewriting a summary, or archiving durable knowledge.

Required workflow:

```text
detect → evidence → proposal → approval policy → apply → verify → receipt
```

### Class C — authority/security repair

Examples: PSE lifecycle, Task authority, Decision authority, approval,
security policy, and verified promotion. These are never model-autonomous.

The model may classify, rank, extract a proposal, prepare a repair, or explain.
It may not grant itself authority, mark its own output canonical, approve a
Decision, complete Task authority, advance PSE lifecycle, or bypass governed
mutation.

## 20. MemoryActionPolicy

The future deterministic policy component is `MemoryActionPolicy` (an
implementation may use the internal name `NextActionPlanner` only if it does
not imply an autonomous LLM agent).

Inputs:

```text
signal
state
domain
trust
confidence
index status
resource budget
```

Possible outputs:

```text
NOOP
INDEX_FTS
QUEUE_DENSE
REFRESH_DOMAIN
RUN_DENSE
RUN_RERANK
PROMOTE_TO_WORKING
PROPOSE_DURABLE_MEMORY
PROPOSE_CORRECTION
REQUEST_APPROVAL
RUN_MAINTENANCE
REBUILD_PROJECTION
DEFER
QUARANTINE
QUEUE_NEW_REVISION
```

The policy chooses a next bounded action and is server-derived from the stated
inputs. It does not perform a mutation, act as an authority, or turn a
low-confidence signal into a canonical write.

## 21. Incremental Dense Index v2

The dense index must be treated as a derived projection with two identities.

### Global index identity

```text
schema_version
embedding_model_revision
embedding_dimension
chunker_revision
dense_schema_revision
```

### Per-source / per-chunk validity

```text
source_content_hash
chunk_id
chunk_revision
embedding_revision
indexed_at
```

An ordinary source change follows:

```text
changed note
  ↓
new source hash
  ↓
changed chunks only
  ↓
dirty chunk set
  ↓
IndexWorkQueue
```

It must not follow `one source changed → entire dense index stale`.

Full dense rebuild is allowed only for:

- embedding model revision change;
- embedding dimension change;
- chunker schema/revision change;
- dense index schema change;
- explicit migration or force-rebuild request;
- proven corruption requiring full reconstruction.

An accepted FTS-only generation may report dense coverage as pending; it must
not silently present stale dense rows as current. The future implementation
must choose a partial-dense validity model instead of relying on global manifest
clearing as the normal write path.

## 22. IndexWorkQueue

Future queue item contract:

```text
IndexWorkItem:
  source_id
  source_revision
  domain_ids
  chunk_ids
  priority
  reason
  embedding_model_revision
  estimated_work
  created_at
  queue_state
  retry_count
  idempotency_key
  chunk_revision (when the item represents a single chunk revision)
  last_error (bounded and redacted)
  deferred_until (when deferred)
  lease_id / lease_expires_at (when running)
```

Queue items are idempotent by source revision, chunk revision, model revision,
and reason. They must survive restart, expose retry/defer state, and never
cause unbounded fan-out. Queue processing respects CPU/RAM budgets and uses the
existing batch/low-RAM controls before any future optimization. An error is
diagnostic data, not an instruction, and must be redacted before a context pack
or receipt exposes it. A failed item must carry a bounded error; after the
retry policy is exhausted it enters `dead_letter` and requires explicit review
before requeue.

The retry policy is deliberately small and bounded: automatic retries use
exponential/backoff where applicable, total requeues and manual requeues have
separate finite caps, dead-letter follows exhaustion, and explicit review plus
a source-revision check is required before requeue. High retry counts are not
safe defaults and retry storms are a gate failure. Phase 5 may prove a minimum
dirty-set/index-validity substrate; persistent `IndexWorkQueue` is the primary
Phase 6 owner unless a Phase 5 benchmark and ADR prove earlier need.

## 23. HOT / WARM / COLD

| Tier | Content | Dense policy |
|---|---|---|
| HOT | active projects, active decisions, current work, recent important agent sessions, frequently retrieved knowledge | eager / high priority |
| WARM | areas, resources, recently used references | batched / deferred |
| COLD | archive, old logs, old raw conversations | FTS first; dense only on demand or escalation |

Tier is an index-cost priority, not an authority label. An archived or cold
item can remain canonical evidence; a hot item can remain merely proposed.

## 24. Index Cost Model

Before any expensive operation, the planner produces an `IndexCostEstimate`:

```text
affected_sources
affected_chunks
model_required
priority
estimated_memory_class
estimated_cpu_class
full_rebuild
reason
```

Policy outputs are:

```text
RUN_NOW
QUEUE
DEFER
REQUIRE_EXPLICIT_DEEP_SYNC
QUEUE_NEW_REVISION
```

The runtime must reject any `consumed_tokens > max_tokens` condition and any
aggregate item/byte/queue/work overflow; it must not clamp unsafe values or
silently downgrade the result. Query-time ContextPack compilation has
`index_work_triggered=false`; index work is returned to the separate policy and
queue boundary.

Minimum acceptance metrics:

```text
fts_sync_time
dense_queue_length
dirty_chunks
embedded_chunks_per_run
reembed_amplification
index_disk_size
model_load_time
peak_ram
cpu_time
query_p50
query_p95
dense_p50
dense_p95
reranker_p50
reranker_p95
dense_escalation_ratio
rerank_escalation_ratio
fts_only_resolution_ratio
```

Definition:

```text
reembed_amplification = embedded_chunks / logically_changed_chunks
```

For a note with four changed chunks, `12000 / 4` is a failed ordinary edit;
approximately `4 / 4` is the target. Full migration rebuilds are reported
separately and are not normalized into ordinary edit performance.

## 25. Shadow Mode

Before changing the default retrieval result:

```text
legacy retrieval
       │
       ├─ result served
       │
       └─ new planner runs in shadow
                    ↓
                 compare
```

Shadow mode records, without changing the served result:

```text
Recall@K
MRR
MAP
nDCG
context precision
latency
dense usage
rerank usage
index cost
```

The new planner becomes default only after a versioned acceptance report shows
legacy quality non-regression, bounded latency/resource cost, deterministic
pack behavior, and safe fallback. Shadow computation itself remains bounded
and must not trigger unplanned global indexing.

## 26. Phase 5 Work Breakdown

Phase number remains unchanged. The refined read-first order is:

```text
Pre-Phase-5 Foundation Hardening
        ↓
Phase 5A — Runtime contracts v2 + frozen evaluation corpus
        ↓
Phase 5B — Deterministic multi-domain router
        ↓
Phase 5C — Search scope pushdown
        ↓
Phase 5D — RetrievalPlanner + ContextPack read-only vertical slice
        ↓
Phase 5E — Shadow benchmark / legacy comparison
        ↓
Phase 5F — Incremental dense validity / dirty-set behavior
        ↓
Phase 5G — Small MCP read/explainability surfaces
        ↓
Phase 5H — Phase closure / default decision
```

Phase 5 is currently `BLOCKED / NOT STARTED`; every item below is
`PLANNED / NOT IMPLEMENTED`.

| Gate | Planned scope | Required evidence before advancing |
|---|---|---|
| Foundation | Explicit mutation authority, principal/session semantics, retrieval boundary, failure receipts, and actual deadline/budget behavior | `pre-phase5-foundation-hardening-gate.md`, source-bound security tests, PSE/Task/Decision/crash regression, protected admission |
| 5A — Runtime contracts v2 + frozen evaluation corpus | Typed v2 retention, bitemporal, ordering, resource, budget, retry, and evaluation boundaries | v2 schema tests, v1 compatibility evidence, digests/provenance, development/holdout isolation, no source/mutation changes outside the bounded runtime PR |
| 5B — Deterministic multi-domain router | Backward-compatible policy evolution, `DomainMatch[]`, traversal stages, authority/noise/index policy | v1 compatibility, routing benchmark, explainable reasons, deterministic tie handling, no domain/trust conflation |
| 5C — Search scope pushdown | Pass `SearchScope` into FTS, TF, dense, graph, temporal, archive, and quarantine selection | Scope enters candidate generation; privileged override tests; recall/cost evidence; post-filter-only implementation fails |
| 5D — RetrievalPlanner + ContextPack | Read-only authority-aware planner, noise gate, bounded escalation, provenance, redaction, and pack assembly | Determinism, authority-vs-relevance, bounded bytes/tokens, no writes, archive/quarantine policy, direct/MCP parity |
| 5E — Shadow benchmark / legacy comparison | Run the planner in shadow while legacy retrieval remains served | Frozen development/holdout corpus, no holdout tuning, quality/resource/authority non-regression, rollback receipt |
| 5F — Incremental dense validity / dirty-set behavior | Per-source/per-chunk validity and minimum dirty-set substrate; persistent queue only with evidence/ADR | Ordinary edit avoids vault-wide re-embedding; crash/restart, exact coverage, model migration, low-RAM evidence |
| 5G — Small MCP read/explainability surfaces | `compile_context`, `explain_context`, `retrieval_plan`, `index_status`, and `index_cost` or a reviewed bounded combination | ApplicationService boundary, read-only annotations, auth/path checks, no new network plane, tool-count discipline |
| 5H — Phase closure / default decision | Acceptance report, rollback/default decision, and signed closure | Shadow PASS, holdout integrity, quality non-regression, resource bounds, remote CI, signed closure evidence |

The Controlled Dependency Refresh is already closed at final integration in the
current governance snapshot. No Foundation or 5A–5H gate authorizes Actions
#396, capture, migration, a release, or a version bump by itself.

## 27. Phase 6 Work Breakdown

Phase 6 is **Agent Capture & Integrations**, `NOT STARTED`, and is not
authorized by this plan. It is the primary owner for persistent continuous
capture/index work, including `IndexWorkQueue`.

Target sequence:

```text
adapter
  ↓
raw capture
  ↓
append-only storage
  ↓
session segmentation
  ↓
cheap noise classification
  ↓
ProjectSemanticCompiler
  ↓
domain membership
  ↓
MemoryDisposition
  ↓
IndexWorkQueue
```

Required architecture: backpressure, bounded queues, idempotent session
identity, adapter isolation, restart recovery, privacy/redaction, retention and
sensitivity classes, bitemporal metadata, `MemoryDisposition`, promotion
proposal, and no automatic canonical promotion. Capture adapters must call
existing project ingestion and governed memory boundaries rather than inventing
a second event store. Every message is not canonical memory and every message
is not an embedding.

## 28. Phase 7 Work Breakdown

Phase 7 is `NOT STARTED`. A Context Broker façade is optional, not a mandatory
implementation milestone.

The optional target is a read-oriented **Context Broker** over existing
authorities, created only if multiple real consumers demonstrate orchestration
value beyond `ContextPackCompiler`, `ApplicationService`, and materialized
views:

```text
Context Broker
      ↓
Working Memory / Durable Knowledge / Project PSE State / Conversation Memory
      ↓
Materialized Views
      ↓
ContextPack
```

Planned views:

```text
current project summary
open issues
active decisions
ready/blocked tasks
recent changes
hot knowledge
recent relevant sessions
contradictions
pending repairs
```

Phase 7 must resolve existing `.power/tasks` versus legacy
`.power/work-packets` control-plane drift through a separate contract/ADR. It
must reuse `ApplicationService`, `ProjectStateService`, `source_service`, and
existing Web/MCP boundaries. The broker and views are rebuildable projections,
not a new database of truth.

## 29. Phase 8 Work Breakdown

Phase 8 is `NOT STARTED`.

Planned scope:

- `IndexCostController`, queue backpressure, low-RAM and CPU bounds;
- crash recovery for capture, indexing, views, and repair;
- privacy, retention, forgetting, and raw evidence controls;
- prompt-injection quarantine and authority-spoof resistance;
- repair safety, rollback, idempotency, and receipt verification;
- load, soak, concurrency, cache, and index recovery tests;
- no silent fallback and no unbounded resource amplification.

Security requirements include validated Pydantic/stdlib boundaries, path
containment and symlink checks, no shell execution from model output, safe
remote endpoint policy for any future external source, SSRF defenses, bounded
MCP input, and least-privilege read/write separation. A new remote broker or
write-capable network service requires a separate threat model and ADR.

## 30. Phase 9 Work Breakdown

Phase 9 is `NOT STARTED`.

The release order is binding:

```text
architecture complete
  ↓
shadow mode PASS
  ↓
small real dataset
  ↓
soak
  ↓
real vault migration
  ↓
bulk capture
  ↓
full benchmark
  ↓
upgrade validation
  ↓
RC
  ↓
POWER 3.8.0 decision
```

No step may be skipped by declaring a planning document, schema, or benchmark
placeholder to be implementation evidence.

## 31. Acceptance Gates

The detailed gate matrix is versioned in
`artifacts/project-state/planning/phase5-9-acceptance-gates.md`. The minimum
blocking criteria are:

| Gate | Objective | Required evidence | Metric | PASS condition | FAIL condition | Blocks |
|---|---|---|---|---|---|---|
| Retrieval | Domain-aware quality without legacy regression | Routing, multi-domain, scope-pushdown, ContextPack and shadow reports | Recall@K, MRR/MAP/nDCG, context precision, p50/p95 | All declared thresholds and legacy non-regression pass | Post-filter-only scope, missing domains, or quality regression | Phase 5 default switch and Phase 6 |
| Index | Local, recoverable, bounded work | Dirty-set sequence, crash/restart, exact coverage, model migration, low-RAM receipts | Re-embed amplification, queue length, peak RAM, CPU time | Ordinary edit does not globally re-embed; recovery is deterministic | Silent incomplete dense index, global normal rebuild, or unbounded queue | Phase 5 closure and Phase 6 capture |
| Noise | Suppress noise without losing evidence | Duplicate/false-noise/injection/quarantine tests and raw retention proof | False-noise rate, quarantine rate, retained evidence count | Canonical evidence is never destructively discarded; unsafe input fails closed | Source deletion, authority spoof, or unbounded false suppression | Capture and context default |
| Repair | No unapproved semantic mutation | Detect→proposal→approval→apply→verify→receipt replay and rollback tests | Idempotent apply, rollback success, receipt verification | Semantic/authority changes require governed approval | Model or caller boolean directly changes canonical state | Phase 6/7 repair paths |
| Capture | Safe ingestion at scale | Lossless raw capture, backpressure, restart, idempotency, privacy and adapter-isolation evidence | Queue bound, duplicate ingest count, recovery time, retention compliance | Capture remains bounded, private, restart-safe, and non-canonical by default | Every message promoted/embedded, dropped raw evidence, or duplicate ingest | Bulk capture and Phase 9 migration |
| Governance | Correct phase and authority boundaries | Fresh GitHub state, signed commits, exact PR/tree/check evidence, scope audit | Branch/base/head/tree/parent tuple | Protected normal merge and declared scope are exact | Bypass, stale blocker, stale SHA, or source/runtime diff | Any phase transition or release |

## 32. Migration Strategy

Migration is staged and reversible:

1. Publish and protect the contracts and architecture plan.
2. Finish the independent dependency admission and final integration gates.
3. Implement Phase 5 contracts and read-only planner behind feature/shadow
   control.
4. Validate on a small representative dataset; preserve the original source
   and create manifests for all derived projections.
5. Run shadow retrieval and compare quality, latency, token, and index costs.
6. Enable bounded materialized views and working-memory projections.
7. Add one capture adapter at a time with idempotency, privacy, and restart
   evidence.
8. Migrate the real vault only after soak and rollback gates pass.
9. Enable bulk capture only after migration and full benchmark evidence.

Existing sources are never replaced by an index migration. Every migrated
source has a content hash, source revision, provenance, domain membership,
trust/lifecycle disposition, and a rebuildable projection record. Full dense
rebuilds are explicit migrations, not ordinary note-write behavior.

## 33. Explicit Anti-Goals

POWER 3.8 must not:

- create a new search engine beside `search_vault` executors;
- create a second semantic compiler beside the Phase 3 Project Semantic
  Compiler;
- create a new canonical memory database, domain registry, task store,
  decision authority, or PSE authority;
- make Qdrant, Milvus, or another vector database mandatory;
- scan all dense chunks and apply domain filtering only after candidate
  generation once scope pushdown is implemented;
- make global dense rebuild the normal source-edit path;
- treat a model extraction, retrieved passage, or caller boolean as canonical
  authority;
- delete raw source because it is classified as noise;
- automatically embed or canonically promote every captured message;
- mix semantic domain with trust/lifecycle state;
- mix session-local, working, durable-candidate, and canonical memory;
- call a context compiler during every query to create new semantic entities;
- add a generic `SemanticCompiler` or `ContextCompiler` class that collides
  with the established names;
- expose a new MCP network plane without an independent threat model and
  transport decision;
- hide model failure behind an unlabeled FTS or empty-result fallback;
- call planning artifacts phase evidence or implementation output;
- change public version, tag, release, or Actions #396 in this planning gate.

## 34. Risks

| Risk | Impact | Mitigation / owner phase |
|---|---|---|
| Scope remains post-filtered | High latency and under-retrieval in multi-domain vaults | Phase 5C SQL/projection pushdown and recall gate |
| Global manifest invalidation | Full re-embedding, RAM/CPU amplification | Phase 5D dirty-set and per-chunk validity |
| Model identity drift | Semantically incompatible vectors appear valid | Global model revision, dimension, chunker identity and migration gate |
| Context authority escalation | Agent acts on untrusted or stale evidence | Orthogonal trust axis, provenance, read-only pack, application authorization |
| Raw capture flood | Disk/CPU exhaustion and privacy exposure | Phase 6 backpressure, TTL, redaction, queue budgets, adapter isolation |
| Prompt injection in retrieval/capture | Unauthorized tool or policy actions | Treat all text/model output as data, quarantine, no shell/path interpolation |
| Duplicate semantic systems | Conflicting state and maintenance paths | Reuse-first inventory and explicit compiler/broker boundaries |
| Incomplete repair receipt | Irreversible or unreviewable mutation | Class-based repair workflow, idempotency, rollback, durable receipt |
| Legacy path drift | Agent sees stale or incomplete views | Phase 7 path ADR and direct parity tests |
| Optional neural asset failure | Misleading quality or unpredictable cost | Fail-closed readiness, explicit fallback reason, FAST profile |
| Vector backend premature adoption | New operational and supply-chain surface | Scope/dirty-set benchmark first; separate ADR required |
| Main advances during planning | Stale base or contradictory governance | Rebase/merge normally, refresh tuple, rerun docs/schema gates |

## 35. Open Architectural Decisions

These are intentionally open; the plan does not fabricate answers.

1. **Domain v2 precedence:** how explicit domain membership, path, tags, note
   type, and model hints combine when they disagree.
2. **ContextPack digest:** exact canonical serialization and whether the digest
   covers model/provider identity in addition to source and policy revisions.
3. **Partial dense validity:** storage shape for per-chunk pending/stale state
   while preserving an active usable generation.
4. **Chunk identity migration:** path-inclusive identity versus a mapping table
   for identical content in different sources.
5. **Temporal source history:** whether future capture retains immutable source
   revisions or only provenance references to raw evidence.
6. **Semantic entity persistence:** how Phase 3 candidates become durable
   projections without duplicating PSE RAID/task/decision authority.
7. **Human approval proof:** identity and receipt semantics beyond a caller
   supplied `approved=true` flag.
8. **Materialized view ownership:** exact resolution of `.power/tasks` and
   `.power/work-packets` before Phase 7 Web/control-plane work.
9. **Thresholds:** numerical recall, latency, RAM, queue, false-noise, and
   re-embedding thresholds for each supported host profile.
10. **ANN/vector backend:** whether real benchmark evidence justifies a future
    backend protocol after scope pushdown and incremental indexing.

Each decision requires a versioned contract or ADR before implementation uses
it. Until then, future code must select the conservative, bounded behavior and
label it as provisional.

## 36. Cross-links

### Planning and governance

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Latest final-integration handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-09T065950Z_controlled-dependency-refresh_final-integration.md)

### Machine-readable planning contracts

- [Context/retrieval contracts v2](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json)
- [Retrieval evaluation manifest v1](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/retrieval-eval-v1.schema.json)
- [Pre-Phase-5 Foundation Hardening gate](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md)
- [Retained v1 context contract](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/context-retrieval-contracts-v1.schema.json)
- [Index cost policy](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/index-cost-policy-v1.json)
- [Domain Policy v2 example](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/domain-policy-v2.example.yaml)
- [Phase 5–9 acceptance gates](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/phase5-9-acceptance-gates.md)

### Existing authority and evidence

- [Phase 3 compiler contract](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-3/compiler_contract.md)
- [Phase 4 report](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/phase-4/PHASE_4_REPORT.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Threat model](../threat-model.md)

The final implementation must begin by reading this plan, the planning
contracts, the current state, the roadmap, the development protocol, and the
latest handoff from live `main`. It must then independently revalidate GitHub
state and the next execution gate before writing runtime code.
