# POWER 3.8 — Development Protocol

> This protocol is a repository-facing operating contract. Before a protected
> merge it is provisional; after a protected merge its paths are canonical for
> that snapshot. It never replaces live GitHub facts, exact Git objects, branch
> protection, or an independent gate authorization.

## Source of truth

```text
GitHub live state > chat history
exact Git objects > narrative
remote CI/checks > local claims
repository-native memory > agent memory
evidence > assertion
```

Repository documents are a recovery aid, not a mutable-fact oracle. Every new
agent must read the current documents and then independently verify their SHA
anchors against GitHub REST before acting.

## Non-negotiable execution rules

```text
GitHub > chat history
exact SHA > narrative
candidate SHA may change during remediation
candidate SHA change invalidates old evidence, but does NOT terminate the work;
it starts a new candidate audit epoch
mergeable_state alone is not merge authorization and is not an automatic blocker;
actual required policy state must be diagnosed
one gate = one bounded work package
no admin bypass
normal merge preferred
```

These rules apply to both provisional and canonical repository memory. A
candidate or governance branch may advance only through a newly recorded epoch,
fresh validation, and the ordinary protected GitHub policy path.

## Evidence hierarchy

Use this order when sources disagree:

1. Git object and GitHub REST object state.
2. GitHub PR, branch-protection, ruleset, review, and check state.
3. Remote CI artifacts attached to the exact SHA.
4. Merged repository evidence and authoritative phase reports.
5. Local reproduction and local worktree evidence.
6. Handoff and other narrative reports.
7. Chat history.

Labels must be precise:

- **LOCAL CANDIDATE** — local worktree or branch only.
- **REMOTE EXACT-HEAD** — evidence attached to the exact PR head.
- **MERGED MAIN** — evidence attached to an exact protected merge on `main`.
- **FINAL INTEGRATION** — evidence after all declared gates are admitted.

Candidate evidence must never be called `MERGED MAIN` or `FINAL INTEGRATION`.

## Exact-head principle

An authorization is valid only for the exact tuple:

```text
PR number
base SHA
head SHA
head tree SHA
head parent(s)
```

The following retained tuple is the first historical HF #406 candidate epoch;
it is not the current main state and must not be reused for a future gate:

```text
PR: 406 (historical candidate epoch 1)
BASE: 119d5c39aa2c22734ca72c351f8a70790371678f
HEAD: 201da2e0e78d1bbf860c98dc653008c0fb4984cd
TREE: c8d66c9bf65c54b09bb9990380313737af63c932
PARENT: 119d5c39aa2c22734ca72c351f8a70790371678f
```

The final HF #406 admitted tuple is retained in the current-state and
post-merge handoff documents. The earlier planning-start observation
`d8b704f6125347ff9f9c39981193807d2160b135` is historical evidence only. The
current final-integration snapshot base is
`a386858a45489eb5db213d42ffe773db9134ff88`; it is an immutable snapshot anchor,
not a promise about a future governance merge SHA.

Any change to the PR, base, head, tree, parent, diff, or relevant policy
invalidates the evidence for that candidate epoch. A repair, compatibility
change, lock/export regeneration, merge of current `main`, or conflict
resolution may update the candidate; record the new tuple and start a new audit
epoch instead of silently reusing old evidence. Do not merge a different
object under the old approval.

The candidate epoch record must include the new base, head, tree, parent(s),
diff, dependency/export hashes, test and security results, remote checks, and
merge-policy observation. A changed SHA is stale evidence, not a terminal
workflow condition.

## One chat = one gate

One bounded chat handles one major gate. Do not automatically chain:

```text
Foundation Hardening → Phase 5A–5H → Phase 6 → Phase 7 → Phase 8 → Phase 9
```

The Controlled Dependency Refresh, including Actions #396 and final
integration, is closed in the current governance snapshot. The next bounded
runtime gate is Foundation Hardening; it must be independently revalidated from
fresh live state and must not be silently chained into Phase 5.

## GitHub publication policy

Use local Git plus the configured GPG key as the canonical path for signed
repository commits and branch publication:

- create the commit locally with `git commit -S`;
- verify it locally with `git verify-commit HEAD`;
- publish through an authenticated HTTPS or SSH Git channel without placing a
  token in a remote URL, command argument, prompt, log, or repository file;
- use authenticated GitHub REST for live state reads, PR/comments, state
  pointers, and the protected normal merge endpoint when authorized.

Do not use admin bypass, protection changes, fake signatures, browser-only
merges, GraphQL bypasses, or ad-hoc remote URL credentials. If the preferred
publication channel fails, try at most one other legitimate authenticated
channel; keep the branch and provisional evidence available if canonical
signing/publication remains blocked.

The GitHub credential is host-local and must be injected only in memory. Never
print, paste, commit, log, URL-encode, or place it in command arguments, remote
URLs, prompts, handoffs, or repository files. If authenticated REST state is
not observable, stop; do not ask an agent to guess or bypass the missing policy.

## Merge policy

The required merge method is a **normal merge commit** when a gate is admitted.

For POWER 3.8 governance, dependency, architecture, and release gates, this
gate-specific exact-head rule takes precedence over the generic
`CONTRIBUTING.md` preference for squash merges. It preserves the documented
merge parents and exact candidate tuple. It does not override GitHub branch
protection: if the live protected policy accepts only another method, record
that policy conflict as a blocker and do not bypass or weaken protection.

- Revalidate PR, base, head, tree, checks, reviews, policy, and mergeability
  immediately before one merge attempt.
- No administrator bypass.
- No protection bypass.
- No force push.
- No auto-merge.
- No merge queue override.
- No temporary protection or ruleset modification.
- `mergeable_state` is diagnostic only. `unstable` or `blocked` requires a
  table of required/optional checks, pending/failing checks, reviews and
  requests, conversations, branch freshness, rulesets, queue, deployments, and
  the exact protected merge response; it is not by itself authorization or a
  terminal blocker.
- When the concrete GitHub policy state accepts a normal protected merge, make
  at most one normal `merge_method=merge` attempt for the exact current head
  with an exact-head guard. If GitHub rejects it, record the exact reason and
  remediate rather than blindly retrying.

## Governance publication boundary

Repository governance is a canonical snapshot memory; live GitHub is mutable
operational truth. At a meaningful gate boundary, the publication sequence is:

```text
read governance snapshot
        ↓
read latest append-only handoff
        ↓
fetch live main and policy through REST
        ↓
verify snapshot ancestry and exact gate evidence
        ↓
publish one consolidated governance reconciliation
```

The current reconciliation records the closed Controlled Dependency Refresh,
the deferred/closed #402 bundle, the superseded/closed #407 historical PR, and
the next Foundation Hardening gate. Only the protected normal merge makes this
snapshot canonical; an open PR or unsigned REST Contents commit remains
provisional. Historical handoffs and evidence branches are retained and never
rewritten to look current.

## Governance churn rule

Do not create a governance PR after every implementation commit. Publish
repository-state reconciliation only at a meaningful gate boundary or when
stale state would materially mislead the next agent. The default model is:

```text
bounded implementation PR
        +
PR closure receipt
        +
consolidated governance update at a major boundary
```

## GPG and commit integrity

Authoritative implementation and governance commits must be GPG-signed and
verified by GitHub. A local signature alone is insufficient for a canonical
claim. Record signature status and exact object identity in the handoff. The
local gate is:

```bash
git config user.name
git config user.email
git config user.signingkey
gpg --list-secret-keys
git commit -S
git verify-commit HEAD
```

## Evidence commits

Do not create a trailing evidence commit solely to replace a previously unknown
final SHA. The commit being evaluated must contain the intended content, and
the final merge SHA must be resolved from live GitHub state after the merge.

## Handoff discipline

Every gate produces one timestamped, append-only handoff. A handoff must contain
exact SHAs, state labels, evidence links, blockers, and the next authorized gate;
it must not paste secrets or unbounded logs. Historical handoffs are retained as
historical snapshots and are never silently rewritten as current state.

## Context / memory / retrieval architecture rules

The POWER 3.8 architecture plan and its versioned planning artifacts are
binding design direction only. They are not runtime implementation or phase
evidence. The following rules apply when the owning future phase is authorized.

### Source and authority hierarchy

```text
raw source / canonical ledger
        > curated semantic projection
        > materialized views
        > indexes / embeddings / caches
```

Indexes, views, embeddings, reranker scores, and `ContextPack` objects are
derived and rebuildable. Index corruption may never rewrite source truth.

### Orthogonal data axes

Semantic domain and trust/lifecycle are separate fields:

```text
domain: project_state | projects | decisions | tasks | code | infrastructure
        | research | documentation | operations | agent_conversations | logs

trust/lifecycle: RAW | PROPOSED | CURATED | VERIFIED | CANONICAL | SUPERSEDED
                 | ARCHIVED | QUARANTINED | NOISE
```

`domain != authority`, `domain != lifecycle`, `path != trust`, and `archive` is
not a semantic domain. Chat evidence can be promoted only through explicit
provenance and policy; it is neither permanently untrusted nor automatically
canonical.

### Reuse-first and unambiguous naming

Reuse `search_vault` executors, `DomainRegistry`, `SemanticChunker`,
`BGEM3OnnxManager`, `BGEM3Reranker`, `ProjectStateService`, PSE, TaskService,
DecisionService, memory proposal/apply, maintenance, and generation index.
Do not create a parallel search engine, semantic compiler, domain registry,
canonical memory database, task/decision store, mutation path, or PSE authority.

The Phase 3 role is **ProjectSemanticCompiler** (currently exposed by the
source class `SemanticCompiler` in `semantic_compiler.py`); it produces typed
candidates and proposals. The Phase 5 role is **ContextPackCompiler**; it
selects existing knowledge and assembles bounded context. Do not introduce a
generic `SemanticCompiler` or `ContextCompiler` that overlaps these roles.

### Retrieval and scope

Use `DomainMatch[]`, not single-domain routing. Resolve `SearchScope` before
FTS/TF/dense/graph candidate generation. Candidate generation must be bounded
by domain, path, source type, trust, temporal, and project scope; post-filtering
alone does not satisfy the contract.

Use progressive budgets:

```text
FAST     = state/metadata/FTS/TF/temporal/noise_gate/views; no model load
BALANCED = FAST + selected-domain semantic + small rerank pool
DEEP     = multi-domain semantic/graph_assisted/temporal/rerank/raw fallback by escalation
```

Cheap retrieval precedes expensive retrieval. A query must not trigger a
global reindex. The normal source-edit path must not require global
re-embedding.

The effective bounded value is layered as structural absolute safety ceiling →
`ResourceProfile` default → domain policy cap → caller-lower-only hint. The
caller may only lower a server-selected cap. FAST/BALANCED/DEEP numeric
defaults are planning hypotheses and must be calibrated in the Phase 5 shadow
benchmark. Profile flags and model-load policy are server-selected. An
incompatible stage/flag combination is rejected or explicitly escalated, never
silently clamped. Host-specific facts belong to deployment profiles and
benchmark evidence, not framework invariants.

For authority-sensitive `project_state`, `decision`, `task`, and `governance`
intents, ordering is access policy → authority policy → temporal validity →
supersession → contradiction state → semantic relevance → reranking →
diversity/token packing. A semantically similar raw chat must not outrank a
canonical authority record merely because its floating-point score is higher.

### Noise and capture

Noise actions are only `INCLUDE`, `DOWNRANK`, `EXCLUDE_FROM_RETRIEVAL`, or
`QUARANTINE`; there is no `DELETE_SOURCE` action. Raw capture is append-only,
privacy-bounded, idempotent, restart-safe, and backpressured. Do not promote or
embed every agent message automatically.

Retention class and sensitivity class are separate from trust/lifecycle. An
append-only audit/tombstone receipt is not indefinite payload retention. A
retention action may expire eligible payload while retaining bounded,
secret-free evidence. Noise classification alone never deletes source. Where
applicable, delayed capture distinguishes `observed_at` and `recorded_at`, while
`valid_from`/`valid_to` remain optional.

### Model authority and repair

LLM output is untrusted input. A model may classify, rank, extract a proposal,
prepare repair, or explain. It may not mark output canonical, approve a
Decision, complete Task authority, advance PSE, or bypass governed mutation.

Repair is classed as deterministic derived repair, semantic repair, or
authority/security repair. Semantic repair always follows:

```text
detect → evidence → proposal → approval policy → apply → verify → receipt
```

Existing memory proposal/apply and maintenance boundaries remain the owners of
mutation. Caller-supplied booleans are not a substitute for the future human
approval proof decision.

### Dense cost and external vector policy

Track global model/chunker/schema identity separately from per-source/per-chunk
validity. Phase 5 proves only the minimum dirty-set/index-validity substrate,
HOT/WARM/COLD priorities, and an `IndexCostEstimate` before expensive work.
Persistent `IndexWorkQueue` is the primary Phase 6 owner unless a Phase 5
benchmark and ADR prove earlier need. Full dense rebuild is reserved for
model/dimension/chunker/schema change, explicit migration, or proven corruption.

Qdrant, Milvus, or another vector database is not mandatory. Any future ANN or
external backend requires scope/index benchmarks, a separate ADR, supply-chain
admission, operational cost proof, and explicit approval.

### Shadow requirement

The new planner runs in shadow while legacy retrieval remains served. Default
retrieval changes only after quality, determinism, token, latency, resource,
noise, and index-cost evidence passes the acceptance artifact.

## Plan → Act → Validate

Each bounded action follows PAV:

1. **Plan:** state scope, exact objects, authority, and stop conditions.
2. **Act:** make one isolated change only in the authorized paths.
3. **Validate:** inspect added and removed content, run the applicable checks,
   verify signatures and live REST state, and mark unknowns `UNVERIFIED`.

For candidate changes, validation must also recompute the candidate epoch when
the head, base, tree, parent, diff, or policy state changes. The old evidence
is retained as historical input and never silently promoted.

Maximum retry discipline:

- one merge attempt per exact gate unless GitHub explicitly reports transient
  failure;
- one fresh state investigation after a merge/policy failure;
- one CI rerun for a proven external infrastructure failure;
- no repeated commands that add no evidence.

## Current operational state

Current state after the protected governance and HF merges:

```text
CONTROLLED DEPENDENCY REFRESH: CLOSED / FINAL INTEGRATION VERIFIED
PR #402: CLOSED WITHOUT MERGE / DEFERRED
PR #407: CLOSED WITHOUT MERGE / SUPERSEDED HISTORICAL EVIDENCE
CONTEXT/MEMORY/RETRIEVAL ARCHITECTURE: PROVISIONAL PLANNING V2 / CANONICAL AFTER PROTECTED MERGE / NOT IMPLEMENTED
FOUNDATION HARDENING: NEXT RUNTIME GATE / NOT STARTED
ACTIONS #396: CLOSED / MERGED
PHASE 5: BLOCKED / NOT STARTED
PUBLIC VERSION: 3.7.11
POWER 3.8.0: NO-GO
```

The HF and Actions merge receipts are retained `MERGED MAIN` evidence. Their
candidate epochs are retained `REMOTE EXACT-HEAD`/historical evidence and are
not themselves merged-main proof. Do not start Foundation Hardening or Phase 5–9, version bumps,
tags, releases, release images, or final release notes from this snapshot;
Foundation Hardening requires its own bounded admission.

## Cross-links

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Planning index](README.md)
- [Context / memory / retrieval architecture](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Latest final-integration handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-09T065950Z_controlled-dependency-refresh_final-integration.md)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)
