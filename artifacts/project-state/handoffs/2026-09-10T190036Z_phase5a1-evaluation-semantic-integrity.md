# POWER 3.8 Phase 5A.1 Evaluation Semantic-Integrity Handoff

> Append-only candidate handoff. This record is not `MERGED MAIN` evidence until
> the exact candidate passes protected GitHub admission, one normal merge, and
> independent post-merge readback.

## Project and starting point

```text
PROJECT: POWER Framework 3.8
REPOSITORY: https://github.com/weby-homelab/power-framework
PUBLIC_VERSION: 3.7.11
ACTIVE_NODE: WS
CHECKOUT: /root/gemma/projects/P.O.W.E.R
BRANCH: fix/power-3.8-phase5a1-eval-semantic-integrity
```

```text
STARTING_MAIN: 0a70ca4e9acc89596acd192931c1d174040ad484
STARTING_TREE: bffb0f5844a6eaee809a0b191aaa9346f6ccb408
STARTING_PARENTS: 9f732b1160f58e7ced88ebaa2fd52dd7c82da428 09a222b9c39d650d70aa116d9bce727d3cdbfe3b
```

## Phase 5A proof

```text
PHASE5A_PR: #415
PHASE5A_RUNTIME_CONTRACTS: CLOSED / MERGED / VERIFIED
PHASE5A_FINAL_HEAD: 09a222b9c39d650d70aa116d9bce727d3cdbfe3b
PHASE5A_FINAL_TREE: bffb0f5844a6eaee809a0b191aaa9346f6ccb408
PHASE5A_MERGE: 0a70ca4e9acc89596acd192931c1d174040ad484
PHASE5A_MERGE_TREE: bffb0f5844a6eaee809a0b191aaa9346f6ccb408
PHASE5A_MERGE_PARENTS: 9f732b1160f58e7ced88ebaa2fd52dd7c82da428 09a222b9c39d650d70aa116d9bce727d3cdbfe3b
PHASE5A_GPG: verified=true / reason=valid
PHASE5A_REQUIRED_CONTEXTS: PASS
PHASE5A_DOCS: PASS
PHASE5A_CODEQL: PASS
```

## Semantic defects and correction

Independent reviewers A and B audited all 40 queries without seeing each
other's verdict. Primary-fixture adjudication confirmed:

```text
REAL_HOLDOUT_DEFECTS: p38-ho-q06, p38-ho-q11, p38-ho-q16
ADDITIONAL_GT_DEFECTS: p38-dev-q19, p38-ho-q19
CORRECTED_AMBIGUOUS_ROWS: p38-dev-q10, p38-dev-q14, p38-dev-q15, p38-dev-q20, p38-ho-q10, p38-ho-q14, p38-ho-q15, p38-ho-q20
FINAL_QUERY_40_AUDIT: PASS
SEMANTIC_ADJUDICATION: PASS
```

The holdout q06/q11/q16 queries were rewritten toward current/real/curated
answers while their authoritative GT rows remained unchanged. Both q19 GT rows
were corrected to `p38-src-infra-current`; q19 GT reasons and per-row provenance
digests were regenerated. q20 wording was clarified toward the verified
cross-domain projection, and the six q10/q14/q15 temporal labels were corrected
to `not_applicable`; neither change used implementation output.

```text
PRIOR_CODERABBIT_CLASSIFICATION: NON-ACTIONABLE
CORRECTED_CLASSIFICATION: VALID / ACTIONABLE
ERRATUM: artifacts/project-state/phase-5a/EVALUATION_CORPUS_V1_ERRATUM.md
MATRIX: benchmarks/power38/retrieval_eval/v1.1/semantic-adjudication.md
MACHINE_ADJUDICATION: benchmarks/power38/retrieval_eval/v1.1/semantic-adjudication.json
```

## Historical v1 and active v1.1 digests

```text
HISTORICAL_V1_STATUS: RETAINED / STRUCTURAL PASS / SEMANTIC ERRATUM
V1_DATASET_DIGEST: 179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0
V1_SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
V1_QUERY_SET_DIGEST: 7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086
V1_DEVELOPMENT_DIGEST: 29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289
V1_HOLDOUT_DIGEST: ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a
V1_DISJOINTNESS_DIGEST: 554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275
```

```text
ACTIVE_EVALUATION_REVISION: v1.1
ACTIVE_SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
ACTIVE_DATASET_DIGEST: d3e9f0c0697e18572d9149a9c38bf6b02b72b44927d0fab481bd9cd74203fc4d
ACTIVE_QUERY_SET_DIGEST: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
ACTIVE_DEVELOPMENT_DIGEST: 4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95
ACTIVE_HOLDOUT_DIGEST: 61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551
ACTIVE_DISJOINTNESS_DIGEST: cf8054395040f17e4d21a005e248b7804fd515cc555b12b52b0afca0f32376d4
ACTIVE_SEMANTIC_ADJUDICATION_DIGEST: 0c1c2b32cb6ad84413dddfc93fe73777a37ba735468614a49afd97fc11784c48
ACTIVE_SEMANTIC_ADJUDICATION_MARKDOWN_DIGEST: 7ee822bdb11db3497bf0057fe1df3a4aa9eb5ddfa44ce1e5db191bf5f3f24c60
ACTIVE_GROUND_TRUTH_PROVENANCE_DIGEST: f307f47eb2eea70942fb114e5a41819db44bd9a614251946ef4e530118953b6c
ACTIVE_HOLDOUT_ACCESS_RECEIPT_DIGEST: e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997
REVIEWER_A_RECEIPT_DIGEST: 8d19e3c56ee2d85062ccebcbb6397dd0a8de7ec62c4a1df14d0a3630b15dc158
REVIEWER_B_RECEIPT_DIGEST: 14a4549f67b6efc40489a5e708fd0eafa35f464f94e5aa7d1153969db783c7b7
```

`v1/` was not edited. The 29-file baseline is in
`artifacts/project-state/phase-5a/v1-immutability-proof.json`. Structural
integrity and semantic adjudication are separate claims.

## Candidate epochs

```text
EPOCH_0:
  BASE=0a70ca4e9acc89596acd192931c1d174040ad484
  TREE=bffb0f5844a6eaee809a0b191aaa9346f6ccb408
  PARENTS=9f732b1160f58e7ced88ebaa2fd52dd7c82da428,09a222b9c39d650d70aa116d9bce727d3cdbfe3b
  WHY=verified protected Phase 5A merge; start one bounded correction gate
EPOCH_1:
  BASE=0a70ca4e9acc89596acd192931c1d174040ad484
  HEAD=RESOLVE_FROM_GITHUB
  TREE=RESOLVE_FROM_GITHUB
  PARENTS=RESOLVE_FROM_GITHUB
  WHY=semantic corpus revision, verifier revision-awareness, governance reconciliation
```

Changed artifact scope is limited to the new v1.1 corpus, evaluation verifier
revision mapping/tests, planning acceptance wording, state/roadmap/architecture
reconciliation, erratum, report, immutability proof, and this handoff. No
dependency, lock, workflow, source fixture, retrieval implementation, index,
model, MCP, or public-version change is included.

Adversarial review's pre-existing `RuntimeContractEnvelope` optional-registration
import-order issue is not changed because it requires `context_contracts.py`,
which is explicitly out of scope for this correction. The historical
`PHASE_5A_REPORT.md` remains untouched; its stale candidate narrative is
superseded by the erratum and this handoff rather than rewritten.

## Validation status before remote admission

```text
V1_VERIFIER: PASS
V1.1_VERIFIER: PASS
V1.1_EXPECTED_REVISION_GUARD: PASS
PHASE5A1_TARGETED_TESTS: 34 passed (--no-cov)
SOURCE_CORPUS_BYTE_COMPARISON: PASS (20/20)
V1_IMMUTABILITY_BASELINE: PASS (29/29 files)
FULL_REGRESSION: 1882 passed, 4 skipped, 17 deselected; coverage 83.36%
BENCHMARK_INTEGRITY: 114 passed, 1 skipped
OUTCOME_AND_CONTINUITY: PASS
UPGRADE_MATRIX: PASS (Linux; unsupported macOS/Windows deferred)
PACKAGE_SMOKE: PASS (wheel and sdist)
RUFF_FORMAT_MYPY_DOC_DRIFT_MKDOCS_PIP_AUDIT: PASS
REMOTE_CHECKS: PENDING_PR
GPG: PENDING_FINAL_COMMIT
```

## Phase 5B preflight findings

```text
5B-SEC-01: revalidate/enforce POWER_DOMAIN_CONFIG containment inside the vault.
5B-ARCH-01: preserve deterministic single-domain legacy placement routing.
5B-ARCH-02: expose retrieval multi-domain routing as a separate bounded API.
5B-ARCH-03: separate source-membership selectors from free-text query-routing signals.
5B-ARCH-04: deterministic no-LLM/model router remains the default requirement.
5B-ARCH-05: do not execute 5C/5D/5F behavior in the 5B gate.
5B-EVAL-01: adjudicate expected DomainMatch/domain labels independently before metrics.
```

## Merge and next gate

```text
PR: RESOLVE_FROM_GITHUB
FINAL_HEAD: RESOLVE_FROM_GITHUB
FINAL_TREE: RESOLVE_FROM_GITHUB
FINAL_PARENTS: RESOLVE_FROM_GITHUB
GPG: RESOLVE_FROM_GITHUB
MERGE: RESOLVE_FROM_GITHUB
POST_MERGE_READBACK: RESOLVE_FROM_GITHUB
ADMIN_BYPASS: NO
PROTECTION_BYPASS: NO
FORCE: NO
AUTO_MERGE: NO
```

Next gate after protected closure: Phase 5B — Domain Policy v2 plus
Deterministic Multi-domain Router Admission, starting from corrected v1.1.
Phase 5B is not started by this handoff.
