# POWER 3.8 Governance Post-Merge — HF Refresh Handoff

> Append-only handoff. Governance is canonical on `main` after PR #408; HF
> admission is not merged and must be rebuilt against the new main.

## STAGE

Pre-HF controlled dependency refresh after canonical governance merge.

## PUBLIC_VERSION

`3.7.11` — public stable and frozen.

## STARTING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f`

## ENDING_MAIN

`4b49e00c75866fa57f71e7bef61547915f7e01db`

## STATE_BASE_SHA

`4b49e00c75866fa57f71e7bef61547915f7e01db`

## PR

- Governance PR [#408](https://github.com/weby-homelab/power-framework/pull/408):
  `MERGED`.
- HF PR [#406](https://github.com/weby-homelab/power-framework/pull/406):
  `OPEN / NOT MERGED`; its base remains the pre-governance main.
- Provisional evidence PR [#407](https://github.com/weby-homelab/power-framework/pull/407):
  retained, open, and marked `SUPERSEDED BY #408`.
- Actions PR #396: `HOLD / NOT STARTED`.

## BASE_SHA

HF #406 original base: `119d5c39aa2c22734ca72c351f8a70790371678f`.

## HEAD_SHA

HF #406 retained head: `201da2e0e78d1bbf860c98dc653008c0fb4984cd`.

## HEAD_TREE

HF #406 retained tree: `c8d66c9bf65c54b09bb9990380313737af63c932`.

## HEAD_PARENT

HF #406 retained parent: `119d5c39aa2c22734ca72c351f8a70790371678f`.

## OBSERVED_AT_UTC

`2026-09-08T09:14:03Z` — post-merge REST and Git verification.

## CANDIDATE_EPOCH

```text
GOVERNANCE_MERGE_EPOCH: governance-408-4
GOVERNANCE_PR: 408
GOVERNANCE_HEAD: b6f54b0c04da545ba1fe3cd9fa932638d2ff8815
GOVERNANCE_TREE: da33bef8fd4ecd5eafa68e04bb7db21246fb42b4
MERGE_SHA: 4b49e00c75866fa57f71e7bef61547915f7e01db
MERGE_PARENTS: 119d5c39aa2c22734ca72c351f8a70790371678f, b6f54b0c04da545ba1fe3cd9fa932638d2ff8815

HF_EPOCH: hf-406-1-stale-after-governance-merge
HF_BASE: 119d5c39aa2c22734ca72c351f8a70790371678f
HF_HEAD: 201da2e0e78d1bbf860c98dc653008c0fb4984cd
HF_TREE: c8d66c9bf65c54b09bb9990380313737af63c932
HF_PARENT: 119d5c39aa2c22734ca72c351f8a70790371678f
INVALIDATED_BY: main advanced to 4b49e00c75866fa57f71e7bef61547915f7e01db
```

The HF epoch is retained for provenance but cannot authorize a merge. Merge
current `main` into the HF branch or create a replacement, then record the new
base/head/tree/parent, recompute the three-file diff and all evidence. A SHA
change starts a new epoch and does not terminate the work.

## GPG

- Governance head `b6f54b0c04da545ba1fe3cd9fa932638d2ff8815`: local and GitHub
  `verified=true`, `reason=valid`.
- Normal merge commit `4b49e00c75866fa57f71e7bef61547915f7e01db`: GitHub
  `verified=true`, `reason=valid`.
- Protected merge method: normal `merge`; no bypass or force operation.

## MERGE_STATUS

```text
GOVERNANCE_PR_408: MERGED
GOVERNANCE_MERGE: ACCEPTED BY PROTECTED NORMAL MERGE
HF_PR_406: OPEN / NOT MERGED / STALE BASE
HF_NORMAL_MERGE: NOT ATTEMPTED
```

## MERGE_SHA

`4b49e00c75866fa57f71e7bef61547915f7e01db`

## MERGE_PARENTS

- `119d5c39aa2c22734ca72c351f8a70790371678f`
- `b6f54b0c04da545ba1fe3cd9fa932638d2ff8815`

## TESTS

- PR #408 required checks: `11/11 success` before merge.
- Post-merge `main` had 10 direct required workflow check-runs observed as
  `success`, including Python 3.13/3.14, security, package smoke, upgrade
  matrix, benchmark integrity, Python analysis, build, base runtime, and
  aggregate. CodeQL was `success` on the exact governance PR head before merge;
  no separate push CodeQL run appeared in the observed main check-run set.
- Local governance docs: `.venv/bin/mkdocs build --strict` `PASS` and
  workspace `./verify.sh` `PASS` before merge.
- HF exact-head local evidence: lock/export/pip-check, deterministic HF tests,
  core security matrix, Ruff, format, MyPy, and pip-audit `PASS`; full suite
  `1774 passed, 4 skipped, 17 deselected, 83.05%`, with one timing assertion
  failure at `5.107s` that passed isolated at `4.14s` and is pre-existing
  performance variance, not a dependency failure.

## SECURITY

- WEB-01: `CLOSED / PASS` through merged PR #405.
- WEB-05: `CLOSED / PASS` through merged PR #405.
- Governance merge changed only docs/handoff files and introduced no executable
  network, loader, provider, approval, or path-traversal surface.
- HF security matrix remains exact-head evidence and must be rerun after the
  new HF candidate is based on current `main`.

## CI / CODEQL / DOCS

- Governance PR #408 required contexts were successful before its merge.
- Main merge commit `4b49e00c75866fa57f71e7bef61547915f7e01db` had successful
  post-merge CI required contexts in the observed check set.
- CodeQL and Docs were successful on the exact governance head before merge;
  `deploy` behavior remains workflow-defined and is not the HF admission gate.
- No HF check run was started by this handoff after the main advance.

## REVIEW_THREADS

- Governance #408 merged after required-policy diagnosis; branch protection
  required zero approvals and required conversation resolution was disabled.
- #408 retained CodeRabbit findings were repaired or explicitly bounded in the
  PR body and review-disposition comment.
- #406 has zero submitted reviews, zero requested reviewers, and zero inline
  comments in the authenticated observation; its old check evidence is stale
  for the new base.

## WORKTREE

- Repository: `/root/geminicli/projects/power-framework`.
- Current local branch: `docs/power-3.8-post-governance-state`.
- Base commit: `4b49e00c75866fa57f71e7bef61547915f7e01db`.
- State update branch is provisional until its normal protected PR merge.

## COMPLETED

- Fresh-fetch verified governance PR #408 merge, merge SHA, tree, parents, and
  current `main` ref.
- Proved the signed governance head is an ancestor of `main` through the
  protected merge graph.
- Verified post-merge required checks and retained HF exact-head evidence.
- Classified #406 as a repairable stale-base candidate, not a terminal stop.

## OPEN_BLOCKERS

- Current-state files on `main` still describe the pre-merge governance snapshot
  until this post-governance state update is normally merged.
- HF #406 requires a new candidate epoch against current `main`; no HF merge
  attempt is authorized under the old base.
- Actions #396 and Phase 5 remain intentionally untouched.

## NEXT_GATE

Publish this post-governance state update in one normal protected PR. Then merge
current `main` into the HF branch or create a replacement, compute the new exact
tuple and three-file diff, rerun the full HF dependency/security/CI matrix, and
make one normal protected HF merge attempt only when policy accepts the exact
head. Do not start Actions #396 or Phase 5.

## AUTHORIZED

- Post-governance state publication: `YES`.
- HF branch refresh/replacement as a new candidate epoch: `YES`.
- One normal HF merge attempt after fresh exact admission: `YES`.

## NOT_AUTHORIZED

- Admin/protection bypass, fake approval, force push, force merge, auto-merge,
  merge queue override, or weakening required checks.
- Starting Actions #396, Phase 5–9, version bump, tag, release, or POWER 3.8.0.
- Rewriting historical handoffs or promoting old HF evidence to current main.

## PUBLICATION

- Canonical merged main:
  [4b49e00](https://github.com/weby-homelab/power-framework/commit/4b49e00c75866fa57f71e7bef61547915f7e01db).
- Governance PR:
  [#408](https://github.com/weby-homelab/power-framework/pull/408).
- Active HF gate:
  [#406](https://github.com/weby-homelab/power-framework/pull/406).
- Current state: `docs/plans/POWER_3.8_CURRENT_STATE.md`.
- Roadmap: `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`.
- Protocol: `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
- This packet is provisional until its state-update PR merges; later changes
  append a new handoff.

## POWER VERSION

`3.7.11`

## POWER 3.8.0

`NO-GO`
