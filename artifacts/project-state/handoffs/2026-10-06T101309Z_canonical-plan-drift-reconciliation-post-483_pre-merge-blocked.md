# CANONICAL_PLAN_DRIFT_RECONCILIATION_POST_483

STAGE: CANONICAL_PLAN_DRIFT_RECONCILIATION_POST_483
PUBLIC_VERSION: 3.7.13
STARTING_MAIN: f38db3aa0177b027a1e6d435fb930c01936f9a69
STATE_BASE_SHA: f38db3aa0177b027a1e6d435fb930c01936f9a69
OBSERVED_AT_UTC: 2026-10-06T09:54:56Z
EXECUTION_AT_UTC: 2026-10-06T10:13:09Z
CANDIDATE_EPOCH: Exact B above; this handoff records no candidate H/T/PR/M/F to avoid a self-reference cycle. Candidate-specific identities and results belong in the private admission receipt.

## Live baseline

- Authenticated `/user` returned HTTP 200 for `weby-homelab`; protected `main`
  and fetched/local Git agreed on B and tree
  `ae78f0a4878eb6013719e9f65b6094e93c5f2373`. B parents are
  `e68bc4eacd5d49db451d0f1379299c17c9175ad1` and
  `c17ed415f183e6895782ad4c3d57e1300cd93195`; GitHub commit verification is
  `verified=true / reason=valid`.
- #480 is closed without merge. #481 is merged as
  `e68bc4eacd5d49db451d0f1379299c17c9175ad1`. #483 is merged as B at
  `2026-10-01T07:50:40Z`; its head is an ancestor of B. Issue #471 is
  `CLOSED / completed` at `2026-10-01T07:55:25Z`. This gate does not mutate
  issue #471.
- At the observation above, paginated open PR results contained only unrelated
  Dependabot PRs #482, #484, and #477; no eligible post-#483 reconciliation PR
  was present. A second complete duplicate check is required before any PR
  creation.
- Protected main currently requires 11 strict status contexts, valid signed
  commits, and the normal protected merge path. No required approval count is
  configured by the live branch-protection response; this does not waive the
  independent review and attestation gates in the repository protocol.

## Acceptance boundary

The linked sanitized evidence
[`openvino-471-current-kb-acceptance.json`](../evidence/openvino-471-current-kb-acceptance.json)
records PASS only for the explicitly authorized current snapshot: 791/791
sources, 5,876 chunks, zero exclusions/errors/retries/catalog conflicts, 100%
FTS and dense coverage, integrity `ok`, and functional semantic/reranked
results without search fallback. The gate-fixed acceptance facts also record
zero duplicates; the JSON records source/inventory equality and zero catalog
conflicts but has no separate duplicate-count field.

Attempt 1 sync succeeded and its metrics collector failed; it is not canonical.
The canonical independent clean-cache Attempt 2 measured
`1794.7842812340023` seconds and `3.375 GiB` peak process-tree RSS. Do not
average, rerun, invent a speedup, or create an unrecorded threshold.

OpenVINO GPU execution used `session.disable_cpu_ep_fallback=1`. This statement
is limited to ORT CPU EP graph fallback: CPU EP can be registered, and no claim
of zero total CPU activity is made. GPU utilization is `NOT_MEASURED`. The
legacy 3,624-note / 19,954-chunk / 23,578-vector workload remains
`NONREPRODUCIBLE / SUPERSEDED / NOT_REPRODUCED / NOT_PASSED`.

## Candidate content and validation boundary

This gate's bounded candidate scope is to reconcile the active pointers/statuses
in the four canonical plans and add this one append-only handoff. At this
observation, candidate edits/publication were not yet complete; the private
continuation records their actual results. Dated prior #481/R6A.2/#472/#473
history remains historical and unchanged. Repository files contain no
H/T/PR/M/F self-reference and no future readback assertion.

The workspace Tier-0 `./verify.sh` is required for candidate validation but is
absent at `/home/weby/verify.sh`; exact source, scope, CWD, result, and recovery
proposal are recorded in the private `VALIDATION_PROVENANCE.md`. No substitute,
wrapper, N/A, or policy change is authorized. Other permitted doc-drift,
strict-MkDocs, link/governance checks must be recorded separately and are not a
replacement for that missing required check.

H/GPG signature, current CI, independent final-H reviews, GitHub conversations,
PR admission, merge method, M/F, ancestry, and post-merge readback are live
facts and are not claimed by this handoff. At this observation the gate is
blocked until those checks are completed; the missing workspace validation
remains unresolved.

## Disposition and next gate

COMPLETED: Verified #483 ancestry and #471 completed disposition; recorded the
current B baseline and the exact active-plan drift for this docs-only candidate.
MERGE_STATUS: NOT ASSERTED HERE; read live GitHub state after any protected
publication.
OPEN_BLOCKERS: Required workspace `./verify.sh` unavailable with no documented
recovery; final exact-profile reviews and candidate CI/admission remain
uncompleted until the candidate H exists.
NEXT_GATE: `PHASE_5E_FRESH_EVALUATION_AUTHORING` only after this canonical-plan
reconciliation is protected-merged and its exact post-merge readback is
verified in a separate invocation. Phase 5E remains `OPEN / NOT PASSED`;
Phase 5F remains `BLOCKED`; POWER 3.8.0 remains `NO-GO`.
AUTHORIZED: This bounded docs-only reconciliation candidate and a single
protected normal PR path if all admission gates pass.
NOT_AUTHORIZED: Phase 5E/5F execution, fresh evaluation, one-shot, GT/holdout,
hardware, benchmark, full sync/rebuild, release, issue #471 mutation, backup
access, runtime/dependency/lockfile/workflow/validator/protection/signing
identity changes, or brain remote sync.

FRESH_EVALUATION_TOUCHED_BY_THIS_GATE: NO
ONE_SHOT_CONSUMED_BY_THIS_GATE: NO
HARDWARE_RERUN_BY_THIS_GATE: NO
GLOBAL_FRESH_EVALUATION_STATE: UNKNOWN
GLOBAL_ONE_SHOT_STATE: UNKNOWN
