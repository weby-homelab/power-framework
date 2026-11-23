# POWER 3.8 Governance Bootstrap — Candidate Epoch 3

> Append-only provisional handoff. This packet records the exact governance
> candidate observed before its protected merge attempt; it is not a merge
> receipt and does not authorize HF, Actions #396, or Phase 5.

## STAGE

Pre-HF governance publication — PR #408 exact-head admission ready.

## PUBLIC_VERSION

`3.7.11` — public stable and frozen.

## STARTING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f`

## ENDING_MAIN

`119d5c39aa2c22734ca72c351f8a70790371678f` — unchanged; no protected merge
was performed in this epoch.

## PR

- Governance PR [#408](https://github.com/weby-homelab/power-framework/pull/408):
  `OPEN / NOT MERGED`.
- HF PR [#406](https://github.com/weby-homelab/power-framework/pull/406):
  `OPEN / NOT MERGED`.
- Provisional source PR [#407](https://github.com/weby-homelab/power-framework/pull/407):
  retained as historical evidence and marked `SUPERSEDED BY #408`.
- Actions PR #396: `HOLD / NOT STARTED`.

## BASE_SHA

`119d5c39aa2c22734ca72c351f8a70790371678f`

## HEAD_SHA

`3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5`

## HEAD_TREE

`15bd0f743d1a77bfdcdeed03fc61833229dd1e03`

## HEAD_PARENT

`98f90b36e73e0e43ac77dce3dcf895c9caec1ef9`

## OBSERVED_AT_UTC

`2026-09-08T08:45:01Z` — authenticated PR, check, review, and protection
observation.

## CANDIDATE_EPOCH

```text
EPOCH: governance-408-3
BASE_SHA: 119d5c39aa2c22734ca72c351f8a70790371678f
HEAD_SHA: 3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5
HEAD_TREE: 15bd0f743d1a77bfdcdeed03fc61833229dd1e03
HEAD_PARENT: 98f90b36e73e0e43ac77dce3dcf895c9caec1ef9
REASON: update shared state after PR #408 handoff/pointer publication
```

Any later base, head, tree, parent, diff, hash, or policy change invalidates
this epoch's mutable evidence. Retain this packet, record the new tuple, rerun
the bounded checks, and continue rather than stopping solely on SHA change.

## GPG

- Local `git verify-commit`: `PASS` for `3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5`.
- GitHub commit verification: `verified=true`, `reason=valid`.
- GitHub verification timestamp: `2026-09-08T08:37:42Z`.
- All three governance commits in the branch are locally GPG-valid and
  GitHub-verified.

## MERGE_STATUS

```text
GOVERNANCE_PR_408: OPEN / NOT MERGED
mergeable: true
mergeable_state: clean
NORMAL_PROTECTED_MERGE: ADMISSIBLE FOR ONE EXACT-HEAD ATTEMPT
HF_PR_406: OPEN / NOT MERGED / mergeable_state=blocked
```

Branch protection at observation: `strict=true`, 11 required contexts, zero
required approving reviews, required conversation resolution disabled, admins
enforced, force-push disabled, and deletion disabled. The `clean` state for
#408 is the result of the required policy/check diagnosis; it is not inferred
from a magic string alone.

## MERGE_SHA

`N/A` — no governance or HF merge was performed.

## TESTS

- Local `.venv/bin/mkdocs build --strict` — `PASS`; existing unlisted-page and
  Material deprecation warnings only.
- Workspace `./verify.sh` — `PASS`.
- `git diff --check` and Markdown scan — `PASS`.
- Functional suite — `NOT RUN`; governance changes are docs/handoff-only and
  the relevant source gates are represented by remote required checks.

## SECURITY

- No executable source, dependency, workflow, lockfile, version, tag, release,
  or runtime file changed.
- WEB-01 and WEB-05 remain closed through merged security PR #405.
- No new network, loader, provider, approval, or path-traversal boundary was
  introduced.
- HF #406 dependency/security evidence remains a separate exact-head gate.

## CI / CODEQL / DOCS

At `2026-09-08T08:45:01Z`, all 11 required #408 contexts were `completed / success`:

```text
test (3.13)
test (3.14)
security
package-smoke
upgrade-matrix (ubuntu-latest)
upgrade-matrix-aggregate
base-runtime-smoke
benchmark-integrity
analyze (python)
CodeQL
build
```

The repository-defined `deploy` check was skipped and is not required. The
exact check-run IDs are attached to #408 and were independently fetched for
head `3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5`.

## REVIEW_THREADS

- PR #408: one CodeRabbit `COMMENTED` review with four findings; no requested
  reviewer, no required approval, and required conversation resolution is
  disabled.
- Valid findings were repaired or bounded: epoch-3 state, HF metadata
  attribution, and explicit #408 recovery validation.
- Old handoff relative links were not rewritten because published historical
  handoffs are immutable; the anchored evidence map below preserves their
  destinations without altering the original packets.

## IMMUTABLE_RETAINED_EVIDENCE

- Historical #407 pre-merge handoff:
  [a3f8cb5](https://github.com/weby-homelab/power-framework/blob/a3f8cb5f0cfd7e5b37ea316146a4e761a99a46e2/artifacts/project-state/handoffs/2026-09-07T234711Z_hf-406_pre-merge-blocked.md)
- Historical security handoff:
  [a3f8cb5](https://github.com/weby-homelab/power-framework/blob/a3f8cb5f0cfd7e5b37ea316146a4e761a99a46e2/artifacts/project-state/handoffs/2026-09-07_security-merge-hf-admission.md)
- Phase 4 report on merged security `main`:
  [119d5c3](https://github.com/weby-homelab/power-framework/blob/119d5c39aa2c22734ca72c351f8a70790371678f/artifacts/project-state/phase-4/PHASE_4_REPORT.md)
- Current-state/roadmap/protocol candidate:
  [3166244](https://github.com/weby-homelab/power-framework/tree/3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5/docs/plans)

## WORKTREE

- Local repository: `/root/geminicli/projects/power-framework`.
- Branch: `docs/power-3.8-governance-bootstrap`.
- Exact published candidate observed: `3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5`.
- Fresh fetch matched the remote governance ref and all three commits were
  signature-verified locally.

## COMPLETED

- Created and published a fresh signed governance branch from live `main`.
- Repaired the stale unstable-stop model, candidate-epoch contract, pre-HF
  governance boundary, and strict MkDocs artifact-link contract.
- Added two append-only governance handoffs and updated all active recovery
  pointers to the latest packet.
- Updated PR #408 body and published the single current-state pointer on HF
  PR #406; marked #407 `SUPERSEDED BY #408` without closing it.
- Verified #408 exact tuple, all required checks, branch protection, reviews,
  conversations, rulesets, and mergeability through authenticated REST.

## OPEN_BLOCKERS

- Governance PR #408 has not yet received a protected merge receipt; one normal
  exact-head merge attempt remains to be performed.
- HF #406 remains open with `mergeable_state=blocked`; after governance merge,
  `main` advancement will require a new HF candidate epoch.
- Actions #396 and Phase 5 remain intentionally untouched.

## NEXT_GATE

Perform one normal protected merge of #408 with exact head
`3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5` and `merge_method=merge`. If GitHub
rejects it, capture the exact reason and remediate; do not bypass protection.
After acceptance, fresh-fetch post-governance `main`, verify merge parents/tree,
publish a post-governance handoff, and rebuild/revalidate HF #406 as a new
candidate epoch. Do not start Actions #396 or Phase 5.

## AUTHORIZED

- One ordinary protected merge attempt for the exact clean #408 head: `YES`.
- New candidate epoch after a base/head/policy change: `YES`.
- Post-merge state publication and HF revalidation: `YES`.

## NOT_AUTHORIZED

- Admin/protection bypass, fake approval, force merge, force push, disabled
  checks, auto-merge, or merge queue override.
- Starting Actions #396, Phase 5–9, version bump, tag, release, or POWER 3.8.0.
- Rewriting historical handoffs or calling any open candidate `MERGED MAIN`.

## PUBLICATION

- Governance PR:
  [#408](https://github.com/weby-homelab/power-framework/pull/408).
- Active HF gate:
  [#406](https://github.com/weby-homelab/power-framework/pull/406).
- Current state: `docs/plans/POWER_3.8_CURRENT_STATE.md`.
- Roadmap: `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`.
- Protocol: `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
- This packet is provisional until the protected governance merge; later state
  transitions append a new handoff rather than rewriting it.

## POWER VERSION

`3.7.11`

## POWER 3.8.0

`NO-GO`

## RETAINED_EVIDENCE

- [Governance PR #408](https://github.com/weby-homelab/power-framework/pull/408)
- [HF PR #406](https://github.com/weby-homelab/power-framework/pull/406)
- [Provisional source PR #407](https://github.com/weby-homelab/power-framework/pull/407)
- [Signed governance head](https://github.com/weby-homelab/power-framework/commit/3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5)
