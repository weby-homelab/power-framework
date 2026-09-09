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

## Gate 0 — Controlled Dependency Refresh final-integration prerequisite

### Objective

Prove that the Controlled Dependency Refresh is closed at final integration and
that the governance candidate is based on the current protected `main`.

### Required evidence

- Fresh live GitHub `main` SHA and tree.
- Python, WEB security, HF, and Actions admissions are closed with exact merged
  evidence or an explicit bounded disposition.
- PR #402 is classified deferred/closed without merge and PR #407 is classified
  superseded historical evidence/closed without merge.
- Final integration admission evidence covers the current dependency graph,
  lock/export consistency, package/security/upgrade/frozen regression gates,
  required CI, Docs, and CodeQL.
- No source, dependency, workflow, version, tag, release, or capture changes in
  the planning package.
- Signed commit and GitHub signature verification for the admitted planning or
  implementation commit.

### Metric

Exact candidate tuple and protected policy result.

### PASS condition

All declared dependency surfaces are closed or explicitly deferred by the
current governance contract, final integration evidence is green, and live
state matches the governance candidate tuple.

### FAIL condition

Any stale base/head/tree, missing required check, dependency inconsistency,
security regression, or unverified protected merge.

### What it blocks

Foundation Hardening, all Phase 5–9 implementation, and every public
version/release action.

## Gate Foundation — Pre-Phase-5 Foundation Hardening

### Objective

Close the authority, principal, retrieval-boundary, failure-receipt, and
deadline/budget gaps that would make new agent-facing retrieval surfaces unsafe.
This is an integration admission before Phase 5, not a reopening of Phase 0–4.

### Required evidence

- `artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md`
  is revalidated against the exact candidate source tree.
- F1: missing approval or authorized context fails closed and cannot mutate any
  canonical store.
- F2: actor labels are not authentication; principal/session binding is explicit
  and supports the declared local/offline boundary.
- F3: agent-facing retrieval cannot use an environment-controlled external DB or
  path to bypass the configured vault/source boundary.
- F4: failed operations produce bounded, structured, secret-free receipts when
  the contract requires a receipt, without claiming success or copying raw
  content.
- F5: sync/async deadline, cancellation, worker, timeout, and result-budget
  semantics are actual bounded execution semantics, not only post-action timing
  checks.
- Adversarial tests cover path traversal, symlinks, SSRF, shell injection,
  malformed input, authentication, authorization, and secret handling.
- PSE, Task, Decision, crash-recovery, Web, MCP, lint/type/test/security, and
  exact protected policy gates remain green.

### Metric

Unauthorized mutation count, principal-binding rejection count, boundary-bypass
count, secret/content leakage count, cancellation/timeout classification, and
receipt completeness.

### PASS condition

All F1–F5 controls fail closed under adversarial and integration tests, no
existing Phase 0–4 contract regresses, and the exact candidate is normally
merged under current protection with independent security review.

### FAIL condition

Any implicit apply authority, actor-as-authentication path, external retrieval
boundary bypass, unbounded/secret-bearing failure receipt, or post-action-only
deadline remains.

### What it blocks

Phase 5A–5H, agent-facing ContextPack/MCP surfaces, Phase 6 capture, and all
later phases.

## Gate 5A — Runtime contracts v2 and frozen evaluation corpus

### Objective

Turn the approved v2 planning contract and frozen evaluation manifest into
typed, versioned runtime boundaries without silently expanding their meaning.

### Required evidence

- Schema validation for the v2 retention, sensitivity, tombstone, bitemporal,
  evidence-ordering, resource-profile, budget, retry, and evaluation contracts.
- Retained v1 contracts remain parseable historical evidence; they are not
  silently reinterpreted as the v2 runtime contract.
- A frozen evaluation manifest covers UA, EN, mixed UA/EN, exact lookup,
  project state, decision, task, code, infrastructure, research, cross-domain,
  historical/stale, superseded, contradiction, noise, prompt injection, hard
  negatives, and authority conflict.
- Dataset digest, query-set digest, schema version, ground-truth provenance,
  development split, holdout split, and no-tuning-on-holdout audit.
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
- Retention separates append-only audit metadata from eligible payload; noise
  classification alone never authorizes source deletion.
- Bitemporal tests handle delayed capture/correction and omit validity intervals
  when no meaningful interval exists.
- Resource profiles are abstract (`LOW_RESOURCE`, `STANDARD`, `PERFORMANCE`,
  `CUSTOM`); host facts remain deployment/benchmark evidence.
- FAST/BALANCED/DEEP defaults are calibrated hypotheses, not product constants;
  caller hints can only lower a server-selected cap.
- Retry tests prove a small bounded budget, backoff, dead-letter, explicit review
  before requeue, and no retry storm.
- Authority-sensitive tests prove canonical project state, decisions, tasks, and
  governance outrank semantically similar raw chat before relevance/reranking.
- No new authority store, model loader, mutation path, or runtime network
  surface.

### Metric

Schema validation pass rate, invalid-input rejection count, deterministic
serialization equality, and bounded object sizes.

### PASS condition

Valid fixtures pass, malformed/unknown fields fail closed, repeated
serialization of identical inputs is byte-identical, and holdout access is
auditable and never used for tuning.

### FAIL condition

Unknown fields are silently accepted, bounds are missing, or the runtime
contract diverges from this version without a new version/ADR.

### What it blocks

5B–5H and all later phases.

## Gate 5B — Domain Policy v2 and Multi-domain Router

### Objective

Add backward-compatible multi-domain matching, traversal policy, authority
preference, noise policy, and index priority without conflating domain with
trust or lifecycle. Authority preference is a policy stage, not a semantic
similarity tie-breaker.

### Required evidence

- Domain v1 fixtures remain valid and retain legacy P.A.R.A. behavior when no
  v2 policy is present.
- `DomainMatch[]` fixtures with top, secondary, and low-confidence domains.
- Explainable reasons for every non-empty match and deterministic tie handling.
- Explicit policy for conflicting path/tag/type/model signals.
- Tests proving a domain does not grant canonical authority or change PSE,
  Task, Decision, or memory ownership.
- Authority-vs-relevance fixtures prove a canonical state/decision/task or
  governance record outranks a more similar raw chat when intent is
  authority-sensitive.
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
- Default `include_archived=false` and `include_quarantine=false` behavior,
  server-derived privileged authorization for overrides, and explicit audit
  evidence for any archived/quarantine read.
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

## Gate 5D — RetrievalPlanner and ContextPack read-only vertical slice

### Objective

Prove the minimum read-only planner/context vertical slice needed to evaluate
retrieval behavior without making a persistent background queue a prerequisite.

### Required evidence

- Read-only `RetrievalPlanner` and `ContextPack` fixtures with authority
  ordering, temporal/supersession state, provenance, contradiction state, and
  bounded cost.
- `INCLUDE`, `DOWNRANK`, `EXCLUDE_FROM_RETRIEVAL`, and `QUARANTINE` decisions for
  empty, duplicate, stale, superseded, prompt-injection, secret-leakage, and
  authority-spoof cases.
- Raw-source retention proof for every suppressed item; noise classification
  alone never deletes source payload.
- FAST→BALANCED→DEEP escalation traces with reasons for escalation and skipped
  stages, cost/token caps, and explicit optional-neural failure.
- Maximum token/item enforcement, excluded-item explanations, redaction, and
  `consumed_tokens <= max_tokens` rejection rather than silent clamping.
- Server-derived access policy and implementation status; caller input cannot
  grant raw/quarantine access or mark a pack runtime-complete.
- Direct ApplicationService/MCP parity and a read-only proof that no ledger,
  TaskStore, DecisionService, vault, index, or proposal mutates during compile.
- Explicit `include_archived=false` and `include_quarantine=false` defaults,
  privileged authorization for overrides, and audit evidence for every override.
- Untrusted rendering/consumer contract for retrieved text.

### Metric

Pack determinism, authority-vs-relevance ordering, false-noise/quarantine rate,
retained evidence count, escalation ratio, token cost, and query-side writes.

### PASS condition

Identical deterministic inputs produce identical bounded packs, canonical
authority outranks semantically similar raw chat for authority-sensitive intent,
all included items carry provenance/authority labels, and compilation performs
zero mutation.

### FAIL condition

The compiler writes state, creates semantic entities at query time, loses
provenance, exceeds bounds, treats retrieved text as authority, or allows
caller-controlled archive/quarantine access.

### What it blocks

5E–5H, Context Broker, and agent-facing context use.

## Gate 5E — Shadow benchmark and holdout validation

### Objective

Compare the planner/context vertical slice with legacy retrieval in bounded
shadow mode before any default-selection decision.

### Required evidence

- Frozen evaluation manifest with dataset/query-set digests, category coverage,
  ground-truth provenance, development/tuning split, and sealed holdout split.
- Explicit proof that no tuning, threshold choice, prompt change, or profile
  calibration reads holdout labels or results.
- Legacy result remains served while the new planner runs in bounded shadow mode.
- Authority-vs-relevance, temporal validity, supersession, contradiction, noise,
  prompt-injection, hard-negative, and mixed-language cases are reported.
- Quality, deterministic pack, token, latency, resource, dense/reranker, and
  index-cost comparison with reproducible commands and host profile.
- Rollback/default-selection receipt and signed closure report.

### Metric

Recall@K, MRR, MAP, nDCG, context precision, authority-order violations,
p50/p95 latency, token cost, dense/rerank usage, index cost, and legacy
non-regression.

### PASS condition

Development and holdout results are separately reproducible, holdout integrity
is proven, declared quality/resource thresholds pass, legacy quality does not
regress, and default switching has protected evidence.

### FAIL condition

Holdout leakage, authority outranked by relevance, unexplained shadow drift,
quality regression, cost amplification, or missing rollback evidence.

### What it blocks

5F–5H, default planner selection, capture indexing, and migration.

## Gate 5F — Incremental Dense Validity and dirty-set behavior

### Objective

Make ordinary source changes produce a bounded dirty chunk set rather than a
global dense rebuild, while preserving exact generation and coverage safety.

### Required evidence

- Two-source or multi-source test: dense sync, edit one source, FTS update,
  dirty-set creation, and unchanged-source vector reuse.
- Exact source/chunk/model/chunker revision records, partial-dense validity,
  crash/restart recovery, idempotent retry, and stale-source rejection.
- Full-rebuild tests for model revision, dimension, chunker schema, dense schema,
  explicit migration, and proven corruption.
- Low-RAM and bounded batch/commit receipts; incomplete vector coverage cannot
  publish as a valid dense generation.
- A persistent `IndexWorkQueue` is not a prerequisite here; if benchmark
  evidence proves it necessary before Phase 6, an explicit ADR and bounded
  admission are required.

### Metric

`reembed_amplification`, dirty chunks, embedded chunks per run, peak RAM, CPU
time, model load time, and generation publication time.

### PASS condition

An ordinary edit re-embeds only its changed chunks, unchanged sources remain
valid, and all crash/recovery/coverage checks pass.

### FAIL condition

An ordinary source edit triggers a global rebuild, loses dirty work, publishes
incomplete vectors, or accepts incompatible model identity without migration.

### What it blocks

5G–5H, automatic capture indexing, and real-vault migration.

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
- RetentionClass, SensitivityClass, PayloadRetentionPolicy, and bounded
  TombstoneReceipt/DeletionReceipt tests across raw, working, durable, cache,
  index, view, and backup copies.
- Bitemporal `observed_at`/`recorded_at` behavior with optional
  `valid_from`/`valid_to`, delayed capture, correction, and supersession tests.
- Session identity, duplicate-ingest rejection, idempotency, and restart
  recovery.
- Backpressure and queue-bound load tests.
- Persistent `IndexWorkQueue` ownership, lifecycle, retry/dead-letter, and
  restart-recovery tests are primary Phase 6 evidence; Phase 5 may use only a
  minimum dirty-set substrate unless an ADR proves earlier necessity.
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

## Gate 7 — Optional Context Broker and Materialized Views

### Objective

Provide rebuildable views over Working Memory, Durable Knowledge, PSE state,
Conversation Memory, and approved retrieval evidence. A Context Broker façade
is optional and is admitted only if multiple real consumers demonstrate
orchestration value beyond `ContextPackCompiler`, `ApplicationService`, and
materialized views.

### Required evidence

- View schemas for current project summary, open issues, active decisions,
  ready/blocked tasks, recent changes, hot knowledge, relevant sessions, domain
  summaries, contradictions, and pending repairs.
- Rebuild and stale-view detection from canonical sources.
- A documented consumer/value decision proving why a broker façade is needed;
  otherwise the façade is not implemented.
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
- Append-only audit metadata is distinct from retained payload; retention and
  deletion require explicit policy and a bounded tombstone receipt.
- `observed_at` and `recorded_at` are distinct; `valid_from`/`valid_to` are
  optional and are not fabricated for information without a validity interval.
- LLM output is untrusted and cannot directly mutate canonical state.
- Authority policy precedes semantic relevance for authority-sensitive intents;
  no single opaque score may erase that ordering.
- Evaluation holdout data is never used for tuning, threshold calibration, or
  profile selection.
- PSE, TaskService, DecisionService, memory proposal/apply, and generation
  publication retain their existing ownership.
- A changed SHA, source revision, model revision, or policy creates a new
  evidence epoch; old evidence is retained but not silently reused.
- No external vector backend is mandatory without a separate ADR and benchmark.
- Every future implementation must report `UNVERIFIED` rather than infer PASS.
