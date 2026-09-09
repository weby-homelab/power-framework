# POWER 3.8 — Current State

> **Publication class:** governance state projection. Before a protected merge,
> this branch is provisional; after a protected merge, the same repository
> paths are canonical for the recorded snapshot. Mutable GitHub values below
> remain subject to fresh live verification.

## Machine-readable recovery header

```text
PROJECT_STATE_SCHEMA:
power.project-state.v2

PUBLIC_VERSION:
3.7.11

DEVELOPMENT_TARGET:
3.8.0

STATE_STATUS:
CONTROLLED DEPENDENCY REFRESH CLOSED / FINAL INTEGRATION VERIFIED / V2 PLANNING RECORDED

SNAPSHOT_BASE_SHA:
a386858a45489eb5db213d42ffe773db9134ff88

SNAPSHOT_BASE_TREE:
664f34995961a2990dee00ecde0ebe7c8ed0f5d8

SNAPSHOT_LAST_INCLUDED_PR:
396

CURRENT_LIVE_MAIN:
RESOLVE_FROM_GITHUB

LIVE_MAIN_REVALIDATION_REQUIRED:
YES

LAST_CLOSED_GATE:
Controlled Dependency Refresh — Final Integration

NEXT_GATE:
Pre-Phase-5 Foundation Hardening Admission

ACTIONS_396:
CLOSED / MERGED

LAST_MERGED_PR:
396

HF_PR:
406 MERGED / POST-MERGE VERIFIED

PHASE_5:
BLOCKED / NOT STARTED

PHASE_5_IMPLEMENTATION:
BLOCKED / NOT STARTED

FOUNDATION_HARDENING:
NEXT GATE / PLANNED / NOT STARTED

PHASES_0_4:
CLOSED / FROZEN

PHASES_6_9:
NOT STARTED

RELEASE_3_8_0:
NO-GO

CANONICAL_GOVERNANCE_BRANCH:
docs/power-3.8-final-integration-course-correction

CANONICAL_GOVERNANCE_COMMIT:
RESOLVE_FROM_GITHUB

CANONICAL_GOVERNANCE_PR:
RESOLVE_FROM_GITHUB

LATEST_HANDOFF:
artifacts/project-state/handoffs/2026-09-09T065950Z_controlled-dependency-refresh_final-integration.md

CONTEXT_MEMORY_ARCHITECTURE_PLAN:
docs/plans/POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md

PLANNING_CONTRACTS:
artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json

RETAINED_V1_CONTRACTS:
artifacts/project-state/planning/context-retrieval-contracts-v1.schema.json
artifacts/project-state/planning/index-cost-policy-v1.json

RETRIEVAL_EVAL_CONTRACT:
artifacts/project-state/planning/retrieval-eval-v1.schema.json

FOUNDATION_HARDENING_GATE:
artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md

RETAINED_V1_INDEX_COST_POLICY:
artifacts/project-state/planning/index-cost-policy-v1.json

ACTIVE_BUDGET_CONTRACT:
artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json

PHASE_ACCEPTANCE_GATES:
artifacts/project-state/planning/phase5-9-acceptance-gates.md

ARCHITECTURE_STATUS:
CANONICAL PLANNING V2 / NOT IMPLEMENTED
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
- The protected `main` observed for this final-integration snapshot was
  `a386858a45489eb5db213d42ffe773db9134ff88` with tree
  `664f34995961a2990dee00ecde0ebe7c8ed0f5d8`.
- `SNAPSHOT_BASE_SHA` and `SNAPSHOT_BASE_TREE` are immutable snapshot anchors.
  They are not a mutable substitute for a fresh live-main read.
- The governance branch/head/merge objects for this PR are resolved from live
  GitHub after protected publication; no future SHA is written here.
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
- Context / Memory / Retrieval architecture: **CANONICAL PLANNING V2 / NOT IMPLEMENTED**.
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
| Actions #396 | CLOSED / MERGED | Exact head/tree/parent and protected merge are retained below |
| PR #402 | DEFERRED / CLOSED WITHOUT MERGE | Broad maintenance bundle; split future admissions required |
| PR #407 | SUPERSEDED / CLOSED WITHOUT MERGE | Historical pre-HF evidence retained for auditability |
| Final integration | CLOSED / FINAL INTEGRATION VERIFIED | Current main graph, locks/exports, tests, security, package, upgrade, Docs, and CodeQL passed |
| Foundation Hardening | PLANNED / NOT STARTED / NEXT GATE | F1–F5 contract before Phase 5 |

## Actions #396 exact objects

- PR: [#396](https://github.com/weby-homelab/power-framework/pull/396),
  `CLOSED / MERGED`.
- Candidate head: `147afac8f4b43a967207309d69ccad78c6d16739`.
- Candidate tree: `664f34995961a2990dee00ecde0ebe7c8ed0f5d8`.
- Candidate parents: `a715df08b34a0c561e487199ff56a2853279d951` and
  `64178e9d2791fc8a291ac647374efc566f201f0e`.
- Candidate GitHub verification: `verified=true`, `reason=valid`.
- Protected merge: `a386858a45489eb5db213d42ffe773db9134ff88`.
- Merge parents: `64178e9d2791fc8a291ac647374efc566f201f0e` and
  `147afac8f4b43a967207309d69ccad78c6d16739`.
- Merge tree equals candidate tree exactly; the four intended workflow files
  are the complete Actions diff.
- No admin bypass, protection bypass, force merge, or auto-merge was used.

## Final integration evidence

- Live protected `main`: `a386858a45489eb5db213d42ffe773db9134ff88`, tree
  `664f34995961a2990dee00ecde0ebe7c8ed0f5d8`, GitHub `verified=true`.
- Required protected contexts were freshly enumerated from REST: `test (3.13)`,
  `test (3.14)`, `security`, `package-smoke`, `upgrade-matrix (ubuntu-latest)`,
  `upgrade-matrix-aggregate`, `base-runtime-smoke`, `benchmark-integrity`,
  `analyze (python)`, `CodeQL`, and `build`.
- Exact-main local validation: `uv lock --check`, `uv sync --locked`, pip check,
  Ruff, format, MyPy, strict MkDocs, and pip-audit passed.
- Frozen regression: 346 targeted PSE/Task/Decision/crash tests passed; full
  hermetic suite passed with `1775 passed, 4 skipped, 17 deselected`, coverage
  `83.06%`.
- Security subset: `147 passed`; package smoke, neural contract, base runtime,
  upgrade matrix/aggregate, benchmark integrity, outcome, and continuity gates
  passed. No model was downloaded.
- Remote CI, Docs, and CodeQL workflow runs for current main were successful.
- `artifact-metadata: write` is not a current POWER requirement; existing
  attestation permissions remain unchanged.

## Stale PR dispositions

| PR | Exact head | Exact base | Disposition |
|---|---|---|---|
| #402 | `555748e07f4ef2d61dc08dc0b3cb4c8d92b913d0` | `2d8058854ffbfae8526095af9809ab2c6f9c04f6` | `CLOSED WITHOUT MERGE / DEFERRED`; failed package-smoke, broad incompatible bundle |
| #407 | `a3f8cb5f0cfd7e5b37ea316146a4e761a99a46e2` | `119d5c39aa2c22734ca72c351f8a70790371678f` | `CLOSED WITHOUT MERGE / SUPERSEDED HISTORICAL EVIDENCE`; unsigned stale pre-HF snapshot |

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

- Prior governance bootstrap PR #408 merge:
  `4b49e00c75866fa57f71e7bef61547915f7e01db`.
- Post-governance state PR #409 merge:
  `0400aea20776715d801339de325ba0cba65fab10`.
- CI admission repair PR #410 merge:
  `7ed70766904e394d9717fe3fb7e18ed079e1887b`.
- HF PR #406 merge:
  `2d8058854ffbfae8526095af9809ab2c6f9c04f6`.
- Post-HF governance publication PR #411 merge:
  `d8b704f6125347ff9f9c39981193807d2160b135`.

## Gate decision and blockers

```text
CONTROLLED DEPENDENCY REFRESH = CLOSED / FINAL INTEGRATION VERIFIED
PR #402 = CLOSED WITHOUT MERGE / DEFERRED
PR #407 = CLOSED WITHOUT MERGE / SUPERSEDED HISTORICAL EVIDENCE
ACTIONS #396 = CLOSED / MERGED
FOUNDATION HARDENING = NEXT GATE / PLANNED / NOT STARTED
PHASE 5 = BLOCKED / NOT STARTED
```

The dependency surfaces and Actions admission were accepted through normal
protected merges or explicit bounded deferral after fresh required-check,
security, package, regression, and policy diagnosis. The current next gate is
Foundation Hardening. POWER 3.8.0 cannot be released from this state.

## Canonical governance status

The prior governance and dependency merges are canonical on protected `main`;
this consolidated course-correction branch becomes the next canonical snapshot
only after its protected normal merge:

- Governance branch: `docs/power-3.8-final-integration-course-correction`.
- Prior governance bootstrap merge: `4b49e00c75866fa57f71e7bef61547915f7e01db`,
  with GitHub `verified=true`, `reason=valid`.
- The final governance PR and protected merge SHA are intentionally resolved
  from GitHub after publication; no future SHA is fabricated in this snapshot.
- Post-governance state PR #409 and CI admission repair PR #410 are merged on
  protected `main`.
- The prior `docs/power-3.8-premerge-state-publication` branch remains
  provisional evidence and is retained as source material; it is not replaced
  or deleted.
- HF #406 and Actions #396 are closed by protected merges; their candidate
  epochs remain retained evidence for the dependency-refresh audit.

## Next authorized work

1. Independently audit and admit Pre-Phase-5 Foundation Hardening from fresh
   live `main`.
2. If Foundation Hardening passes, create a fresh bounded Phase 5A candidate
   from the then-current protected `main`; do not start Phase 5 in this gate.
3. Keep Phase 5–9 runtime work, version bumps, tags, releases, and POWER 3.8.0
   publication blocked until each declared gate is independently closed.

## Do not start

- Do not reopen or mutate the closed Actions #396 admission; any future
  dependency candidate must record its exact base/head/tree/parent, diff,
  hashes, tests, security, CI, and policy evidence.
- Do not merge, auto-merge, force-push, or bypass protection.
- Do not start Foundation Hardening implementation, Phase 5, or later phases
  from this governance gate.
- Do not bump the public version, create a tag, create a release, or publish
  `POWER 3.8.0`.
- Do not treat candidate or evidence-branch documents as `MERGED MAIN` evidence.

## Cross-links

- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Architecture planning](POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md)
- [Planning artifacts](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/planning/README.md)
- [Latest final-integration handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/)
- [Historical HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)
