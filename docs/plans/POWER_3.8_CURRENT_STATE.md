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
PRE-HF GOVERNANCE CANDIDATE / HF BLOCKED

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
docs/power-3.8-governance-bootstrap

CANONICAL_GOVERNANCE_COMMIT:
d788825607ae55b9de1142f67ab076f8e533d14d (signed candidate; canonical after protected merge)

CANONICAL_GOVERNANCE_PR:
408 OPEN / PROVISIONAL

LATEST_HANDOFF:
artifacts/project-state/handoffs/2026-09-08T082529Z_governance-bootstrap_pre-hf.md
```

## Fresh state anchor

- Repository: [weby-homelab/power-framework](https://github.com/weby-homelab/power-framework).
- State was read from GitHub REST during this session. Every future agent must
  fetch and revalidate the mutable values below before acting.
- OBSERVED_AT_UTC: `2026-09-08T08:13:35Z`.
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
- GitHub reports `mergeable=true`, `mergeable_state=blocked` at the observation
  above. This field is diagnostic, not a standalone authorization or terminal
  failure: required checks, review requirements, unresolved conversations,
  branch freshness, rulesets, queue, and deployment policy must be diagnosed
  before one normal protected-merge attempt.
- At this observation, all 11 published required contexts for #406 were
  successful, branch protection required zero approving reviews, and no
  unresolved review conversation was reported. The remaining `blocked` reason
  is not inferred from those facts and remains subject to the protected merge
  admission test.

## Governance candidate #408

- Branch: `docs/power-3.8-governance-bootstrap`.
- PR: [#408](https://github.com/weby-homelab/power-framework/pull/408),
  `OPEN`, `merged=false`.
- Candidate head:
  `d788825607ae55b9de1142f67ab076f8e533d14d`.
- Candidate tree:
  `380cba0de80d622e4db109be168f642eaaddd1ea`.
- Candidate parent:
  `119d5c39aa2c22734ca72c351f8a70790371678f`.
- GitHub commit verification: `verified=true`, `reason=valid` at
  `2026-09-08T08:23:57Z`.
- The candidate contains only the seven governance/handoff files listed in
  the PR body; remote required checks are pending for this new head.
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
HF MERGE = PENDING POLICY DIAGNOSIS / ADMISSION
NORMAL MERGE = NOT YET ATTEMPTED FOR THIS OBSERVATION
FRESH CHATGPT AUDIT REQUIRED
```

The exact authorization text supplied for PR #406 does not override fresh
GitHub state. Authenticated REST inspection is available and shows the
required-check and review-policy values above; `mergeable_state=blocked` still
requires diagnosis, not a magic-string stop. A normal merge attempt must use
the exact current head guard, at most once for this candidate epoch, with no
bypass or retry loop.

## Canonical governance status

The pre-HF canonical governance bootstrap has started from live `main`:

- Governance branch: `docs/power-3.8-governance-bootstrap`.
- Governance commit: `d788825607ae55b9de1142f67ab076f8e533d14d`, locally and
  GitHub-verified signed candidate.
- Governance PR: [#408](https://github.com/weby-homelab/power-framework/pull/408),
  open/provisional until protected merge.
- The prior `docs/power-3.8-premerge-state-publication` branch remains
  provisional evidence and is retained as source material; it is not replaced
  or deleted.
- A governance merge before HF is permitted when GitHub's protected normal
  merge policy accepts it. If `main` advances, #406 must be revalidated as a
  new candidate epoch rather than treated as failed evidence.

## Next authorized work

1. Validate and publish this pre-HF governance candidate through a normal
   protected PR.
2. Revalidate `main`, #406, required checks, reviews, conversations, rulesets,
   queue/deployment requirements, and exact Git objects immediately before any
   normal merge attempt.
3. If governance merges first, record the new `main` and rebuild or merge it
   into the HF candidate as a new candidate epoch; old evidence becomes stale,
   not fatal.
4. Admit HF #406 only after its current exact tuple and protected policy pass.
5. After HF post-merge verification, publish a new governance state update.

## Do not start

- Do not mutate the HF branch without recording a new candidate epoch and
  recomputing its exact base/head/tree/parent, diff, hashes, tests, security,
  CI, and policy evidence.
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
- [Latest governance handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T081335Z_governance-bootstrap_pre-hf.md)
