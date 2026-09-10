# Phase 5A Runtime Contract Mapping

This matrix is implementation evidence for the independent runtime identity
`power.context-runtime.v2`. Planning schemas remain historical/governance data;
the runtime package does not read `docs/plans/` or `artifacts/project-state/planning/`
to obtain operational values.

## Retained v1 structural contracts

| Planning source | Runtime v2 type | Mapping / tightening | Deferred behavior owner | Test surface |
|---|---|---|---|---|
| v1 `QueryIntent` | `QueryIntent` | `intent` and `budget_class` are closed enums; optional fields are omission-or-value, never explicit null | 5B intent/routing behavior | runtime contract tests |
| v1 `RetrievalBudget` | `RetrievalBudget` | `budget_class` is the Python-safe name for planning `class`; structural class caps and stage/flag compatibility are validation only, not product defaults | 5B–5E policy/planner | runtime contract tests |
| v1 `SearchScope` | `SearchScope` | Domain/path/source/trust/temporal/project dimensions are bounded; safe relative prefixes are data only | 5C scope pushdown | runtime contract tests |
| v1 `DomainMatch` | `DomainMatch` | Bounded finite score and bounded unique reasons; no authority inference | 5B router | runtime contract tests |
| v1 `RetrievalStage` | `RetrievalStage` enum | Closed vocabulary; envelope binds the scalar payload exactly | 5B–5D stage selection | discriminator tests |
| v1 `RetrievalPlan` | `RetrievalPlan` | Planned/attempted/skipped sets are bounded and partition-consistent; values are supplied data, not planner behavior | 5D planner | runtime contract tests |
| v1 `NoiseAssessment` | `NoiseAssessment` | Closed dispositions; unsafe quarantine requires `QUARANTINED`; source preservation is literal true | 5D noise gate | noise tests |
| v1 `ContextItem` | `ContextItem` | Domain membership, trust↔authority matrix, provenance basis, redaction and bounded cost are pure validation | 5D ContextPack compiler | authority/noise tests |
| v1 `ContextPack` | `ContextPack` | Read-only output type with bounded items and `index_work_triggered=false`; no compiler or search call | 5D ContextPack compiler | read-only contract tests |
| v1 `IndexWorkItem` | `IndexWorkItem` | DTO only; bounded queue-state/lease fields; no queue, worker, scheduler, or retry execution | Phase 6 queue owner | DTO cross-field tests |
| v1 `IndexCostEstimate` | `IndexCostEstimate` | Bounded non-negative cost/impact fields | Phase 5F/6 index-cost policy | DTO bounds tests |
| v1 `MemoryDisposition` | `MemoryDisposition` enum | Closed disposition vocabulary; it is not mutation authority | Phase 6 capture policy | enum tests |
| v1 `MemoryAction` | `MemoryActionDecision` (`MemoryAction` compatibility alias) | Policy-engine factory is required; forged caller payloads fail; `origin=policy_engine` and `server_derived=true` are typed invariants | Governed future policy/apply boundary | server-derived tests |
| v1 `TemporalBoundary` | `TemporalBoundary` | Date-only boundary and historical flag are bounded data | 5C temporal pushdown | scope tests |
| v1 `Provenance` | `Provenance` | Safe source references, bounded revisions/event IDs, explicit authority basis | 5D provenance assembly | source-reference tests |
| v1 `ExcludedItem` | `ExcludedItem` | Bounded source ID and reason | 5D explainability | pack tests |
| v1 `ContextBudget` | `ContextBudget` | `consumed_tokens <= max_tokens`, literal `index_work_triggered=false` and `budget_satisfied=true` | 5D token packing | budget tests |
| v1 `Explainability` | `Explainability` | Bounded summary/decisions/revisions | 5D explainability | pack tests |
| v1 `AccessPolicy` | `AccessPolicy` | Server-bound origin, mandatory redaction, approval required for privileged raw/quarantine access | Foundation/5D authorization boundary | access tests |
| v1 `Freshness`, `ContradictionState`, `NoiseState` | closed enums | Lifecycle/status axes remain separate from domain and authority | 5B–5E behavior | ContextItem tests |

## Canonical v2 policy contracts

| Planning source | Runtime v2 type | Mapping / tightening | Deferred behavior owner | Test surface |
|---|---|---|---|---|
| v2 `RetentionClass` | `RetentionClass` + `RetentionClassContract` | Closed enum plus strict value DTO; audit metadata remains distinct from payload | Phase 6 retention | policy tests |
| v2 `SensitivityClass` | `SensitivityClass` + `SensitivityClassContract` | Closed sensitivity vocabulary; no payload disclosure behavior | Phase 6 privacy | policy tests |
| v2 `PayloadRetentionPolicy` | `PayloadRetentionPolicy` | Audit retention and explicit source-delete policy are literals; quarantine cannot alone authorize delete | Phase 6 retention engine | retention tests |
| v2 `TombstoneReceipt` | `TombstoneReceipt` | Opaque references/digests, aware UTC timestamps, explicit tombstone/deletion action rules; no deletion engine | Phase 6 governed deletion | receipt tests |
| v2 `BitemporalEvidence` | `BitemporalEvidence` | Aware UTC observed/recorded timestamps; optional validity interval; `valid_to >= valid_from`; no invented observed/recorded ordering | Phase 5C/6 temporal behavior | datetime tests |
| v2 `EvidenceOrderingPolicy` | `EvidenceOrderingPolicy` | Exact explainable eight-stage order and six-level authority rank; no score collapse | 5D/5E ranking behavior | ordering tests |
| v2 `ResourceProfile` | `ResourceProfile` | Host-neutral profile classes; calibration explicitly deferred to shadow benchmark | 5E benchmark | resource tests |
| v2 `HostCapabilityProfile` | `HostCapabilityProfile` | Deployment/benchmark references are opaque and bounded; no WS/PRXMX policy constants | deployment evidence | host DTO tests |
| v2 `RetrievalBudgetPolicy` | `RetrievalBudgetPolicy` | Structural/resource/domain/caller layers; caller hint is lower-only; resolver is pure and does not read environment | 5B–5E policy calibration | budget resolver tests |
| v2 `RetryPolicy` | `RetryPolicy` + `BackoffPolicy` | Small bounded caps, backoff ordering, dead-letter/review/revision literals; no worker/retry loop | Phase 6 queue | retry tests |
| v2 `EvaluationCorpusManifest` and `retrieval-eval-v1` | `EvaluationCorpusManifest` | Runtime identity omits planning-only metadata; digests, split policy and provenance are typed | 5E quality evaluation | corpus verifier tests |

## Envelope and serialization

`RuntimeContractEnvelope` exposes `schema_version=power.context-runtime.v2`, a
closed `contract` discriminator, and an exact payload type. It does not expose
planning fields such as `planning_only`, `implementation_status`, or
`phase_status` as mandatory caller input. Canonical bytes use the existing
POWER compact UTF-8 JSON helper after enum/datetime normalization; SHA-256 is
the only Phase 5A digest algorithm.

No row in this mapping creates retrieval behavior, writes memory, starts index
work, loads a model, accesses a network, or dereferences an untrusted source
reference.
