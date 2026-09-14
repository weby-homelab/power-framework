# POWER 3.8 INFRA-1 — Constrained Local Infrastructure Execution Broker

> Append-only provisional handoff. This record becomes `MERGED MAIN` evidence
> only after the exact candidate passes protected admission, one normal merge,
> and independent post-merge readback.

## Recovery anchor

```text
PROJECT: POWER Framework 3.8
REPOSITORY: https://github.com/weby-homelab/power-framework
PUBLIC_VERSION: 3.7.11
BRANCH: feat/power-3.8-infra-execution-broker
ACTIVE_GATE: INFRA-1 — Constrained Local Infrastructure Execution Broker
NEXT_GATE: Phase 5C — SearchScope Pushdown
TRANSFER_PR: #419 / https://github.com/weby-homelab/power-framework/pull/419
```

```text
STARTING_MAIN: 6a315d5919eeef797bc506ecb216313c20419fc2
STARTING_TREE: a03b90648e1e57c5a579e5834988015192027cb0
STARTING_PARENTS:
  dde1e1369c2d79d8f01b9fce21ae1fb55834a814
  887f8319b70c4e7be98d503d53924a70ad211c38
STARTING_GPG: verified=true / reason=valid
STARTING_PROTECTION: strict=true; 11 required contexts; force/deletion disabled
```

## Phase 5B bounded erratum

Live GitHub confirms Phase 5B is closed by PR #418 and merge
`6a315d5919eeef797bc506ecb216313c20419fc2`. Candidate head
`887f8319b70c4e7be98d503d53924a70ad211c38` has actual parent
`12dda70c8badbbff723971d023206574b4130b64`. The protected merge parents are
the Phase 5A.1 main `dde1e1369c2d79d8f01b9fce21ae1fb55834a814` and that candidate
head. A different parent in the historical narrative is retained as a bounded
reporting typo; historical Phase 5B files are not rewritten.

## Dependency boundary

PR #417 is open maintenance work with a separate dependency graph and a failed
`package-smoke` check on its head `49d88950dfa266b0f6c53c167ddbbfcf3e956ce2`.
It is not merged, rebased, modified, or bundled into INFRA-1. No dependency
ranges, `uv.lock`, HF/model ranges, MCP dependency, NumPy/Pydantic pair, or
ONNX/GPU graph is changed by this gate.

## INFRA-1 scope

Implemented candidate boundary:

- strict `InfraRequest` with only `status`, `probe`, `rsync-dry-run`,
  `replicate`, and `verify`;
- bounded Unix socket framing and OS peer-principal derivation;
- operator profile schema with target/source/receiver/host-key/credential
  allowlists, resource bounds, dry-run policy, and approval policy;
- fixed noninteractive SSH options and fixed rsync argv; no shell, arbitrary
  host/path/command/options, password fallback, or inherited ssh-agent;
- source manifest containment with symlink/hardlink/special-file rejection;
- immutable run/staging semantics, idempotency replay/conflict handling,
  bounded secret-free receipts, and optional service receipt persistence;
- ApplicationService Task projection: capability absence → `blocked`, approval
  absence → `auth-required`, genuine missing request datum → `input-required`;
- static capability IDs plus separate dynamic `power infra status`;
- one typed MCP tool `infra_action` and operator CLI client;
- opt-in non-root systemd service, profile example, receiver/rrsync reference,
  ADR, threat-model and security-boundary documentation.

Not implemented or admitted: arbitrary shell/SSH, restore, delete/prune,
remote sudo/package/firewall/lifecycle, Ansible/Terraform, Phase 5C retrieval
scope pushdown, version/tag/release changes, or real-host provisioning.

## Security invariants

```text
DIRECT_ARBITRARY_SSH_FROM_AGENT: DENIED
ARBITRARY_REMOTE_SHELL: DENIED
PASSWORD_AUTH_FALLBACK: DENIED
PRIVATE_KEY_IN_LLM_CONTEXT: DENIED
BROKER_UNAVAILABLE: BLOCKED / MISSING_EXECUTION_CAPABILITY
```

Handoff text remains data and cannot execute an infra action. The receiver is a
dedicated non-root forced `rrsync` account with `restrict`, no forwarding/PTY,
no-delete, and optional stable-source `from=` defense in depth.

## Candidate epoch

```text
EPOCH_0_BASE: 6a315d5919eeef797bc506ecb216313c20419fc2
EPOCH_1_HEAD: dcf27b55e3e5bfeb285fc93ed73a485ce0f707fb
EPOCH_1_TREE: 85a84c6e9158dc98168dc9e7a1dff03259aba90b
EPOCH_1_PARENTS: 6a315d5919eeef797bc506ecb216313c20419fc2
EPOCH_1_WHY: INFRA-1 broker/client/task/MCP/CLI/security/docs implementation
EPOCH_1_GPG: verified=true / reason=valid / fingerprint=2D49E810C7F2527E
```

## Local evidence at handoff creation

```text
FOCUSED_INFRA_TESTS: PASS (18 hermetic broker tests plus application/CLI/MCP slices)
RUFF_TARGETED: PASS
MYPY_TARGETED: PASS
DOC_DRIFT: PASS with POWER_GLOBAL_SKILL_PATH pinned to repository skill;
  unmodified host-global copies are stale and are not repository evidence
REAL_HOST_CREDENTIAL: deployment evidence unavailable; not requested
REAL_REPLICATE: NOT RUN
```

## Next action

Complete the remaining local security/systemd/Task/MCP regression matrix, run
the full hermetic quality gate, inspect the complete dual-sided diff, create a
GPG-signed candidate commit, publish the PR, and admit only the exact head with
all required protected contexts. Do not start Phase 5C.

## Append-only continuation — local validation, not a candidate epoch

This addendum supersedes no historical evidence and does not claim a published
candidate. The earlier `EPOCH_1_HEAD` block above is stale for the current local
worktree and must not be used as provenance for the changes below.

```text
LOCAL_OBSERVED_AT_UTC: 2026-09-13T23:25:47Z
LOCAL_WORKTREE: /root/gemma/projects/P.O.W.E.R-INFRA-1
LOCAL_BASE_HEAD: ace5d6351dd599578491023419140b6a79bd6b7f
LOCAL_IMPLEMENTATION_EPOCH: uncommitted worktree; no candidate commit published
LOCAL_DIRTY_ENTRY_COUNT: 55
REMOTE_READBACK_AT_UTC: 2026-09-13T23:26:08Z
REMOTE_PR: #419
REMOTE_BASE_SHA: 6a315d5919eeef797bc506ecb216313c20419fc2
REMOTE_HEAD_SHA: 62323a930189c7afea497a984bdf6858011dfa09
REMOTE_HEAD_TREE: 3529bdb7beb71678daf14865079e1852e6d3c750
REMOTE_HEAD_PARENT: dcf27b55e3e5bfeb285fc93ed73a485ce0f707fb
REMOTE_HEAD_GPG: verified=true
REMOTE_PR_STATE: open / mergeable=true / mergeable_state=blocked
REMOTE_REQUIRED_CHECKS: all green except CodeQL=failure; deploy=skipped
```

## Continuation validation

The current uncommitted implementation was validated locally with:

```text
FULL_HERMETIC_GATE: 2004 passed, 4 skipped, 17 deselected, 5 warnings
COVERAGE: 82%
TARGETED_INFRA_GATE: 79 passed
RUFF_CHECK: PASS
RUFF_FORMAT_CHECK: PASS
MYPY_SRC: PASS
UV_LOCK_CHECK: PASS
UV_SYNC_LOCKED_AND_PIP_CHECK: PASS
PACKAGE_WHEEL_SDIST_SMOKE: PASS / version=3.7.11 / queries=16
PIP_AUDIT: no known vulnerabilities; local distribution not on PyPI
MKDOCS_STRICT: PASS
DOC_DRIFT: PASS with repository POWER_GLOBAL_SKILL_PATH
SYSTEMD_ANALYZE_VERIFY: PASS; unrelated xfs CPUAccounting warnings only
REAL_RECEIVER_EVIDENCE: unavailable
REAL_REPLICATE: NOT RUN
```

The code continuation includes durable dry-run receipt gating, type-aware
read-only verify inventory and digest pulls, prepared-admission recovery and
expiry rollback, source directory/file bounds, fsync publication, bounded
connection handling, strict caller JSON ACL, and explicit systemd interpreter
checks. Publication, remote check refresh, receiver evidence, protected merge,
and Phase 5C remain blocked.

## Append-only continuation — final local candidate validation

This addendum records the later local implementation and documentation work. It
does not replace the stale candidate epoch above and does not claim `REMOTE
EXACT-HEAD` or `MERGED MAIN` status.

```text
LOCAL_OBSERVED_AT_UTC: 2026-09-14T16:17:31Z
LOCAL_BASE_HEAD: ace5d6351dd599578491023419140b6a79bd6b7f
LOCAL_WORKTREE: dirty / uncommitted / 55+ changed-or-untracked entries
LOCAL_CANDIDATE_PROVENANCE: no signed candidate commit or immutable tuple
REMOTE_MAIN_SHA: 6a315d5919eeef797bc506ecb216313c20419fc2
REMOTE_MAIN_TREE: a03b90648e1e57c5a579e5834988015192027cb0
REMOTE_PR: #419
REMOTE_PR_HEAD: 62323a930189c7afea497a984bdf6858011dfa09
REMOTE_PR_TREE: 3529bdb7beb71678daf14865079e1852e6d3c750
REMOTE_PR_PARENT: dcf27b55e3e5bfeb285fc93ed73a485ce0f707fb
REMOTE_PR_READBACK: open / mergeable=true / mergeable_state=unstable
REMOTE_REQUIRED_CHECKS: CodeQL=failure; deploy=skipped; other observed checks successful
REAL_RECEIVER_EVIDENCE: unavailable
REAL_REPLICATE: NOT RUN
```

### Final local evidence

```text
FULL_HERMETIC_GATE: 2012 passed, 4 skipped, 17 deselected
COVERAGE: 82%
TARGETED_BROKER_TASK_RECOVERY_GATES: 120, 142, 189, 299, and 388 passed in separate runs
RUFF_REPOSITORY: PASS (122 source files)
MYPY_REPOSITORY: PASS (122 source files)
PACKAGE_BUILD: wheel + sdist, version 3.7.11
PACKAGE_SMOKE: PASS / queries=16
UV_LOCK_CHECK: PASS / 132 packages resolved
PIP_CHECK: PASS
PIP_AUDIT: no known vulnerabilities; local distribution skipped as not on PyPI
SYSTEMD_ANALYZE_VERIFY: PASS; unrelated xfs CPUAccounting warnings only
MKDOCS_STRICT: PASS; existing nav/deprecation/unrecognized-link warnings remain
GIT_DIFF_CHECK: PASS
FRESH_CODE_REVIEW: no P0/P1 protected-admission code blocker found
DOC_DRIFT: FAIL / global OpenCode skill and repository runtime-contract copies differ;
  global CLI-count metadata is inconsistent (27 vs 26)
```

The implementation now includes admission/run owner fencing, fail-closed
recovery, exact read-only verification, canonical writer receipts, task-bound
verify/completion rules, repeat-dry-run receipt separation, stable replay
projection identity, and explicit public Task API boundaries. These facts are
still local provisional evidence until a signed exact candidate is published
and passes fresh protected CI/readback plus operator receiver evidence.

The next authorized action is candidate/provenance preparation only: inspect and
stage the intended diff, create a GPG-signed feature-branch commit, publish via
the approved GitHub REST/Git channel, re-read the exact PR tuple and required
checks, and keep Phase 5C, release, and real replication blocked until all gates
are independently green.

## Append-only continuation — published candidate epoch

The local implementation and governance reconciliation were published to the
existing feature branch for PR #419. This is a new candidate epoch; prior local
and remote tuples remain historical evidence and are not silently reused.

```text
PUBLISHED_OBSERVED_AT_UTC: 2026-09-14T16:40:21Z
PR: 419
BASE_SHA: 6a315d5919eeef797bc506ecb216313c20419fc2
HEAD_SHA: 4dc2db46885ab81e337f398f16ea6a7aac585839
HEAD_TREE: 0550327422405aace37a6593abcfc3e836b7c7fc
HEAD_PARENT: 62323a930189c7afea497a984bdf6858011dfa09
HEAD_GPG: verified=true / reason=valid
PR_STATE: open / mergeable=true / mergeable_state=unstable
OBSERVED_CHECK_RUNS: 11; several in_progress; deploy=skipped
PRIOR_HEAD_CODEQL: failure on 62323a9; superseded by this candidate epoch
```

The exact candidate contains the INFRA-1 implementation, security/deployment
artifacts, tests, API/ADR documentation, planning reconciliation, and the
append-only evidence updates. Local gates remain `2012 passed, 4 skipped, 17
deselected`, `82%` coverage, repository Ruff/MyPy PASS, package smoke PASS,
`uv lock --check` PASS, systemd verification PASS, strict MkDocs PASS, and
`git diff --check` PASS. A fresh read-only review found no P0/P1
protected-admission code blocker. The doc-drift helper still reports the
global OpenCode skill/repository runtime-contract mismatch.

Protected admission is not claimed: required remote checks have not completed,
receiver/forced-`rrsync` evidence is unavailable, and Phase 5C, release, and
merge remain blocked.
