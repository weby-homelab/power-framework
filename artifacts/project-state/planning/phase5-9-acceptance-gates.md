# POWER 3.8 Phase 5–9 Acceptance Gates

> **Status:** APPROVED PLANNING DIRECTION
>
> **Publication class:** VERSIONED PRE-IMPLEMENTATION ACCEPTANCE CONTRACT
>
> **Implementation status:** NOT IMPLEMENTED
>
> This file defines future evidence gates. It is not phase evidence and does
> not authorize Actions #396, Phase 5 implementation, capture, migration, or a
> release.

## How to use this file

Each gate is closed only when its evidence is attached to the exact candidate
or merged commit, independently reviewed, and accepted through the repository's
protected workflow. A green unit test is necessary but is not sufficient when
the gate concerns authority, security, quality, or resource cost.

Every gate record must include:

```text
gate identifier
implementation commit and tree
source/index/model revisions
test and benchmark commands
raw result artifacts or bounded receipts
security and privacy result
review/policy result
PASS or FAIL decision
```

The terms below are binding:

- **PASS** means the stated acceptance condition is demonstrated for the
  declared dataset and host profile.
- **FAIL** means the gate remains open and every dependent gate is blocked.
- **UNVERIFIED** is not PASS.
- A benchmark without its dataset, revision, command, and result is a claim,
  not evidence.

## Gate 0 — Governance admission prerequisite

### Objective

Prove that the dependency and governance gates preceding Phase 5 are closed and
that the candidate is based on the current protected `main`.

### Required evidence

- Fresh live GitHub `main` SHA and tree.
- Actions #396 exact PR/base/head/tree/parent tuple, required checks, reviews,
  conversations, rulesets, and protected normal-merge result.
- Final integration admission evidence after all declared dependency gates.
- No source, dependency, workflow, version, tag, release, or capture changes in
  the planning package.
- Signed commit and GitHub signature verification for the admitted planning or
  implementation commit.

### Metric

Exact candidate tuple and protected policy result.

### PASS condition

All prerequisite gates are `CLOSED / MERGED` or explicitly admitted by the
current governance contract, and live state matches the candidate tuple.

### FAIL condition

Any stale base/head/tree, missing required check, unresolved review/policy
requirement, or unverified protected merge.

### What it blocks

All Phase 5–9 implementation and every public version/release action.

## Gate 5A — Retrieval / Context Contracts

### Objective

Turn the planning contract into typed, versioned runtime boundaries without
silently expanding its meaning.

### Required evidence

- Schema validation for `QueryIntent`, `RetrievalBudget`, `SearchScope`,
  `DomainMatch`, `RetrievalStage`, `RetrievalPlan`, `NoiseAssessment`,
  `ContextItem`, `ContextPack`, `IndexWorkItem`, `IndexCostEstimate`,
  `MemoryDisposition`, and `MemoryAction`.
- Discriminator tests proving the envelope `contract` cannot be paired with a
  different payload type.
- Closed enum and `additionalProperties` tests where the contract is closed.
- Confidence `[0, 1]`, non-negative cost, bounded token/candidate, and safe path
  validation tests.
- Cross-field tests for trust↔authority, unsafe-noise→quarantine,
  source-reference safety, server-derived `MemoryAction`, and read-only
  `index_work_triggered=false`.
- Deterministic serialization/digest decision and test, or an explicit open
  decision that prevents digest-dependent behavior.
- No new authority store, model loader, mutation path, or runtime network
  surface.

### Metric

Schema validation pass rate, invalid-input rejection count, deterministic
serialization equality, and bounded object sizes.

### PASS condition

Valid fixtures pass, malformed/unknown fields fail closed, and repeated
serialization of identical inputs is byte-identical.

### FAIL condition

Unknown fields are silently accepted, bounds are missing, or the runtime
contract diverges from this version without a new version/ADR.

### What it blocks

5B–5H and all later phases.

## Gate 5B — Domain Policy v2 and Multi-domain Router

### Objective

Add backward-compatible multi-domain matching, traversal policy, authority
preference, noise policy, and index priority without conflating domain with
trust or lifecycle.

### Required evidence

- Domain v1 fixtures remain valid and retain legacy P.A.R.A. behavior when no
  v2 policy is present.
- `DomainMatch[]` fixtures with top, secondary, and low-confidence domains.
- Explainable reasons for every non-empty match and deterministic tie handling.
- Explicit policy for conflicting path/tag/type/model signals.
- Tests proving a domain does not grant canonical authority or change PSE,
  Task, Decision, or memory ownership.
- At least one cross-domain query fixture.

### Metric

Routing precision/recall, multi-domain coverage, routing latency, and domain
decision explainability coverage.

### PASS condition

The router returns bounded `DomainMatch[]`, preserves v1 behavior, and never
uses domain membership as an authority or lifecycle shortcut.

### FAIL condition

Queries are forced into one domain, reasons are absent, or a v2 policy breaks a
valid v1 registry without a migration decision.

### What it blocks

5C–5H and Phase 6 capture routing.

## Gate 5C — Search Scope Pushdown

### Objective

Ensure domain, path, project, source-type, trust, and temporal scope restrict
candidate generation before expensive dense, graph, or reranker work.

### Required evidence

- SQL/projection traces showing `SearchScope` reaches FTS and TF candidate
  selection.
- Dense-row selection traces showing out-of-scope vectors are not materialized
  into the scoring matrix.
- Graph traversal traces showing hops remain inside allowed scope.
- Temporal boundary tests with current and historical candidates competing for
  the same global rank.
- Defense-in-depth post-filter tests.
- A comparison against the current global-candidate/post-filter behavior.

### Metric

In-scope recall, out-of-scope candidate count, candidate count, dense rows
materialized, p50/p95 latency, and peak memory.

### PASS condition

Scope is applied before candidate generation for each applicable stage, recall
does not regress, and out-of-scope rows are zero at the stage boundary.

### FAIL condition

The implementation still scans the global corpus and only filters after top-K,
or scope filtering reduces recall without an explicit bounded policy.

### What it blocks

5D–5H, default planner selection, and large-vault capture indexing.

## Gate 5D — Incremental Dense Index v2 and IndexWorkQueue

### Objective

Make ordinary source changes produce a bounded dirty chunk set rather than a
global dense rebuild, while preserving exact generation and coverage safety.

### Required evidence

- Two-source or multi-source test: dense sync, edit one source, FTS update,
  dirty-set creation, queue processing, and unchanged-source vector reuse.
- Exact source/chunk/model/chunker revision records.
- Crash during embedding, restart recovery, idempotent retry, and stale-source
  rejection tests.
- Full-rebuild tests for model revision, dimension, chunker schema, dense schema,
  explicit migration, and proven corruption.
- Queue lifecycle tests for pending/running/deferred/failed/dead-letter states,
  leases, retry exhaustion, conditional timestamps/errors, restart recovery,
  idempotent requeue, and explicit review before dead-letter requeue.
- Low-RAM and bounded batch/commit receipts.
- Duplicate-content and chunk-identity collision tests.
- Proof that incomplete vector coverage cannot be published as a valid dense
  generation.

### Metric

`reembed_amplification`, dirty chunks, embedded chunks per run, queue length,
peak RAM, CPU time, model load time, and generation publication time.

### PASS condition

For an ordinary note with four changed chunks, embedded chunks are approximately
four, unchanged sources are not re-embedded, and all crash/recovery/coverage
checks pass.

### FAIL condition

One ordinary source edit resets the global manifest or re-embeds the corpus,
publishes incomplete vectors, loses queue work, or accepts incompatible model
identity without an explicit migration.

### What it blocks

5E–5H, automatic capture indexing, and real-vault migration.

## Gate 5E — Noise Policy and Hierarchical RetrievalPlanner

### Objective

Recognize cheap, semantic, and unsafe noise and escalate retrieval from cheap
to expensive stages without destructive source behavior or unbounded cost.

### Required evidence

- Fixtures for empty/near-empty, boilerplate, duplicate, status spam,
  superseded, stale, low-information, prompt injection, secret leakage, and
  authority spoof cases.
- `INCLUDE`, `DOWNRANK`, `EXCLUDE_FROM_RETRIEVAL`, and `QUARANTINE` decisions.
- Raw-source retention proof for every suppressed item.
- FAST→BALANCED→DEEP escalation traces including reasons for escalation and
  skipped stages.
- Fail-closed injection/quarantine tests that do not execute text or model
  output.
- Cost and token caps under adversarial repeated/large input.

### Metric

False-noise rate, quarantine rate, retained evidence count, escalation ratio,
dense/rerank usage, token cost, and p50/p95 query latency.

### PASS condition

Noise actions are explainable and non-destructive, unsafe input is quarantined,
and no request exceeds its declared budget.

### FAIL condition

Raw evidence is deleted, model text changes authority, unsafe input is included
by default, or maximum-cost retrieval is unconditional.

### What it blocks

5F–5H and all capture promotion.

## Gate 5F — ContextPackCompiler

### Objective

Assemble bounded context from existing knowledge and retrieval evidence without
creating new semantic entities or performing mutation at query time.

### Required evidence

- Deterministic pack fixtures with identical source/policy/model revisions.
- `ContextItem` authority, trust, provenance, freshness, contradiction, noise,
  retrieval stage, token-cost, bounded excerpt/reference mode, and redaction
  coverage.
- Maximum token/item enforcement and excluded-item explanations.
- Source revision, generation identity, policy revision, and pack digest
  readback where the digest decision is closed.
- Aggregate validation proving `consumed_tokens <= max_tokens` and rejecting
  oversized byte/item work rather than silently clamping it.
- Server-derived `access_policy` and `implementation_status` checks; caller
  input must not grant raw/quarantine access or mark a pack runtime-complete.
- Direct `ApplicationService` and MCP parity tests.
- Read-only test proving no ledger, TaskStore, DecisionService, vault, index,
  or proposal mutation occurs during compilation.
- Untrusted rendering/consumer contract for retrieved text.
- Raw/quarantine access tests proving explicit capability, mandatory redaction,
  and no default raw transcript release.

### Metric

Pack determinism, max-token violations, consumed/max token ratio, item count,
context precision, source provenance coverage, and query-side writes (target 0).

### PASS condition

Identical deterministic inputs produce identical bounded packs, all included
items have provenance and authority labels, and the compiler performs zero
mutation.

### FAIL condition

The compiler writes state, invokes the Project Semantic Compiler to create new
entities, loses provenance, exceeds token bounds, or treats retrieved text as
authority.

### What it blocks

5G–5H, Context Broker, and agent-facing context use.

## Gate 5G — MCP context and explainability surfaces

### Objective

Expose a small, typed, authenticated/read-only set of context and cost
surfaces without creating a parallel MCP or mutation plane.

### Required evidence

- `compile_context(...)`, `explain_context(...)`, `retrieval_plan(...)`,
  `index_status(...)`, and `index_cost(...)` contracts, or a reviewed decision
  that combines compatible surfaces without losing boundaries.
- `ApplicationService` use cases and DTO validation before MCP registration.
- Read-only/destructive/idempotent annotations matching behavior.
- Vault path containment, project existence, authorization, token, timeout, and
  result-size limits.
- Direct/MCP parity and malformed-input tests.
- No new TCP/HTTP surface, external fetch, shell invocation, or secret in
  response/logs.
- If a future source is remote, endpoint allowlisting, HTTPS, DNS/IP pinning,
  private-address rejection, redirect/timeout/size limits, and no credential
  forwarding are required; GitHub live facts remain control-plane evidence.

### Metric

Tool contract validity, unauthorized request rejection, response size, latency,
query-side writes, and tool count.

### PASS condition

Tools call existing application boundaries, return bounded typed data, reject
unsafe input, and preserve current transport/security topology.

### FAIL condition

MCP tools directly access stores, accept arbitrary paths/URLs, mutate on a
read-only operation, or multiply into ungoverned micro-tools.

### What it blocks

5H and every agent integration.

## Gate 5H — Shadow validation and Phase 5 closure

### Objective

Prove that the new planner can coexist with legacy retrieval and is safe to
make the default for the declared profile.

### Required evidence

- Legacy result served while the new planner runs in bounded shadow mode.
- Fixed dataset, query set, language mix, source revisions, model revisions,
  and reproducible commands.
- Retrieval quality, ContextPack, latency, token, dense, reranker, and index
  cost comparison.
- Adversarial trust/noise/authority and resource tests.
- Rollback/default-selection receipt and a signed closure report.

### Metric

Recall@K, MRR, MAP, nDCG, context precision, p50/p95 latency, dense/rerank
usage, token cost, index cost, and legacy non-regression.

### PASS condition

Declared quality and resource thresholds pass, legacy quality does not regress,
ContextPack determinism passes, and a rollback path is verified.

### FAIL condition

Shadow differs without an explainable bounded policy, quality regresses, cost
amplifies beyond policy, or default switching lacks protected evidence.

### What it blocks

Phase 5 closure, Phase 6 capture, and Phase 7 broker/view consumers.

## Gate 6 — Agent Capture and Integrations

### Objective

Add isolated adapters that preserve raw evidence and use the approved semantic,
memory, and indexing boundaries.

### Required evidence

- Lossless raw capture and declared redaction/retention receipts.
- Session identity, duplicate-ingest rejection, idempotency, and restart
  recovery.
- Backpressure and queue-bound load tests.
- Cheap noise classification before any model/index work.
- Candidate and `MemoryDisposition` routing with no automatic canonical
  promotion.
- Privacy enforcement and adapter isolation.
- Proof that a raw message is not automatically embedded or written as a
  durable canonical note.

### Metric

Raw events accepted/lost, duplicate ingest count, queue depth, backpressure
events, recovery time, redaction count, retention compliance, and promotion
rate.

### PASS condition

Capture is bounded, restart-safe, idempotent, privacy-compliant, and produces
raw/session/working/proposal outcomes before any canonical promotion.

### FAIL condition

Raw content is lost, every message becomes canonical/embedded, queues are
unbounded, or an adapter bypasses the governed mutation boundary.

### What it blocks

Bulk capture, real-vault migration, and Phase 9 release validation.

## Gate 7 — Context Broker and Materialized Views

### Objective

Provide rebuildable views over Working Memory, Durable Knowledge, PSE state,
Conversation Memory, and approved retrieval evidence.

### Required evidence

- View schemas for current project summary, open issues, active decisions,
  ready/blocked tasks, recent changes, hot knowledge, relevant sessions, domain
  summaries, contradictions, and pending repairs.
- Rebuild and stale-view detection from canonical sources.
- Resolution of `.power/tasks` versus `.power/work-packets` ownership.
- `ProjectStateService`, TaskService, DecisionService, memory, source, and
  generation revision provenance.
- Web/MCP/CLI authorization, path, CSRF/XSS, output encoding, and bounded
  response tests if a Web surface is included.

### Metric

View freshness, rebuild determinism, stale detection, query latency, view size,
and unauthorized read/write rejection.

### PASS condition

Views are deterministic/rebuildable, point to current authority revisions, and
never become an alternative source of truth.

### FAIL condition

A view is mutated as authority, stale data is presented as current, paths are
ambiguous, or a Web surface bypasses existing auth/security boundaries.

### What it blocks

Phase 8 hardening and Phase 9 migration/release.

## Gate 8 — Security, Reliability, and Performance

### Objective

Demonstrate that the integrated system remains fail-closed, private,
recoverable, and resource-bounded under normal and adversarial load.

### Required evidence

- Fault injection for queue, SQLite, model, cache, generation, projection,
  capture, and repair failures.
- Crash recovery and replay receipts with no source-of-truth loss.
- CPU cap at or below the host policy, low-RAM behavior, disk/queue bounds, and
  concurrency/soak evidence.
- Prompt injection, secret leakage, authority spoof, path traversal, symlink,
  SSRF, shell-injection, and malformed input tests at every boundary.
- Privacy/forgetting behavior across raw, working, durable, cache, index, view,
  and backup copies.
- No silent fallback; every degraded mode is labelled and policy-bound.

### Metric

Fault recovery rate, rollback success, peak RAM, CPU utilization, disk/queue
growth, p50/p95 latency, error classification, and secret-leak test count.

### PASS condition

All declared fault/security/resource gates pass with bounded, explainable
degradation and no unauthorized mutation or disclosure.

### FAIL condition

Any silent data loss, authority escalation, unbounded resource path, unsafe
network fetch, shell/path execution, or unverified rollback.

### What it blocks

Real-vault migration, bulk capture, RC, and release.

## Gate 9 — Migration, Benchmark, and Release

### Objective

Migrate only after architecture, shadow, capture, broker, and hardening gates
are closed, then make an evidence-based POWER 3.8.0 decision.

### Required evidence

- Versioned migration manifest with source/body/attachment hashes and rollback
  record.
- Small-dataset and soak results before real-vault migration.
- Full retrieval/index/capture benchmark with declared host and dataset.
- Upgrade validation, package/lock/SBOM evidence, documentation build, tests,
  lint/type checks, and security scan.
- Signed RC/tag/release only after protected approval and exact remote readback.
- Explicit decision record for GO or NO-GO; a plan or placeholder is never a
  release receipt.

### Metric

Migration completeness, rollback success, full benchmark metrics, coverage,
latency/resource limits, package integrity, and release artifact verification.

### PASS condition

All previous gates are `VALIDATED`, the declared migration is reversible, exact
release evidence is present, and the protected release decision is GO.

### FAIL condition

Any prerequisite is unverified, migration is lossy/unreversible, release
artifacts are unsigned/unreadable, or benchmark/resource claims lack evidence.

### What it blocks

The POWER 3.8.0 tag, release, and public version publication.

## Cross-gate invariants

These invariants apply to every gate:

- Source truth outranks projections, indexes, caches, and model output.
- Semantic domain is independent from trust/lifecycle state.
- Raw evidence is retained according to policy; noise never means delete.
- LLM output is untrusted and cannot directly mutate canonical state.
- PSE, TaskService, DecisionService, memory proposal/apply, and generation
  publication retain their existing ownership.
- A changed SHA, source revision, model revision, or policy creates a new
  evidence epoch; old evidence is retained but not silently reused.
- No external vector backend is mandatory without a separate ADR and benchmark.
- Every future implementation must report `UNVERIFIED` rather than infer PASS.
