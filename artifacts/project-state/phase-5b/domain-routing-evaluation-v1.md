# POWER 3.8 Phase 5B — Domain Routing Evaluation v1

## Evidence identity

```text
EVALUATION_REVISION: v1.1
ROUTER_ALGORITHM_REVISION: domain-router-v1
POLICY_REVISION: phase5b-routing-v1
NORMALIZATION_REVISION: nfkc-casefold-tokens-v1
POLICY_SHA256: f728a27fd8c009c9dd18c01c2afc5399368c3663eb97cc645ec22896efe8f88b
ROUTING_GROUND_TRUTH_SHA256: 434e10ca12d011c1b5cad8cacee086839102a02d3e53703d4ab6aef08a292c06
```

The active v1.1 source, dataset, query-set, development, and holdout digests
are copied from the immutable `benchmarks/power38/retrieval_eval/v1.1/manifest.json`:

```text
SOURCE_CORPUS: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
DATASET: 5d8f2d7e68b62b3a2385c7a534a492083e1ff1b9f68973d4cbe8bf64461521fc
QUERY_SET: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
DEVELOPMENT: 4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95
HOLDOUT: 61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551
```

The machine-readable result is
`domain-routing-evaluation-v1.json`. Recompute it with:

```bash
uv run --offline python scripts/verify_domain_routing.py
```

The verifier is offline, model-free, retrieval-free, and does not mutate the
repository, configured vault, database, refs, or remote state. It uses bounded
temporary fixtures for the legacy compatibility and containment probes. The
latency values below are observations from one bounded WS run, not acceptance
thresholds or router inputs.

## Independent ground truth

`domain-routing-ground-truth-v1.json` is a separate artifact. Two independent
read-only semantic reviewers examined query text, intent/category, v1.1 source
fixtures, source metadata, scenario family, and approved domain semantics
before seeing router output. The orchestrator adjudicated disagreements. No
router output, score, embedding, model, threshold, or retrieval metric was used
to create the labels. No floating-point score is human ground truth.

The adjudication keeps semantic domain and trust/lifecycle axes orthogonal:
`RAW`, `CANONICAL`, `SUPERSEDED`, `QUARANTINED`, and `NOISE` are not domains.
Queries asking to reveal secrets, execute notes, or change scope therefore have
zero domain matches. Quarantine is not a delete or routing instruction.

The principal adjudication points were:

- authority/contradiction queries require both `governance` and `decisions`,
  with the explicit query intent selecting the expected primary domain;
- quarantine handling remains zero-domain because it is a lifecycle/policy
  concern, not a semantic domain;
- the verified admission-package queries require
  `project_state`, `tasks`, and `infrastructure`; `governance` is acceptable
  diagnostic context.

## Frozen router algorithm

The policy declares integer score units:

```text
keyword signal: 50
intent signal: 30
caller hint signal: 20
total: 100
minimum inclusion score: 0.20
low-confidence boundary: 0.20
server maximum: 4 domains
tie policy: descending score, explicit policy order, canonical domain ID
```

For each registered domain, each signal bucket contributes at most once:

1. normalize query and configured keywords with Unicode NFKC, casefold, format
   and control-character handling, and bounded whitespace;
2. tokenize into literal Unicode word tokens; configured keywords are literal
   token sequences, never regular expressions or substring path selectors;
3. add the keyword unit when any configured keyword phrase occurs;
4. add the intent unit when the validated intent is declared by the domain;
5. add the caller-hint unit when a canonical registered domain ID is hinted;
6. divide the integer sum by 100 and include scores at or above the inclusive
   minimum;
7. add only bounded closed reason codes (`keyword_signal`, `intent_signal`,
   `caller_hint_signal`, conflict/low-confidence codes), never query/source
   text or authority claims;
8. sort by `(-score_units, policy_index, domain_id)` and return at most the
   effective maximum `min(server_max, budget.max_domains, caller_max_domains)`.

Unknown hints do not mint domains. A conflicting hint is a signal, not an
override: lexical and intent candidates remain independently scored and the
conflict is represented by a bounded reason. A caller maximum can lower the
server cap but cannot raise it. An empty result is valid.

`SourceDomainClassifier` is separate. It consumes only a safe relative source
path, source tags, and source type, and returns zero or more
`SourceDomainMembership` values. It never consumes query text. Its path/tag/type
reasons are not `DomainMatch` query reasons.

The v1 `route_domain()` and `resolve_search_policy()` APIs remain single-domain
placement/legacy policy APIs. They were not replaced by the router, and no 5C
candidate filtering or scope pushdown was added.

## Development split

```text
QUERIES: 20
RETURNED_MATCHES: 25
REQUIRED_DOMAIN_COUNT: 23
REQUIRED_DOMAIN_HITS: 23
SINGLE-DOMAIN CASES: 12 / 12 top-domain hits
MULTI-DOMAIN CASES: 5 / 5 complete required-domain coverage
ZERO-MATCH CASES: 3 / 3 correct
ROUTING_PRECISION: 1.000
ROUTING_RECALL: 1.000
REQUIRED_DOMAIN_RECALL: 1.000
TOP-DOMAIN_ACCURACY_UNAMBIGUOUS_SINGLE: 1.000 (12 / 12)
UNEXPECTED_DOMAIN_FALSE_POSITIVES: 0
MULTI-DOMAIN_COVERAGE: 1.000 (5 / 5)
ZERO-MATCH_CORRECTNESS: 1.000 (3 / 3)
TIE_DETERMINISM: PASS
EXPLAINABILITY_COVERAGE: 1.000
MAXIMUM_RETURNED_DOMAINS: 3
P50_ROUTING_LATENCY: 299.816 us (observed run)
P95_ROUTING_LATENCY: 334.073 us (observed run)
RESULTS_DIGEST: 81b8f675baa667b424e46451cf6c52f3355081e7cacedec48855a70e62eaf09b
```

## Final holdout admission evaluation

The algorithm, weights, thresholds, normalization, policy revision, and ground
truth were frozen before the holdout pass. Holdout labels were read only for
admission comparison; they were not used to alter any number or policy field.

```text
QUERIES: 20
RETURNED_MATCHES: 27
REQUIRED_DOMAIN_COUNT: 24
REQUIRED_DOMAIN_HITS: 24
SINGLE-DOMAIN CASES: 12 / 12 top-domain hits
MULTI-DOMAIN CASES: 5 / 5 complete required-domain coverage
ZERO-MATCH CASES: 3 / 3 correct
ROUTING_PRECISION: 1.000
ROUTING_RECALL: 1.000
REQUIRED_DOMAIN_RECALL: 1.000
TOP-DOMAIN_ACCURACY_UNAMBIGUOUS_SINGLE: 1.000 (12 / 12)
UNEXPECTED_DOMAIN_FALSE_POSITIVES: 0
MULTI-DOMAIN_COVERAGE: 1.000 (5 / 5)
ZERO-MATCH_CORRECTNESS: 1.000 (3 / 3)
TIE_DETERMINISM: PASS
EXPLAINABILITY_COVERAGE: 1.000
MAXIMUM_RETURNED_DOMAINS: 3
P50_ROUTING_LATENCY: 300.813 us (observed run)
P95_ROUTING_LATENCY: 332.440 us (observed run)
RESULTS_DIGEST: 8aa4120a8c01355269cbd3d2cc203ffb0139f0ccd5231458986e8a540e7fa232
```

## Hard invariants

```text
AUTHORITY_VIOLATIONS: 0
LIFECYCLE_VIOLATIONS: 0
VAULT_BOUNDARY_ESCAPES: 0
NON_DETERMINISTIC_OUTPUTS: 0
UNEXPLAINED_DOMAIN_MATCHES: 0
HOLDOUT_TUNING_VIOLATIONS: 0
LEGACY_V1_REGRESSIONS: 0
```

These counts are backed by the focused Phase 5B test matrix, the immutable
active-corpus verifier, and the offline routing verifier. Domain policy fields
for authority preference, noise, traversal, and index priority are parsed as
bounded inert declarations only. They do not reorder evidence, suppress
sources, enqueue indexing, change trust/lifecycle, or mutate PSE/Task/Decision
state.
