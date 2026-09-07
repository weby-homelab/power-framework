# POWER 3.8 — Current State

> **Publication class:** blocked-state evidence only. This document is published
> on the evidence branch named in the handoff; it is not evidence of a merged
> `main` state and does not authorize a governance bootstrap.

## Machine-readable recovery header

```text
PROJECT_STATE_SCHEMA:
power.project-state.v1

PUBLIC_VERSION:
3.7.11

DEVELOPMENT_TARGET:
3.8.0

STATE_STATUS:
PRE-MERGE BLOCKED / EVIDENCE BRANCH ONLY

STATE_BASE_SHA:
119d5c39aa2c22734ca72c351f8a70790371678f

CURRENT_MAIN_SHA:
119d5c39aa2c22734ca72c351f8a70790371678f

ACTIVE_GATE:
Controlled Dependency Refresh — HF #406 exact-head admission

LAST_CLOSED_GATE:
Controlled Dependency Refresh — WEB-01 / WEB-05 security closure

LAST_MERGED_PR:
405

HF_PR:
406 OPEN / NOT MERGED

PHASE_5:
BLOCKED / NOT STARTED

RELEASE_3_8_0:
NO-GO

CANONICAL_GOVERNANCE_BRANCH:
NOT CREATED

CANONICAL_GOVERNANCE_COMMIT:
NOT CREATED

CANONICAL_GOVERNANCE_PR:
NOT CREATED

LATEST_HANDOFF:
artifacts/project-state/handoffs/2026-09-07T234711Z_hf-406_pre-merge-blocked.md
```

## Fresh state anchor

- Repository: [weby-homelab/power-framework](https://github.com/weby-homelab/power-framework).
- State was read from GitHub REST during this session. Every future agent must
  fetch and revalidate the mutable values below before acting.
- The local verified base anchor is
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
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
| HF admission | BLOCKED / NOT MERGED | PR #406, exact head below |
| Actions #396 | HOLD / NOT STARTED | Must not begin in this gate |
| Final integration | BLOCKED | Requires all dependency admissions |

## HF #406 exact objects

- PR: [#406](https://github.com/weby-homelab/power-framework/pull/406),
  `OPEN`, `merged=false`.
- Authorized base and current base:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- Authorized head:
  `201da2e0e78d1bbf860c98dc653008c0fb4984cd`.
- Authorized head tree:
  `c8d66c9bf65c54b09bb9990380313737af63c932`.
- Authorized head parent:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- GitHub commit verification: `verified=true`, `reason=valid`.
- GitHub reports `mergeable=true`, but
  `mergeable_state=unstable`; this is not the required normal-merge admission
  state.
- Intended target: `huggingface-hub 1.30.0`.
- Maintained specifier: `>=1.30.0,<1.31.0`.
- PR diff is limited to `pyproject.toml`,
  `release/web-runtime.requirements.txt`, and `uv.lock`.
- `uv.lock` SHA-256:
  `d8a7456d53bdfc79090f4b3a3b9279664e2662c4f7343100a68db734c167485a`.
- Web export SHA-256:
  `4001e0b073acb7c6eb40bab6047bcb13adedbca3d2a6ebdf23e1b28687b435c3`.

## Gate decision and blockers

```text
HF MERGE = BLOCKED
NORMAL MERGE POLICY NOT SATISFIED
FRESH CHATGPT AUDIT REQUIRED
```

The exact authorization text supplied for PR #406 does not override a fresh
GitHub state that is not admitted for normal merge. The authenticated local
GitHub CLI credential was invalid during the session, so branch-protection and
some review-policy details were not fully observable. No bypass or retry loop
is permitted.

## Canonical governance status

The canonical post-HF governance bootstrap has **not** started:

- Governance branch: **NOT CREATED**.
- Governance commit: **NOT CREATED**.
- Governance PR: **NOT CREATED**.
- The current `docs/power-3.8-premerge-state-publication` branch is an evidence
  publication branch only; it is not the post-HF governance branch.

## Next authorized work

1. Restore authenticated GitHub REST observability without exposing credentials.
2. Fetch `main` and PR #406 independently.
3. Verify exact PR, base, head, tree, parent, checks, reviews, protection policy,
   and `mergeable_state=normal`.
4. Obtain or revalidate independent authorization for one normal merge attempt.
5. If and only if HF post-merge verification passes, create the canonical
   governance package from the verified post-HF `main`.

## Do not start

- Do not modify or rebase the HF branch.
- Do not merge, auto-merge, force-push, or bypass protection.
- Do not start Actions #396, Phase 5, or later phases.
- Do not bump the public version, create a tag, create a release, or publish
  `POWER 3.8.0`.
- Do not treat candidate or evidence-branch documents as `MERGED MAIN` evidence.

## Cross-links

- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Handoff protocol](../../artifacts/project-state/handoffs/README.md)
- [Latest blocked-state handoff](../../artifacts/project-state/handoffs/2026-09-07T234711Z_hf-406_pre-merge-blocked.md)
