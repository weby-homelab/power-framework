# POWER 3.8 Governance Bootstrap — Candidate Epoch 2

> Append-only provisional handoff. This packet records the second exact
> governance candidate epoch and does not claim that PR #408 or HF #406 merged.

## STAGE

Pre-HF governance publication — candidate epoch 2 after the signed handoff
publication commit.

## PUBLIC_VERSION

`3.7.11` — public stable and frozen.

## STARTING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f`

## ENDING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f` — unchanged; no protected merge
was performed in this epoch.

## STATE_BASE_SHA

`119d5c39aa2c22734ca72c351f8a70790371678f`

## PR

- Governance candidate PR [#408](https://github.com/weby-homelab/power-framework/pull/408):
  `OPEN / NOT MERGED`.
- HF admission PR [#406](https://github.com/weby-homelab/power-framework/pull/406):
  `OPEN / NOT MERGED`.
- Provisional source PR [#407](https://github.com/weby-homelab/power-framework/pull/407):
  retained as evidence and not treated as canonical.
- Actions PR #396: `HOLD / NOT STARTED`.

## BASE_SHA

`119d5c39aa2c22734ca72c351f8a70790371678f`

## HEAD_SHA

`98f90b36e73e0e43ac77dce3dcf895c9caec1ef9`

## HEAD_TREE

`f9046c678191fa97a9a4a9f29db32cc87b23a164`

## HEAD_PARENT

`d788825607ae55b9de1142f67ab076f8e533d14d`

## OBSERVED_AT_UTC

`2026-09-08T08:28:44Z` — live PR #408 and exact check state observation.

## CANDIDATE_EPOCH

```text
EPOCH: governance-408-2
REASON: publish the latest append-only handoff and state-pointer links after epoch 1
BASE_SHA: 119d5c39aa2c22734ca72c351f8a70790371678f
HEAD_SHA: 98f90b36e73e0e43ac77dce3dcf895c9caec1ef9
HEAD_TREE: f9046c678191fa97a9a4f29db32cc87b23a164
HEAD_PARENT: d788825607ae55b9de1142f67ab076f8e533d14d
```

The previous governance epoch was head
`d788825607ae55b9de1142f67ab076f8e533d14d`, tree
`380cba0de80d622e4db109be168f642eaaddd1ea`, parent
`119d5c39aa2c22734ca72c351f8a70790371678f`. It remains retained evidence. Any
later base/head/tree/parent, diff, hash, or policy change starts another epoch
and requires recomputed evidence rather than a terminal stop.

## GPG

- Local `git verify-commit`: `PASS` for `98f90b36e73e0e43ac77dce3dcf895c9caec1ef9`.
- GitHub commit verification: `verified=true`, `reason=valid`.
- GitHub verification timestamp: `2026-09-08T08:28:42Z`.
- Tree and parent match the locally signed commit exactly.

## MERGE_STATUS

```text
GOVERNANCE_PR_408: OPEN / NOT MERGED / mergeable=true / mergeable_state=blocked
HF_PR_406: OPEN / NOT MERGED / mergeable=true / mergeable_state=blocked
GOVERNANCE_NORMAL_MERGE: NOT ATTEMPTED
HF_NORMAL_MERGE: NOT ATTEMPTED
```

The classic merge state is diagnostic. Authenticated protection reports 11
required contexts, strict freshness, zero required approvals, disabled required
conversation resolution, and no force-push/deletion allowance. The #408 checks
were still in progress at this observation; the exact protected merge response
remains the admission arbiter.

## MERGE_SHA

`N/A` — no governance or HF merge was performed.

## TESTS

- Local `.venv/bin/mkdocs build --strict` — `PASS`; only existing unlisted-page
  and Material deprecation warnings.
- Workspace `./verify.sh` — `PASS`.
- `git diff --check` — `PASS`.
- Functional test suite — `NOT RUN`; this remains a docs/handoff-only gate.

## SECURITY

- No executable source, dependency, workflow, lockfile, version, tag, release,
  or runtime file changed.
- WEB-01 and WEB-05 remain closed through merged security PR #405.
- The candidate adds no network, loader, approval, or provider boundary.
- HF security evidence remains exact-head evidence until an HF merge and
  post-merge verification exist.

## CI / CODEQL / DOCS

- PR #408 `test (3.13)`, `test (3.14)`, `package-smoke`,
  `benchmark-integrity`, and `analyze (python)`: `IN PROGRESS` at observation.
- PR #408 `build`, `security`, `base-runtime-smoke`, `upgrade-matrix`, and
  `upgrade-matrix-aggregate`: `SUCCESS` at observation.
- PR #408 CodeQL and Docs: `PENDING / not present in the observed check list`.
- PR #406 exact-head required checks, CodeQL, and Docs: previously successful;
  #406 remains open and policy-blocked.
- PR #407 retains prior required `build`/Docs failure and cancelled/failing
  test evidence; it is not the active candidate.

## REVIEW_THREADS

- PR #408: no independent review evidence was present at handoff creation.
- PR #406: authenticated REST returned zero submitted reviews, zero requested
  reviewers, and zero inline comments; branch protection requires zero approvals.
- PR #407: one active CodeRabbit artifact-link finding remains attached to the
  provisional source PR; the fresh candidate fixes that contract.

## WORKTREE

- Local repository: `/root/geminicli/projects/power-framework`.
- Branch: `docs/power-3.8-governance-bootstrap`.
- Exact published candidate at observation:
  `98f90b36e73e0e43ac77dce3dcf895c9caec1ef9`.
- Remote branch ref was fresh-fetched and matched that SHA.
- This handoff is the state projection for epoch 2; any later commit requires a
  new epoch and a refreshed state pointer.

## COMPLETED

- Created a fresh governance branch from live `main` without changing HF,
  Actions #396, Phase 5, version, tag, release, or production state.
- Imported and repaired the seven governance/source-material files from #407.
- Created two local GPG-signed commits and published both exact objects through
  authenticated GitHub REST after the sandbox denied direct HTTPS push.
- Confirmed GitHub `verified=true` for both signed governance commits and opened
  PR #408.
- Published this latest handoff pointer and retained all prior handoffs.

## OPEN_BLOCKERS

- PR #408 required checks and protected normal-merge admission are pending.
- HF #406 remains open with `mergeable_state=blocked`; its concrete policy
  reason must be diagnosed, and any main advance creates a new HF epoch.
- PR #407 remains open provisional evidence with known required check failures;
  it is retained, not merged as a substitute.

## NEXT_GATE

Fresh-fetch and verify PR #408 exact head/checks/policy. Publish one state-pointer
comment on HF #406, then make at most one normal protected merge attempt for the
exact governance head if GitHub policy accepts it. After a governance merge,
fresh-fetch `main`, rebuild/revalidate HF as a new candidate epoch, and do not
start Actions #396 or Phase 5.

## AUTHORIZED

- Pre-HF governance publication and normal protected review: `YES`.
- Candidate epoch creation after repair/state changes: `YES`.
- Normal merge only after concrete GitHub policy acceptance: `YES`.
- Retention of provisional PR #407: `YES`.

## NOT_AUTHORIZED

- Admin/protection bypass, fake approval, force merge, force push, or disabled
  required checks.
- Starting Actions #396, Phase 5–9, version bump, tag, release, or POWER 3.8.0.
- Calling a PR or candidate `MERGED MAIN` before the protected merge receipt.

## PUBLICATION

- Governance branch:
  `docs/power-3.8-governance-bootstrap`.
- Governance PR:
  [#408](https://github.com/weby-homelab/power-framework/pull/408).
- Current state:
  `docs/plans/POWER_3.8_CURRENT_STATE.md`.
- Roadmap:
  `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`.
- Protocol:
  `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
- This packet is provisional until a protected governance merge; later state
  transitions append a new handoff instead of rewriting this one.

## POWER VERSION

`3.7.11`

## POWER 3.8.0

`NO-GO`

## RETAINED_EVIDENCE

- [Governance PR #408](https://github.com/weby-homelab/power-framework/pull/408)
- [HF PR #406](https://github.com/weby-homelab/power-framework/pull/406)
- [Provisional evidence PR #407](https://github.com/weby-homelab/power-framework/pull/407)
- [Epoch-1 signed commit](https://github.com/weby-homelab/power-framework/commit/d788825607ae55b9de1142f67ab076f8e533d14d)
- [Epoch-2 signed commit](https://github.com/weby-homelab/power-framework/commit/98f90b36e73e0e43ac77dce3dcf895c9caec1ef9)
- [Security PR #405](https://github.com/weby-homelab/power-framework/pull/405)
