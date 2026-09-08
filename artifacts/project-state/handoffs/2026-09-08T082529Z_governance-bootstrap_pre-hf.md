# POWER 3.8 Pre-HF Governance Bootstrap Handoff

> Append-only provisional handoff. It records the pre-HF governance candidate
> and does not claim that PR #408 or HF PR #406 has merged.

## STAGE

Pre-HF governance publication — signed candidate created from live `main`.

## PUBLIC_VERSION

`3.7.11` — public stable and frozen.

## STARTING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f`

## ENDING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f` — unchanged; no protected merge
was performed in this handoff.

## STATE_BASE_SHA

`119d5c39aa2c22734ca72c351f8a70790371678f`

## PR

- Governance candidate PR [#408](https://github.com/weby-homelab/power-framework/pull/408):
  `OPEN`, base `main`.
- HF admission PR [#406](https://github.com/weby-homelab/power-framework/pull/406):
  `OPEN / NOT MERGED`.
- Provisional source PR [#407](https://github.com/weby-homelab/power-framework/pull/407):
  retained and not deleted or treated as canonical.
- Actions PR #396: `HOLD / NOT STARTED`.

## CANDIDATE_EPOCH

```text
EPOCH: governance-408-1
PR: 408
BASE_SHA: 119d5c39aa2c22734ca72c351f8a70790371678f
HEAD_SHA: d788825607ae55b9de1142f67ab076f8e533d14d
HEAD_TREE: 380cba0de80d622e4db109be168f642eaaddd1ea
HEAD_PARENT: 119d5c39aa2c22734ca72c351f8a70790371678f
OBSERVED_AT_UTC: 2026-09-08T08:25:29Z
REASON: fresh signed governance snapshot from live main before HF admission
```

If any base, head, tree, parent, diff, dependency/export hash, or policy state
changes, this epoch is stale. Retain it, create a new epoch, recompute evidence,
and continue remediation rather than stopping solely because the SHA changed.

## GPG

- Local `git verify-commit HEAD`: `PASS` for `d788825607ae55b9de1142f67ab076f8e533d14d`.
- GitHub Git Database commit verification: `verified=true`, `reason=valid`.
- GitHub verification timestamp: `2026-09-08T08:23:57Z`.
- Parent and tree match the locally signed object exactly.

## MERGE_STATUS

```text
GOVERNANCE_PR_408: OPEN / NOT MERGED
HF_PR_406: OPEN / NOT MERGED / mergeable=true / mergeable_state=blocked
GOVERNANCE_NORMAL_MERGE: NOT ATTEMPTED
HF_NORMAL_MERGE: NOT ATTEMPTED
```

`mergeable_state=blocked` is a diagnostic input. Authenticated branch policy
reported 11 required contexts, strict freshness, zero required approving
reviews, disabled required conversation resolution, and no force-push or delete
permission. The required check state for #406 was successful, but the concrete
protected merge admission result has not been attempted; no magic state string
is used as a terminal stop.

## MERGE_SHA

`N/A` — no governance or HF merge was performed.

## TESTS

- Local `.venv/bin/mkdocs build --strict` — `PASS`; existing unlisted-page and
  Material deprecation warnings only.
- Workspace `./verify.sh` — `PASS`.
- `git diff --check` — `PASS`.
- Functional test suite — `NOT RUN`; this bounded change is documentation and
  handoff publication only.

## SECURITY

- No source, dependency, workflow, lockfile, version, tag, release, or runtime
  file changed.
- WEB-01 and WEB-05 remain closed through merged security PR #405.
- The governance candidate introduces no executable or network boundary.
- HF #406 security evidence remains exact-head/provisional until a new main
  state exists.

## CI / CODEQL / DOCS

- PR #408 remote required checks: `PENDING` at handoff creation.
- PR #408 CodeQL: `PENDING` at handoff creation.
- PR #408 Docs: `PENDING` at handoff creation; local strict build passed.
- PR #406 exact-head CI/CodeQL/Docs: previously verified successful; its live
  PR remains open and blocked by GitHub admission state.
- PR #407 CI/Docs: previously observed required failures and remains
  provisional source material; it is not the active canonical branch.

## REVIEW_THREADS

- PR #408: `PENDING / no independent review evidence yet`.
- PR #406: authenticated REST returned zero submitted reviews, zero requested
  reviewers, and zero inline comments; branch protection currently requires
  zero approvals.
- PR #407: one active CodeRabbit inline finding about artifact links; the fix is
  included in the fresh #408 candidate.

## WORKTREE

- Local repository: `/root/geminicli/projects/power-framework`.
- Branch: `docs/power-3.8-governance-bootstrap`.
- Signed candidate head before this handoff update:
  `d788825607ae55b9de1142f67ab076f8e533d14d`.
- Remote branch ref points to the same verified SHA through GitHub REST.
- A follow-up signed commit is required to publish this handoff and the PR
  pointer update; it will be a new governance candidate epoch.

## COMPLETED

- Fresh GitHub ref, PR, commit, tree, check, review, ruleset, and protection
  inspection completed without starting Actions #396.
- Six independent read-only audits completed; their claims were checked
  against primary GitHub/Git evidence.
- Seven files from #407 imported as source material into a fresh branch from
  live `main`.
- Stale `unstable` stop semantics, candidate SHA handling, pre-HF governance
  boundary, and artifact-link contract repaired.
- Local GPG-signed commit created and GitHub-verified; PR #408 opened.

## OPEN_BLOCKERS

- PR #408 required checks and protected merge admission are pending.
- HF #406 remains open with live `mergeable_state=blocked`; diagnose its actual
  policy response after governance publication and revalidate it as a new epoch
  if `main` advances.
- PR #407 has failing required docs/build checks and unsigned historical
  commits; it remains retained provisional evidence, not a merge target.
- The sandbox denied direct HTTPS `git push`; authenticated REST successfully
  published the exact locally signed commit/tree/ref, so no signing evidence
  was substituted or lost.

## NEXT_GATE

Validate PR #408 exact head and all required checks, publish/update the single
state-pointer comment on HF PR #406, then make one normal protected merge
attempt only if GitHub policy accepts the exact current head. After a
governance merge, fresh-fetch `main`, create a new HF candidate epoch, and
recompute its full dependency/security/CI evidence. Do not start Actions #396
or Phase 5.

## AUTHORIZED

- Pre-HF governance publication from live `main`: `YES`.
- Local GPG signing and ordinary protected PR workflow: `YES`.
- Normal merge only when GitHub protected policy accepts the exact head: `YES`.
- Retaining PR #407 as provisional source material: `YES`.

## NOT_AUTHORIZED

- Admin/protection bypass, fake approval, force merge, or force push.
- Starting Actions #396, Phase 5–9, public version bump, tag, release, or
  `POWER 3.8.0` publication.
- Calling this candidate or PR #407 `MERGED MAIN` before a protected merge.
- Reusing old #406 evidence after `main` or its candidate tuple changes.

## PUBLICATION

- Canonical candidate branch:
  `docs/power-3.8-governance-bootstrap`.
- Candidate PR: [#408](https://github.com/weby-homelab/power-framework/pull/408).
- Current state path after protected publication:
  `docs/plans/POWER_3.8_CURRENT_STATE.md`.
- Roadmap path:
  `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`.
- Protocol path:
  `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
- This handoff is provisional until PR #408 is normally merged; a later
  post-HF handoff must be added rather than rewriting this packet.

## POWER VERSION

`3.7.11`

## POWER 3.8.0

`NO-GO`

## RETAINED_EVIDENCE

- [HF PR #406](https://github.com/weby-homelab/power-framework/pull/406)
- [Governance PR #408](https://github.com/weby-homelab/power-framework/pull/408)
- [Provisional evidence PR #407](https://github.com/weby-homelab/power-framework/pull/407)
- [Signed governance candidate](https://github.com/weby-homelab/power-framework/commit/d788825607ae55b9de1142f67ab076f8e533d14d)
- [Security PR #405](https://github.com/weby-homelab/power-framework/pull/405)
