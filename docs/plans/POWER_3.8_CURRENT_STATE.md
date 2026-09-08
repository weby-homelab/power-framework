# POWER 3.8 — Current State

> **Publication class:** governance state projection. Before a protected merge,
> this branch is provisional; after a protected merge, the same repository
> paths are canonical for the recorded snapshot. Mutable GitHub values below
> remain subject to fresh live verification.

## Machine-readable recovery header

```text
PROJECT_STATE_SCHEMA:
power.project-state.v1

PUBLIC_VERSION:
3.7.11

DEVELOPMENT_TARGET:
3.8.0

STATE_STATUS:
GOVERNANCE CANONICAL / HF REFRESH REQUIRED

STATE_BASE_SHA:
4b49e00c75866fa57f71e7bef61547915f7e01db

CURRENT_MAIN_SHA:
4b49e00c75866fa57f71e7bef61547915f7e01db

ACTIVE_GATE:
Controlled Dependency Refresh — HF #406 new candidate epoch

LAST_CLOSED_GATE:
Pre-HF Governance Snapshot — PR #408 protected merge

LAST_MERGED_PR:
408

HF_PR:
406 OPEN / STALE BASE / REFRESH REQUIRED

PHASE_5:
BLOCKED / NOT STARTED

RELEASE_3_8_0:
NO-GO

CANONICAL_GOVERNANCE_BRANCH:
docs/power-3.8-governance-bootstrap (merged; remote ref auto-deleted)

CANONICAL_GOVERNANCE_COMMIT:
4b49e00c75866fa57f71e7bef61547915f7e01db (protected merge; GitHub-verified)

CANONICAL_GOVERNANCE_PR:
408 MERGED

LATEST_HANDOFF:
artifacts/project-state/handoffs/2026-09-08T091401Z_governance-post-merge_pre-hf.md
```

## Fresh state anchor

- Repository: [weby-homelab/power-framework](https://github.com/weby-homelab/power-framework).
- State was read from GitHub REST during this session. Every future agent must
  fetch and revalidate the mutable values below before acting.
- PRE_GOVERNANCE_OBSERVED_AT_UTC: `2026-09-08T08:13:35Z`.
- GOVERNANCE_POLICY_OBSERVED_AT_UTC: `2026-09-08T08:45:01Z`.
- POST_GOVERNANCE_OBSERVED_AT_UTC: `2026-09-08T09:14:03Z`.
- The pre-governance verified base anchor was
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- Current protected `main` is
  `4b49e00c75866fa57f71e7bef61547915f7e01db`.
- Governance merge tree:
  `da33bef8fd4ecd5eafa68e04bb7db21246fb42b4`.
- Governance merge parents:
  `119d5c39aa2c22734ca72c351f8a70790371678f` and
  `b6f54b0c04da545ba1fe3cd9fa932638d2ff8815`.
- A document SHA is a state anchor, not a substitute for live GitHub verification.

## Public and phase state

- Public version: **3.7.11**, stable and frozen.
- Development target: **POWER 3.8.0**.
- Phase 0: **CLOSED / FROZEN**.
- Phase 1: **CLOSED / FROZEN**.
- Phase 2: **CLOSED / FROZEN**.
- Phase 3: **CLOSED / FROZEN**.
- Phase 4: **CLOSED / FROZEN**.
- Phase 5: **BLOCKED / NOT STARTED**.
- Phases 6–9: **NOT STARTED**.
- POWER 3.8.0: **NO-GO**.

## Controlled Dependency Refresh

| Surface | State | Evidence |
|---|---|---|
| Python admission | CLOSED | Prior merged repository evidence |
| WEB-01 / WEB-05 | CLOSED | Security PR #405 and merge on `main` |
| Pre-HF governance snapshot | CLOSED | PR #408 protected merge on `main` |
| HF admission | REFRESH REQUIRED | PR #406 remains open but its base is behind current `main` |
| Actions #396 | HOLD / NOT STARTED | Must not begin in this gate |
| Final integration | BLOCKED | Requires all dependency admissions |

## HF #406 exact objects

- PR: [#406](https://github.com/weby-homelab/power-framework/pull/406),
  `OPEN`, `merged=false`.
- Original authorized base:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- Current `main` is
  `4b49e00c75866fa57f71e7bef61547915f7e01db`; the candidate base is stale and
  must be refreshed before normal admission.
- Authorized head:
  `201da2e0e78d1bbf860c98dc653008c0fb4984cd`.
- Authorized head tree:
  `c8d66c9bf65c54b09bb9990380313737af63c932`.
- Authorized head parent:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- GitHub commit verification: `verified=true`, `reason=valid`.
- Before the governance merge, GitHub reported `mergeable=true` and
  `mergeable_state=blocked`; after `main` advanced, the live API returned
  `mergeable=null`, `mergeable_state=unknown` while recalculating the open PR.
  These fields are diagnostic, not standalone authorization or terminal
  failure. Branch freshness and all required checks must be recomputed for a
  new candidate epoch.
- The old exact-head required contexts were successful, but they are not
  admission evidence for a candidate based on the new `main`.
- Intended target: `huggingface-hub 1.30.0`.
- Maintained specifier: `>=1.30.0,<1.31.0`.
- PR #406 dependency diff is limited to `pyproject.toml`,
  `release/web-runtime.requirements.txt`, and `uv.lock`.
- `uv.lock` SHA-256:
  `d8a7456d53bdfc79090f4b3a3b9279664e2662c4f7343100a68db734c167485a`.
- Web export SHA-256:
  `4001e0b073acb7c6eb40bab6047bcb13adedbca3d2a6ebdf23e1b28687b435c3`.

## Governance merge #408

- Branch: `docs/power-3.8-governance-bootstrap`.
- PR: [#408](https://github.com/weby-homelab/power-framework/pull/408),
  `MERGED`, `merged=true`.
- Candidate head:
  `b6f54b0c04da545ba1fe3cd9fa932638d2ff8815`.
- Candidate tree:
  `da33bef8fd4ecd5eafa68e04bb7db21246fb42b4`.
- Candidate parent:
  `3166244bcbc7d6e6757e6b45dbde82b2be4ccbc5`.
- GitHub commit verification: `verified=true`, `reason=valid` at
  `2026-09-08T08:54:20Z`.
- Protected merge SHA:
  `4b49e00c75866fa57f71e7bef61547915f7e01db`.
- Protected merge parents are
  `119d5c39aa2c22734ca72c351f8a70790371678f` and
  `b6f54b0c04da545ba1fe3cd9fa932638d2ff8815`.
- The merged tree contains only governance/handoff paths: nine files total,
  including seven imported source-material files and two append-only handoffs.
- Previous governance epoch: head
  `98f90b36e73e0e43ac77dce3dcf895c9caec1ef9`, tree
  `f9046c678191fa97a9a4a9f29db32cc87b23a164`; it remains retained evidence.

## Gate decision and blockers

```text
GOVERNANCE MERGE = CLOSED / PR #408 MERGED
HF MERGE = BLOCKED / NEW CANDIDATE EPOCH REQUIRED
HF NORMAL MERGE = NOT YET ATTEMPTED FOR CURRENT MAIN
```

The governance PR was accepted through one normal protected merge after fresh
required-check and policy diagnosis. The HF authorization for its old base is
now stale because `main` advanced. Refreshing #406 or creating a replacement is
repair work: record the new tuple, recompute the diff/hashes/tests/security/CI,
and then apply the one-normal-merge-attempt rule to the current candidate.

## Canonical governance status

The pre-HF canonical governance bootstrap is canonical on protected `main`:

- Governance branch: `docs/power-3.8-governance-bootstrap`.
- Governance merge: `4b49e00c75866fa57f71e7bef61547915f7e01db`, with GitHub
  `verified=true`, `reason=valid`.
- Governance PR: [#408](https://github.com/weby-homelab/power-framework/pull/408),
  merged by one ordinary protected merge.
- The prior `docs/power-3.8-premerge-state-publication` branch remains
  provisional evidence and is retained as source material; it is not replaced
  or deleted.
- HF #406 must now be revalidated as a new candidate epoch against current
  `main`; its old evidence is retained but cannot authorize a merge.

## Next authorized work

1. Publish this post-governance state update through a normal protected PR.
2. Merge current `main` into the HF branch or create a verified replacement,
   recording the new base/head/tree/parent tuple and preserving a three-file HF
   diff from current `main`.
3. Recompute lock/export hashes, targeted/full tests, security matrix, remote
   checks, reviews, branch policy, and exact mergeability for the new epoch.
4. Admit and normally merge HF #406 only after its current protected policy
   accepts the exact head.
5. After HF post-merge verification, publish the required post-HF governance
   update.

## Do not start

- HF branch mutation is permitted only as a new candidate epoch with recomputed
  exact base/head/tree/parent, diff, hashes, tests, security, CI, and policy
  evidence.
- Do not merge, auto-merge, force-push, or bypass protection.
- Do not start Actions #396, Phase 5, or later phases.
- Do not bump the public version, create a tag, create a release, or publish
  `POWER 3.8.0`.
- Do not treat candidate or evidence-branch documents as `MERGED MAIN` evidence.

## Cross-links

- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Latest governance handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T091401Z_governance-post-merge_pre-hf.md)
