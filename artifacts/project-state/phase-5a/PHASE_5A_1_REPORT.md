# POWER 3.8
# PHASE 5A.1 — RETRIEVAL EVALUATION CORPUS
# SEMANTIC INTEGRITY CORRECTION
# ADMISSION REPORT

## Gate result

```text
PHASE_5A_RUNTIME_CONTRACTS: CLOSED / MERGED / VERIFIED
PHASE_5A_1: CORRECTION CANDIDATE / PROTECTED MERGE REQUIRED
ACTIVE_EVALUATION_REVISION: v1.1 (candidate)
PHASE_5B: BLOCKED / NOT STARTED
POWER_3_8_0: NO-GO
```

This bounded gate audits and corrects evaluation semantics only. It does not
reopen the merged Phase 5A runtime contract gate and does not start Phase 5B.

## Live Phase 5A closure proof

Fresh GitHub REST verification recorded:

```text
PUBLIC_VERSION: 3.7.11
MAIN: 0a70ca4e9acc89596acd192931c1d174040ad484
MAIN_TREE: bffb0f5844a6eaee809a0b191aaa9346f6ccb408
MAIN_PARENTS: 9f732b1160f58e7ced88ebaa2fd52dd7c82da428 09a222b9c39d650d70aa116d9bce727d3cdbfe3b
PHASE5A_PR: #415
PHASE5A_FINAL_HEAD: 09a222b9c39d650d70aa116d9bce727d3cdbfe3b
PHASE5A_FINAL_TREE: bffb0f5844a6eaee809a0b191aaa9346f6ccb408
PHASE5A_MERGE: 0a70ca4e9acc89596acd192931c1d174040ad484
PHASE5A_GPG: verified=true / reason=valid
PHASE5A_REQUIRED_CHECKS: PASS
PHASE5A_CODEQL: PASS
PHASE5A_DOCS: PASS
```

PR #415 remains historical merged evidence. Its runtime contract and retrieval
behavior are not changed by this correction.

## Semantic audit result

Two independent reviewers inspected all 40 pairs before seeing each other's
results. The orchestrator adjudicated against the primary query, ground-truth,
source body, metadata, scenario-family, category, intent, authority, temporal,
and provenance evidence. The complete matrix is
`benchmarks/power38/retrieval_eval/v1.1/semantic-adjudication.md`; the immutable
machine receipt is `semantic-adjudication.json`.

```text
QUERIES_AUDITED: 40 / 40
FINAL_SEMANTIC_ALIGNMENT: PASS (40 / 40)
PROVEN_DEFECT_ROWS: 5
  holdout q06, q11, q16 — query wording reversed the intended current/curated target
  development + holdout q19 — GT pointed to cross-domain instead of direct infrastructure evidence
CORRECTED_AMBIGUOUS_ROWS: q10/q14/q15 in both splits, q20 in both splits
PRODUCT_DECISION_REQUIRED: NO
```

### q06, q11, q16

The development counterparts already asked for current/real/curated answers
and their GT was aligned. The holdout wording accidentally asked for the stale,
hard-negative, and explicitly unverified sources while the GT selected the
authoritative/current/curated winners. Per the correction policy, only the
holdout query wording was rewritten; the authoritative GT rows were preserved.

### q19

Both q19 queries directly ask about a host-neutral resource profile or the
deployment-only status of host facts. Only `p38-src-infra-current` states that
rule. Both GT rows were corrected to that source and their GT reasons and
provenance digests were regenerated. The source and query text were not changed.

The previously ambiguous q20 wording now names the verified cross-domain
admission projection, and the six q10/q14/q15 rows use
`temporal_expectation: not_applicable` because those queries ask about handling,
not source time.

### Query-sensitive authority rule

Authority ordering does not erase query intent. The eligible answer set is
determined first; authority/temporal/supersession/contradiction policy is then
applied within that set. Diagnostic queries may identify stale, hard-negative,
unverified, or quarantined evidence without promoting it to canonical truth.

## Revision and immutability

`benchmarks/power38/retrieval_eval/v1/` remains byte-identical and is explicitly
verified as historical structural evidence with semantic status
`SUPERSEDED_ERRATUM`. `v1.1/` is a complete source-preserving revision with an
explicit manifest identity; no newest-directory discovery is used.

The new revision binds `semantic-adjudication.json` and the exact Markdown
rationale hash into `dataset_digest`. The source corpus digest remains
unchanged. The full old-byte baseline is `v1-immutability-proof.json`.

## v1.1 digest set

```text
SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
DATASET_DIGEST: d3e9f0c0697e18572d9149a9c38bf6b02b72b44927d0fab481bd9cd74203fc4d
QUERY_SET_DIGEST: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
DEVELOPMENT_DIGEST: 4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95
HOLDOUT_DIGEST: 61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551
DISJOINTNESS_DIGEST: cf8054395040f17e4d21a005e248b7804fd515cc555b12b52b0afca0f32376d4
SEMANTIC_ADJUDICATION_DIGEST: 0c1c2b32cb6ad84413dddfc93fe73777a37ba735468614a49afd97fc11784c48
SEMANTIC_ADJUDICATION_MARKDOWN_DIGEST: 7ee822bdb11db3497bf0057fe1df3a4aa9eb5ddfa44ce1e5db191bf5f3f24c60
GROUND_TRUTH_PROVENANCE_DIGEST: f307f47eb2eea70942fb114e5a41819db44bd9a614251946ef4e530118953b6c
HOLDOUT_ACCESS_RECEIPT_DIGEST: e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997
REVIEWER_A_RECEIPT_DIGEST: 8d19e3c56ee2d85062ccebcbb6397dd0a8de7ec62c4a1df14d0a3630b15dc158
REVIEWER_B_RECEIPT_DIGEST: 14a4549f67b6efc40489a5e708fd0eafa35f464f94e5aa7d1153969db783c7b7
```

Historical v1 digest values are retained in the erratum and immutability proof.

## Validation boundary

The verifier is offline, model-free, and network-free. It proves structural and
byte-level integrity, source/reference safety, split disjointness, coverage,
receipt binding, and reproducible digests. It cannot mathematically prove
natural-language ground truth correctness:

```text
STRUCTURAL INTEGRITY != SEMANTIC ADJUDICATION
```

The semantic pass is therefore a separate evidence requirement: two independent
reviews plus primary-fixture orchestrator adjudication. This is dataset curation
before Phase 5B, not model tuning.

## Scope proof

```text
PHASE5A_RUNTIME_CONTRACT_REWRITE: NO
DOMAIN_POLICY_V2: NO
MULTI_DOMAIN_ROUTER: NO
SEARCHSCOPE_PUSHDOWN: NO
RETRIEVALPLANNER: NO
CONTEXTPACKCOMPILER: NO
DENSE_OR_INDEX_BEHAVIOR: NO
MCP_CONTEXT_TOOLS: NO
CAPTURE: NO
VECTOR_DATABASE: NO
VERSION_TAG_RELEASE: NO
```

## Phase 5B preflight findings

These are handoff requirements, not implementation in this gate:

```text
5B-SEC-01: POWER_DOMAIN_CONFIG must enforce vault containment for explicit paths.
5B-ARCH-01: legacy route_domain remains deterministic single-domain placement behavior.
5B-ARCH-02: retrieval-domain multi-match routing is a separate API, not a placement replacement.
5B-ARCH-03: source-membership selectors and free-text query-routing signals are separate.
5B-ARCH-04: deterministic no-LLM/model router is the required default.
5B-ARCH-05: policy v2 must not execute 5C/5D/5F behavior in the 5B gate.
5B-EVAL-01: routing precision/recall needs independently adjudicated expected-domain labels.
```

## Admission

Local validation evidence for this candidate:

```text
LOCK_AND_ENV: uv lock --check / uv sync --locked / pip check = PASS
TARGETED_PHASE5A1: 34 passed (--no-cov)
FULL_HERMETIC: 1882 passed, 4 skipped, 17 deselected; coverage 83.36%
BENCHMARK_INTEGRITY: 114 passed, 1 skipped
OUTCOME_AND_CONTINUITY: PASS
UPGRADE_MATRIX: PASS (Linux supported; macOS/Windows explicitly deferred)
PACKAGE_SMOKE: PASS (wheel and sdist)
RUFF_CHECK: PASS
RUFF_FORMAT: PASS
MYPY: PASS (118 files)
DOC_DRIFT: PASS
MKDOCS_STRICT: PASS (pre-existing warnings only)
PIP_AUDIT: PASS / no known vulnerabilities
V1_VERIFIER: PASS / SUPERSEDED_ERRATUM
V1.1_VERIFIER: PASS / SEMANTIC_ADJUDICATION_PASS
```

The correction candidate is ready for one protected normal merge after exact-head
validation, required contexts, review, GPG, and remote checks. After that single
merge and post-merge readback, v1.1 becomes the active revision for future Phase
5 evaluation and Phase 5B becomes ready/not started. No Phase 5B work is
authorized in this gate.

## Adversarial-review reconciliation

The adversarial review found and this candidate repaired: q20 semantic ambiguity,
immutable v1 inventory/bytes, cross-split ground-truth ownership, active source
digest binding, canonical v1.1 per-row provenance, Markdown rationale binding,
the missing dedicated Gate 5A.1 contract, and CLI/revision regression coverage.

Two findings remain intentionally outside this bounded gate. The pre-existing
`RuntimeContractEnvelope` optional-registration import-order behavior would
require a `context_contracts.py` runtime-contract change, while this gate is
required to leave that Phase 5A runtime module unchanged. The historical
`PHASE_5A_REPORT.md` is append-only evidence and is not rewritten; this erratum,
the v1.1 report, and the latest handoff are the explicit corrective projection.
Neither item changes v1.1 corpus integrity or semantic adjudication.
