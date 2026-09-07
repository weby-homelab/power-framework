# HISTORICAL SNAPSHOT — Security Merge → HF Admission Handoff

> **Historical pre-merge HF admission state.** This file records the earlier
> state exactly as retained from the pre-merge preparation. It is not current
> state after this session and must not be rewritten as if its blocker never
> existed.

## STAGE

Repository Governance Bootstrap — security merge complete, HF admission
awaiting independent authorization.

## STARTING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f`

## ENDING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f` (unchanged; no merge performed).

## PR

- Security PR #405: MERGED.
- HF PR [#406](https://github.com/weby-homelab/power-framework/pull/406): OPEN.
- Historical HF PR #404: CLOSED / SUPERSEDED.
- Actions PR #396: OPEN / HOLD.

## BASE_SHA

HF #406 base: `119d5c39aa2c22734ca72c351f8a70790371678f`.

## HEAD_SHA

HF #406 exact head: `201da2e0e78d1bbf860c98dc653008c0fb4984cd`.

## HEAD_TREE

`c8d66c9bf65c54b09bb9990380313737af63c932`

HF target: `huggingface-hub 1.30.0`.

- `uv.lock` SHA-256:
  `d8a7456d53bdfc79090f4b3a3b9279664e2662c4f7343100a68db734c167485a`.
- Web export SHA-256:
  `4001e0b073acb7c6eb40bab6047bcb13adedbca3d2a6ebdf23e1b28687b435c3`.

## GPG

- HF exact head: **GOOD** signature from `Weby Homelab` (`git verify-commit`
  succeeded locally).
- Security merge #405: **GOOD ON GITHUB** (`verification.verified=true`,
  `reason=valid`). Local `git verify-commit` could not check it because the
  public key for the recorded signature was not present in that host keyring.

## MERGE_STATUS

- Security PR #405 = MERGED.
- Security merge commit:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- HF PR #406 = OPEN / NOT MERGED.
- Historical GitHub observation: `mergeable=true` and
  `mergeable_state=blocked` for #406.
- HF MERGED = NO.

## MERGE_SHA

- Security #405: `119d5c39aa2c22734ca72c351f8a70790371678f`.
- HF #406: N/A.

## MERGE_PARENTS

Security #405 merge parents:

- `be83652aec2daedeb2c98b604b5a49d13e989c7e`
- `a2ba3000c6bc1c3c470b47a0e784ff3c10c51c0b`

Security merge tree: `9db113ea5a24f76abac994e8d7eac69744115f64`.

## TESTS

- PSE/TASK/DECISION: `348 passed`.
- Crash recovery: `11 passed`.
- Combined PSE/TASK/DECISION/crash: `359 passed`.
- Python 3.13: `1775 passed, 4 skipped, 17 deselected`; coverage `83.06%`.
- Python 3.14: `1775 passed, 4 skipped, 17 deselected`; coverage `83.06%`.
- HF functional matrix: PASS for `huggingface-hub==1.30.0`, immutable-revision
  cache fixture, cache confinement, offline replay, and invalid-input rejection.

## SKIPPED

Four canonical skips: one release-tag baseline test and three unavailable live
Web E2E tests.

## DESELECTED

Seventeen tests deselected by the canonical non-neural/non-benchmark gate.

## COVERAGE

`83.06%` on both the Python 3.13 and Python 3.14 canonical suites.

## SECURITY

- WEB-01 = CLOSED / PASS.
- WEB-05 = CLOSED / PASS.
- Security merge #405 is the canonical closure:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- HF #406 does not alter the merged WEB boundaries and records zero unauthorized
  HF calls in its functional evidence.

## CI

- Remote CI run
  [34155572536](https://github.com/weby-homelab/power-framework/actions/runs/34155572536)
  = PASS; all required status contexts are successful.
- Required contexts include Python 3.13/3.14 tests, security, package smoke,
  upgrade matrix, base runtime, benchmark integrity, Python analysis, and build.
- CodeRabbit status = PASS / review completed.

## CODEQL

PASS — [run 34155572534](https://github.com/weby-homelab/power-framework/actions/runs/34155572534).

## DOCS

PASS — [Docs run 34155627507](https://github.com/weby-homelab/power-framework/actions/runs/34155627507).
The repository-defined deploy job is skipped in that successful Docs workflow.

## REVIEW_THREADS

Zero unresolved review threads. Historical GitHub API observation returned zero
submitted reviews, zero requested reviewers, and zero inline review comments for
#406. CodeRabbit reported no actionable comments.

## WORKTREE

- Canonical HF checkout: `/root/geminicli/projects/power-framework`.
- Branch: `chore/power-3.8-hf-refresh`.
- HEAD remains exactly `201da2e0e78d1bbf860c98dc653008c0fb4984cd`.
- Worktree was clean; no commit was added and no remote ref was changed.
- Governance draft was staged outside the repository checkout and was not yet a
  branch, commit, PR, or merged artifact.

## COMPLETED

- POWER 3.7.11 public stable — FROZEN.
- Phase 0 — DONE.
- Phase 1 — DONE.
- Phase 2 — DONE.
- Phase 3 — DONE.
- Phase 4 — DONE / MERGED / FROZEN.
- Phase 4 merge: `01059114a29af2fd0f1faafa6c8190fadcca1c86`.
- Python controlled dependency refresh — MERGED.
- Security WEB-01 — CLOSED.
- Security WEB-05 — CLOSED.
- Security merge — `119d5c39aa2c22734ca72c351f8a70790371678f`.
- Current draft files prepared locally only; no governance commit existed.

## OPEN_BLOCKERS

- Independent HF audit was pending.
- Explicit `HF MERGE AUTHORIZED` had not been received.
- Historical `mergeable_state=blocked` remained without a proven authoritative
  root cause; **HF BLOCK REASON = NOT FULLY OBSERVABLE**.
- Admin bypass, auto-merge, rebase, and evidence commits were forbidden.
- CONTROLLED DEPENDENCY REFRESH = NO-GO.
- ACTIONS #396 = HOLD.
- PHASE 5 = BLOCKED.
- Phase 5 implementation = NOT STARTED.

## NEXT_GATE

Receive the independent verdict `HF MERGE AUTHORIZED`, reverify exact base/head,
required checks, reviews, GPG, and mergeability, then perform a normal protected
merge of #406. After post-HF CI/CodeQL/Docs verification, create the governance
branch from exact post-HF `main`.

## AUTHORIZED

- HF merge authorization: **NO**.
- Governance draft preparation outside the repository: **YES**.
- Governance branch/commit/PR: **NO** before HF merge.

## NOT_AUTHORIZED

- Do not push or modify `chore/power-3.8-hf-refresh`.
- Do not alter HF head `201da2e0e78d1bbf860c98dc653008c0fb4984cd`.
- Do not merge #406, bypass protection, bump version, tag, release, or start
  Actions #396, Phase 5, or Phase 6.
- Do not call local candidate evidence `MERGED MAIN` or `FINAL INTEGRATION`.

## POWER VERSION

`3.7.11`

## POWER 3.8.0

`NO-GO`

## Retained evidence

- [Security PR #405](https://github.com/weby-homelab/power-framework/pull/405)
- [HF PR #406](https://github.com/weby-homelab/power-framework/pull/406)
- [HF head commit](https://github.com/weby-homelab/power-framework/commit/201da2e0e78d1bbf860c98dc653008c0fb4984cd)
- [Phase 4 report](../../../artifacts/project-state/phase-4/PHASE_4_REPORT.md)
