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
HF ADMISSION CLOSED / POST-HF VERIFICATION COMPLETE

STATE_BASE_SHA:
2d8058854ffbfae8526095af9809ab2c6f9c04f6

CURRENT_MAIN_SHA:
2d8058854ffbfae8526095af9809ab2c6f9c04f6

ACTIVE_GATE:
Controlled Dependency Refresh — Actions #396 supply-chain admission

LAST_CLOSED_GATE:
HF #406 Admission — protected normal merge and post-merge verification

LAST_MERGED_PR:
406

HF_PR:
406 MERGED / POST-MERGE VERIFIED

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
artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md
```

## Fresh state anchor

- Repository: [weby-homelab/power-framework](https://github.com/weby-homelab/power-framework).
- State was read from GitHub REST during this session. Every future agent must
  fetch and revalidate the mutable values below before acting.
- PRE_GOVERNANCE_OBSERVED_AT_UTC: `2026-09-08T08:13:35Z`.
- GOVERNANCE_POLICY_OBSERVED_AT_UTC: `2026-09-08T08:45:01Z`.
- POST_GOVERNANCE_OBSERVED_AT_UTC: `2026-09-08T09:14:03Z`.
- HF_MERGE_OBSERVED_AT_UTC: `2026-09-08T09:53:10Z`.
- The pre-governance verified base anchor was
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- Current protected `main` is
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Governance merge tree:
  `da33bef8fd4ecd5eafa68e04bb7db21246fb42b4`.
- Governance merge parents:
  `119d5c39aa2c22734ca72c351f8a70790371678f` and
  `b6f54b0c04da545ba1fe3cd9fa932638d2ff8815`.
- HF merge tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- HF merge parents:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b` and
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
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
| CI admission repair | CLOSED | PR #410 protected merge on `main` |
| HF admission | CLOSED | PR #406 protected merge and post-merge checks |
| Actions #396 | HOLD / NOT STARTED | Must not begin in this gate |
| Final integration | BLOCKED / NEXT AFTER ACTIONS | Requires the Actions admission |

## HF #406 exact objects

- PR: [#406](https://github.com/weby-homelab/power-framework/pull/406),
  `MERGED`, `merged=true`.
- Base at final admission:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- Final head:
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- Final head tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- Final head parents:
  `75f3d7dad242566887fe77b5c64cd5b64aaa0576` and
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- GitHub commit verification: `verified=true`, `reason=valid`.
- Protected merge SHA:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Protected merge parents:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b` and
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- Protected merge tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- The final normal merge used exact-head guard `c385073…`; no bypass or force
  operation was used.
- Intended target: `huggingface-hub 1.30.0`.
- Maintained specifier: `>=1.30.0,<1.31.0`.
- PR #406 dependency diff is limited to `pyproject.toml`,
  `release/web-runtime.requirements.txt`, and `uv.lock`.
- `uv.lock` SHA-256:
  `d8a7456d53bdfc79090f4b3a3b9279664e2662c4f7343100a68db734c167485a`.
- Web export SHA-256:
  `4001e0b073acb7c6eb40bab6047bcb13adedbca3d2a6ebdf23e1b28687b435c3`.

## HF merge #406

- PR: [#406](https://github.com/weby-homelab/power-framework/pull/406),
  `MERGED`, `merged=true`.
- Final HF head:
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- Final HF head tree:
  `a5f63eb671d3d57dd304d497cef4c03c52ed340b`.
- GitHub head verification: `verified=true`, `reason=valid` at
  `2026-09-08T09:49:03Z`.
- Protected merge SHA:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Protected merge parents are
  `7ed70766904e394d9717fe3fb7e18ed079e1887b` and
  `c385073583dc00dc7752169eb36f66ecdd7f4361`.
- The merged tree preserves the three-file HF dependency diff and the CI
  trigger repair already present on `main`.

## Governance and CI merge history

- Governance PR #408 merge: `4b49e00c75866fa57f71e7bef61547915f7e01db`.
- Post-governance state PR #409 merge:
  `0400aea20776715d801339de325ba0cba65fab10`.
- CI admission repair PR #410 merge:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- HF PR #406 merge:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.

## Gate decision and blockers

```text
GOVERNANCE MERGE = CLOSED / PR #408 MERGED
CI ADMISSION REPAIR = CLOSED / PR #410 MERGED
HF ADMISSION = CLOSED / PR #406 MERGED
ACTIONS #396 = NEXT GATE / HOLD / NOT STARTED
```

The governance, CI-admission, and HF PRs were each accepted through one normal
protected merge after fresh required-check and policy diagnosis. The current
next gate is Actions #396; it remains intentionally unstarted. POWER 3.8.0
cannot be released from this state.

## Canonical governance status

The governance bootstrap is canonical on protected `main`:

- Governance branch: `docs/power-3.8-governance-bootstrap`.
- Governance merge: `4b49e00c75866fa57f71e7bef61547915f7e01db`, with GitHub
  `verified=true`, `reason=valid`.
- Governance PR: [#408](https://github.com/weby-homelab/power-framework/pull/408),
  merged by one ordinary protected merge.
- Post-governance state PR #409 and CI admission repair PR #410 are merged on
  protected `main`.
- The prior `docs/power-3.8-premerge-state-publication` branch remains
  provisional evidence and is retained as source material; it is not replaced
  or deleted.
- HF #406 is closed by the protected merge above; its candidate epochs remain
  retained evidence for the dependency-refresh audit.

## Next authorized work

1. Hold and independently revalidate Actions #396 in a later bounded session;
   do not start it automatically from this handoff.
2. If #396 is authorized, create a fresh candidate epoch from current `main`
   and run its full supply-chain/security/CI admission.
3. Keep Phase 5–9, version bumps, tags, releases, and POWER 3.8.0 publication
   blocked until all declared gates are independently closed.

## Do not start

- Actions #396 is not to be mutated or started in this session; any future
  candidate must record its exact base/head/tree/parent, diff, hashes, tests,
  security, CI, and policy evidence.
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
- [Latest HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)
