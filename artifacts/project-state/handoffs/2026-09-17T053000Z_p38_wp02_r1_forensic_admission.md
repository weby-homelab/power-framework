# POWER 3.8 — P38-WP02-R1 Forensic Admission Handoff (PR-R1A)

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-17T05:30:00Z
GATE: P38-WP02-R1 Phase 5D RetrievalPlanner / ContextPack Closure Correction (PR-R1A admission)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-wp02-r1-phase5d-correction-admission
BASE_SHA: 0ea7a92a853c128165f5dcabd9283f5be241263b
BASE_TREE: 08b7f095be8a09053bd9b7ffc64e3918066ad201
STATUS: IN PROGRESS / FORENSIC ADMISSION
```

## 1. Executive Summary

Phase 5D closure is under formal correction. Forensic and runtime audits revealed that PR #440 left
authority-enforcement gaps (PARA folders and dense hits promoted to `CURATED`), failed to stop retrieval
when unsupported `project_ids` were supplied (broad degradation instead of fail-closed), falsely accounted
no-op stages (`GRAPH_ASSISTED`, `RERANK`, `RAW_FALLBACK`) as `attempted`, used `rel_path` as fake source revisions,
invented `Freshness.CURRENT` and `ContradictionState.NONE`, silently swallowed corrupt domain configurations,
and documented an inaccurate byte ceiling.

PR-R1A admits these errata, updates governance projections, blocks Phase 5E, and authorizes a bounded
runtime correction in PR-R1B. No production runtime changes are made in this gate.

```text
PHASE 5D: CLOSURE CORRECTION ADMITTED
P38-WP02-R1: IN PROGRESS
PHASE 5E / P38-WP03: BLOCKED BY P38-WP02-R1
POWER 3.8.0: NO-GO
```

## 2. Live Verification

- Live main: `0ea7a92a853c128165f5dcabd9283f5be241263b`
- Live main tree: `08b7f095be8a09053bd9b7ffc64e3918066ad201`
- Live main parents: `19bab5a8b23f79a69a54ba110bfbffe7a35f64c8`, `65bee0d5501e596e07e5e922de891d93a5f65d85`
- PR #439 merge: `b8ee40ae7df2faf40509b6c6760d884e59cac65a`
- PR #440 candidate: `c6a9a68398ad32cf82ec2af6e838691d43b76aaf`, merge: `19bab5a8b23f79a69a54ba110bfbffe7a35f64c8`
- PR #441 candidate: `65bee0d5501e596e07e5e922de891d93a5f65d85`, merge: `0ea7a92a853c128165f5dcabd9283f5be241263b`
- Branch protection requires exactly 11 contexts. CodeRabbit is informational, not required.
- Public release: `v3.7.13`; Dev package version: `3.7.11`; POWER 3.8.0: NO-GO.

## 3. Changed Artifacts (Docs/Governance Only + Red Tests)

- `docs/plans/POWER_3.8_CURRENT_STATE.md`: admitted P38-WP02-R1, blocked Phase 5E, corrected live main snapshots.
- `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`: added P38-WP02-R1 gate row, marked Phase 5E blocked.
- `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`: blocked Phase 5E gate entry until P38-WP02-R1 completion.
- `docs/plans/README.md`: updated current gate to P38-WP02-R1.
- `artifacts/project-state/phase-5d/PHASE_5D_R1_ADMISSION.md`: detailed forensic admission.
- `artifacts/project-state/phase-5d/PHASE_5D_R1_ERRATUM.md`: erratum table.
- `tests/test_phase5d_r1_closure.py`: 13 red test reproductions marked `@pytest.mark.xfail(strict=True)`.
- This handoff: append-only, preserving all historical records.

## 4. Next Authorized Work

PR-R1B (`fix/p38-wp02-r1-phase5d-runtime-closure`, base = exact protected main after PR-R1A) will:
1. Remove `@pytest.mark.xfail` from `tests/test_phase5d_r1_closure.py`.
2. Implement bounded runtime fixes in `retrieval_planner.py` and `application.py`.
3. Generate `phase5d_r1_verification.json` and `PHASE_5D_R1_REPORT.md`.
4. Pass full regression and two independent reviews (Security & Execution).
