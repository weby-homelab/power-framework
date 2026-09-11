# POWER 3.8
# PHASE 5B — DOMAIN POLICY V2 + DETERMINISTIC MULTI-DOMAIN ROUTER
# CANDIDATE / ADMISSION REPORT

## Gate state

```text
PUBLIC_VERSION: 3.7.11
STARTING_MAIN: dde1e1369c2d79d8f01b9fce21ae1fb55834a814
STARTING_TREE: 194d8c80dabb816bf8027ff097abc1b016dad317
PHASE_5A: CLOSED / MERGED / VERIFIED / PR #415
PHASE_5A_1: CLOSED / MERGED / VERIFIED / PR #416
ACTIVE_EVALUATION_REVISION: v1.1
PHASE_5B: CANDIDATE / IN ADMISSION
PHASE_5C: BLOCKED / NOT STARTED
POWER_3_8_0: NO-GO
```

This report is a repository projection for the bounded 5B candidate. Mutable
PR/head/check/merge values require the exact-head REST readback and are not
fabricated here before protected admission.

## Starting observation

The authenticated GitHub REST preflight observed:

```text
MAIN_SHA: dde1e1369c2d79d8f01b9fce21ae1fb55834a814
MAIN_TREE: 194d8c80dabb816bf8027ff097abc1b016dad317
MAIN_PARENTS:
  0a70ca4e9acc89596acd192931c1d174040ad484
  94e2e08a2d37884b90ac895de35979fa87696bd5
MAIN_VERIFICATION: verified=true / reason=valid
OPEN_PRS: 0
PR_415: MERGED / VERIFIED
PR_416: MERGED / VERIFIED
```

The current main tree was independently compared with the local checkout by
recursive Git tree blob IDs: all 918 entries and every required preflight file
matched tree `194d8c80…`. Local historical refs were stale, so the candidate is
admitted from the live tree identity rather than from a stale local `main` ref.

Branch protection was freshly enumerated through REST. It requires strict
contexts `test (3.13)`, `test (3.14)`, `security`, `package-smoke`,
`upgrade-matrix (ubuntu-latest)`, `upgrade-matrix-aggregate`,
`base-runtime-smoke`, `benchmark-integrity`, `analyze (python)`, `CodeQL`, and
`build`; normal protected merge, no bypass, is the only admission path.

## Bounded scope

Implemented in this gate:

- strict bounded Domain Policy v2 parser and inert policy representation;
- backward-compatible v1 registry parser and v1 placement/search behavior;
- vault-contained `POWER_DOMAIN_CONFIG` and bounded no-follow file reads;
- separate `SourceDomainClassifier` and `RetrievalDomainRouter` APIs;
- bounded explainable `DomainMatch[]`, fixed-point signal scoring, threshold,
  deterministic tie handling, conflict reasons, and caller-lower-only cap;
- minimal `RuntimeContractEnvelope` lazy-registration repair for import-order
  determinism;
- routing ground truth, development/holdout evaluation, tests, docs, and
  recovery evidence.

Not implemented: SearchScope pushdown, FTS/TF/dense/graph scope execution,
RetrievalPlanner, ContextPackCompiler, ranking, indexing/dirty sets, MCP
context tools, capture, models, vector databases, releases, tags, deployment,
or public-version changes.

## Preflight dispositions

### `POWER_DOMAIN_CONFIG` containment

The loader now canonicalizes the configured vault, rejects absolute/outside/
traversal/URI/Windows paths, rejects symlinked files and parents, requires a
regular bounded file, rejects malformed/duplicate-key YAML, and fails closed on
explicit missing/read errors. An empty environment variable retains the v1
truthiness fallback to the default vault-local path. Default missing config
still returns the empty v1 registry.

Domain template reads and domain placement use the same vault checks. Config and
template reads use descriptor-relative `O_NOFOLLOW` traversal; domain directory
creation uses descriptor-relative `mkdirat` semantics. These checks are
containment controls only; they do not grant authority.

### Legacy placement/search compatibility

`route_domain()` remains a single `DomainSpec | None` placement API with v1
additive rule scoring and declaration-order ties. `resolve_search_policy()` still
uses the first v1 search priority and leaves no-domain `auto` to the existing
runtime. Missing v1 registry retains the P.A.R.A. fallback. The new router is
not substituted into CLI placement or `search_vault`.

### Source membership vs query routing

`SourceDomainClassifier` consumes source-relative path, tags, and note type and
can return multiple `SourceDomainMembership` values. Path selectors are never
added to query text. `RetrievalDomainRouter` consumes query, validated intent,
bounded hints, and an optional validated budget; it never reads source metadata.

### Runtime contract import order

The preflight reproduced the `EvaluationCorpusManifest` registry defect: a
manifest envelope could raise a raw `KeyError` when only `context_contracts`
was imported. The bounded repair lazily loads the optional evaluation contract,
rechecks the registry, and converts unavailable discriminators to stable
validation errors. No unrelated Phase 5A DTO or schema meaning changed.

## Domain Policy v2 runtime contract

The runtime fixture is
`artifacts/project-state/phase-5b/domain-policy-v2.runtime.yaml`. The planning
example remains planning-only and is deliberately rejected by the runtime
loader. Closed fields are:

- domain identity;
- source selectors: safe relative glob paths, tags, and types;
- query signals: literal keyword phrases and validated intent IDs;
- inert retrieval stages, candidate/rerank bounds, budget class, escalation;
- inert traversal declaration;
- inert index priority/dense declaration;
- inert noise suppression/action declaration;
- inert authority preference/archive/raw-capture declaration.

The parser rejects unknown fields, duplicate keys/domain IDs/selectors,
non-finite/negative/unbounded values, unsafe paths, invalid enums, excessive
collections, invalid booleans/integers, and malformed YAML. It never executes
regex, code, shell, templates, retrieval stages, authority ordering, noise
suppression, or indexing from policy text.

## Router contract

For each domain, the frozen algorithm uses literal normalized keyword matching,
intent compatibility, and caller hint compatibility with integer weights
`50/30/20`, normalized by `100`. Inclusion is inclusive at `0.20`; low
confidence is marked at `0.20`; server maximum is `4` in the admission policy
and structural ceiling is `16`. Ordering is score descending, explicit policy
order, then domain ID. Reasons are bounded closed codes only.

Caller `max_domains` and `RetrievalBudget.max_domains` can lower the server
maximum, never raise it. Unknown hints do not create domains. Zero matches are
valid. The router is pure: no LLM, network, model, clock, filesystem/database
mutation, indexing, PSE, Task, or Decision mutation.

## Independent routing evidence

```text
GROUND_TRUTH: domain-routing-ground-truth-v1.json
HOLDOUT_LABELS: domain-routing-ground-truth-v1.holdout.json
GROUND_TRUTH_DIGEST: 434e10ca12d011c1b5cad8cacee086839102a02d3e53703d4ab6aef08a292c06
REVIEW_A_RECEIPT: 4c6899732be6b94640154d92e2dfa73bbc6526576971e3351dc3812c6053f65c
REVIEW_B_RECEIPT: 9fb75e89da11315b3741e4fe1c6880110b970f544c4e6a6b6336ed4764d9037f
ROUTER_OUTPUT_USED_FOR_GT: false
HOLDOUT_TUNING: forbidden
```

The verifier loads development labels, freezes policy/algorithm/normalization,
and only then opens the separate holdout-label artifact for admission
comparison. The holdout labels are never passed to a tuning function.

## Evaluation summary

See `domain-routing-evaluation-v1.json` and the offline verifier for per-query
digests and exact returned DTOs. The current observed run reports:

```text
DEVELOPMENT: 20 queries, precision 1.000, recall 1.000,
  required-domain recall 1.000, single top accuracy 12/12,
  multi coverage 5/5, zero-match correctness 3/3,
  false positives 0, explainability 1.000, max returned 3.
HOLDOUT: 20 queries, precision 1.000, recall 1.000,
  required-domain recall 1.000, single top accuracy 12/12,
  multi coverage 5/5, zero-match correctness 3/3,
  false positives 0, explainability 1.000, max returned 3.
HARD INVARIANTS: all zero.
```

Latency is evidence metadata only; no product threshold was invented from the
holdout. The algorithm and policy were frozen before the holdout pass.

## Candidate epochs

```text
EPOCH_0:
  BASE: dde1e1369c2d79d8f01b9fce21ae1fb55834a814
  TREE: 194d8c80dabb816bf8027ff097abc1b016dad317
  WHY: live protected main after Phase 5A.1 post-merge readback
EPOCH_1:
  PR: RESOLVE_FROM_GITHUB
  HEAD: RESOLVE_FROM_GITHUB
  TREE: RESOLVE_FROM_GITHUB
  PARENTS: RESOLVE_FROM_GITHUB
  WHY: Phase 5B runtime, evidence, governance, and security repairs
```

No future merge SHA is written into this candidate report.

## Current admission state

```text
LOCAL_FOCUSED_5B: PASS (45 tests across router/domain regressions)
LOCAL_FULL_HERMETIC: PASS (1921 passed, 4 skipped, 17 deselected; coverage 83.21%)
LOCAL_FULL_GATE: PASS
LOCKED_SYNC_AND_PIP_CHECK: PASS
RUFF_CHECK_AND_FORMAT: PASS
MYPY: PASS (119 files)
DOC_DRIFT: PASS
MKDOCS_STRICT: PASS (pre-existing warnings only)
COMPLEXITY_BUDGET: PASS
PIP_AUDIT: PASS / no known vulnerabilities
PACKAGE_SMOKE: PASS (wheel and sdist; version 3.7.11)
BENCHMARK_INTEGRITY: PASS (114 passed, 1 skipped)
MAINTENANCE_FAULT_GATE: PASS (9 passed)
BASE_RUNTIME_SMOKE: PASS
NEURAL_HERMETIC_CONTRACT: PASS (5 passed)
ROUTING_VERIFIER: PASS / all hard invariants zero
REMOTE_PR: NOT_CREATED
PHASE_5B: CANDIDATE / IN ADMISSION
NEXT_GATE: Phase 5C — SearchScope Pushdown
```
