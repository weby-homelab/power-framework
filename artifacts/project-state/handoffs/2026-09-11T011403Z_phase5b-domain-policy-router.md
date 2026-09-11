# POWER 3.8 Phase 5B Domain Policy / Router Handoff

> Append-only candidate handoff. This record is not merged-main evidence until
> the exact candidate passes protected GitHub admission, one normal protected
> merge, and independent post-merge readback.

## Recovery anchor

```text
PROJECT: POWER Framework 3.8
REPOSITORY: https://github.com/weby-homelab/power-framework
ACTIVE_NODE: WS
CHECKOUT: /root/gemma/projects/P.O.W.E.R
BRANCH: feat/power-3.8-phase5b-domain-policy-router
PUBLIC_VERSION: 3.7.11
```

```text
STARTING_MAIN: dde1e1369c2d79d8f01b9fce21ae1fb55834a814
STARTING_TREE: 194d8c80dabb816bf8027ff097abc1b016dad317
STARTING_PARENTS:
  0a70ca4e9acc89596acd192931c1d174040ad484
  94e2e08a2d37884b90ac895de35979fa87696bd5
STARTING_VERIFICATION: verified=true / reason=valid
PHASE_5A: CLOSED / MERGED / VERIFIED / PR #415
PHASE_5A_1: CLOSED / MERGED / VERIFIED / PR #416 / MERGE dde1e1369c2d...
```

## Implemented candidate scope

- strict bounded v2 parser plus inert retrieval/traversal/index/noise/authority
  metadata;
- v1-compatible placement/search APIs and explicit v1-to-router adapter;
- vault containment and descriptor-relative no-follow config/template/placement
  handling;
- separate source classifier and pure deterministic retrieval router;
- import-order deterministic `RuntimeContractEnvelope` repair;
- independent routing GT, development/holdout verifier, report, and tests.

5C and later behavior remains untouched: no scope pushdown, retrieval ranking,
planner/context pack, index queue, MCP context tools, capture, release, or
version bump.

## Frozen evidence

```text
ACTIVE_EVALUATION_REVISION: v1.1
ACTIVE_SOURCE_CORPUS: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
ACTIVE_DATASET: 5d8f2d7e68b62b3a2385c7a534a492083e1ff1b9f68973d4cbe8bf64461521fc
ACTIVE_QUERY_SET: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
ACTIVE_DEVELOPMENT: 4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95
ACTIVE_HOLDOUT: 61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551
ROUTING_GT: 434e10ca12d011c1b5cad8cacee086839102a02d3e53703d4ab6aef08a292c06
POLICY_REVISION: phase5b-routing-v1
POLICY_SHA256: f728a27fd8c009c9dd18c01c2afc5399368c3663eb97cc645ec22896efe8f88b
```

Ground truth was reviewed independently by two read-only semantic reviewers;
router output was not used. Development labels are loaded before the candidate
freeze, and the separate holdout label file is opened only for post-freeze
admission comparison.

## Pre-admission validation

```text
FOCUSED_PHASE5B: PASS (45 tests across router/domain regressions)
RUFF_TARGETED: PASS
RUFF_FORMAT_TARGETED: PASS
MYPY_SOURCE: PASS (119 files)
ROUTING_VERIFIER: PASS / all hard invariants zero
LOCAL_FULL_HERMETIC: PASS (1921 passed, 4 skipped, 17 deselected; coverage 83.21%)
FULL_GATE: PASS
LOCKED_SYNC_AND_PIP_CHECK: PASS
DOC_DRIFT_MKDOCS: PASS
COMPLEXITY_BUDGET: PASS
PIP_AUDIT: PASS / no known vulnerabilities
PACKAGE_SMOKE: PASS (wheel and sdist)
BENCHMARK_INTEGRITY: PASS (114 passed, 1 skipped)
MAINTENANCE_FAULT_GATE: PASS (9 passed)
BASE_RUNTIME_SMOKE: PASS
NEURAL_HERMETIC_CONTRACT: PASS (5 passed)
GPG_CANDIDATE: PENDING
REMOTE_PR: PENDING
```

## Candidate epoch and next action

```text
EPOCH_0_BASE: dde1e1369c2d79d8f01b9fce21ae1fb55834a814
EPOCH_1_HEAD: RESOLVE_FROM_GITHUB
EPOCH_1_TREE: RESOLVE_FROM_GITHUB
EPOCH_1_PARENTS: RESOLVE_FROM_GITHUB
EPOCH_1_WHY: bounded Phase 5B implementation and adversarial repairs
```

Next operator action: inspect the complete diff, run the repository-equivalent
locked validation and full regression matrix, obtain final fresh exact-head
REST evidence, create the preferred PR, and stop if any protected gate is not
objectively green. Never push directly to `main`, rewrite v1/v1.1, or use an
admin/protection bypass.

## Recovery stop line

```text
Phase 5B is not closed yet. Phase 5C remains unstarted pending independent
protected admission and post-merge readback.
```
