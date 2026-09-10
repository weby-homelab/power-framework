# POWER 3.8 Phase 5A Runtime Contracts and Evaluation Handoff

> Append-only candidate handoff. This is not `MERGED MAIN` evidence until the
> exact candidate passes protected GitHub admission and is read back after one
> normal merge.

## Project

```text
PROJECT: POWER Framework 3.8
REPOSITORY: https://github.com/weby-homelab/power-framework
PUBLIC_VERSION: 3.7.11
ACTIVE_NODE: WS
CHECKOUT: /root/gemma/projects/P.O.W.E.R
BRANCH: feat/power-3.8-phase5a-runtime-contracts
```

## Starting protected main and Foundation proof

```text
STARTING_MAIN: 9f732b1160f58e7ced88ebaa2fd52dd7c82da428
STARTING_TREE: 52aa98950b4c2f371b8f63f906deec16d31c2e48
STARTING_PARENTS: 95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a 96f0b1cc0e1fc85e0921c9518761683266e3f9ae
FOUNDATION_PR: #414
FOUNDATION_FINAL_HEAD: 96f0b1cc0e1fc85e0921c9518761683266e3f9ae
FOUNDATION_MERGE: 9f732b1160f58e7ced88ebaa2fd52dd7c82da428
FOUNDATION_TREE: 52aa98950b4c2f371b8f63f906deec16d31c2e48
FOUNDATION_GPG: verified=true / reason=valid
POST_MERGE_CI: PASS
POST_MERGE_DOCS: PASS
POST_MERGE_CODEQL: PASS
```

## Phase 5A candidate

```text
RUNTIME_CONTRACT_MODULE: src/power_framework/core/context_contracts.py
EVALUATION_MODULE: src/power_framework/core/evaluation_contracts.py
RUNTIME_CONTRACT_VERSION: power.context-runtime.v2
EVALUATION_CORPUS: benchmarks/power38/retrieval_eval/v1
PHASE5A_REPORT: artifacts/project-state/phase-5a/PHASE_5A_REPORT.md
RUNTIME_MAPPING: artifacts/project-state/phase-5a/runtime-contract-mapping.md
FINAL_CANDIDATE_HEAD: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_TREE: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_PARENTS: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_GPG: RESOLVE_FROM_GITHUB
```

## Frozen evidence

```text
SOURCE_FIXTURES: 20
DEVELOPMENT_QUERIES: 20
HOLDOUT_QUERIES: 20
DATASET_DIGEST: 179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0
SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
QUERY_SET_DIGEST: 7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086
DEVELOPMENT_DIGEST: 29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289
HOLDOUT_DIGEST: ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a
DISJOINTNESS_DIGEST: 554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275
HOLDOUT_POLICY: SEALED / NOT SECRET / NO TUNING
```

## Validation receipt

```text
TARGETED_PHASE5A: 55 passed
FULL_HERMETIC: 1868 passed, 4 skipped, 17 deselected
COVERAGE: 83.33%
FOUNDATION_TARGETED: 91 passed
PSE_TASK_DECISION_CRASH: 177 passed
RETRIEVAL_SECURITY: 88 passed
BENCHMARK_INTEGRITY: 114 passed, 1 skipped
UPGRADE_MATRIX: PASS
PACKAGE_SMOKE: PASS
RUFF_FORMAT_MYPY: PASS
DOCS_CODEQL_REMOTE: PENDING EXACT PR HEAD
```

## Next gate and stop

```text
PHASES_0_4: CLOSED / FROZEN
CONTROLLED_DEPENDENCY_REFRESH: CLOSED
FOUNDATION_HARDENING: CLOSED / IMPLEMENTED / VERIFIED
PHASE_5: IN PROGRESS
PHASE_5A: IMPLEMENTED / LOCALLY VERIFIED / PROTECTED MERGE REQUIRED
PHASE_5B: READY FOR SEPARATE ADMISSION / NOT STARTED
PHASE_5C_5H: NOT STARTED
PHASES_6_9: NOT STARTED
POWER_3_8_0: NO-GO
OPEN_BLOCKERS: protected GitHub PR/check/review/merge readback not yet performed
HUMAN_ACTION_REQUIRED: NO
ADMIN_BYPASS: NO
PROTECTION_BYPASS: NO
FORCE: NO
AUTO_MERGE: NO
NEXT_GATE: Phase 5A protected exact-head admission, then Phase 5B separate admission
```

Next agent instruction: read live `main`, this report, the runtime mapping,
frozen manifest, and this handoff; independently verify every digest and the
exact candidate tuple before creating the PR. Do not start Phase 5B router,
SearchScope pushdown, RetrievalPlanner behavior, dense-index work, MCP context
tools, capture, or later phases.
