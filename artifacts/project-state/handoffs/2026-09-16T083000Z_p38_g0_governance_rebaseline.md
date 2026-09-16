# POWER 3.8 — Gate P38-G0 Governance Rebaseline Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T08:30:00Z
GATE: P38-G0 (Governance Rebaseline)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-g0-governance-rebaseline
BASE_SHA: 3cb94ff7f82d18c0f77b336848d1c34f220e58a3
BASE_TREE: 03c2689023e2e2213cd47f243f8fb46a6f626fcc
```

---

## 1. Objective & Scope

Bring mutable POWER governance projections into complete agreement with live repository facts:
- Live main: `3cb94ff7f82d18c0f77b336848d1c34f220e58a3` (includes PR #420, #422, #423, #424).
- Maintenance line `release/3.7`: `44a3dd71fc14b4c45e3c379b5728c27395727560` (tags `v3.7.12`, `v3.7.13`).
- Reconcile PR #421 disposition: closed as SUPERSEDED / CLOSED WITHOUT MERGE.
- Remove internal pseudo-SemVer work-package labels (3.7.12–3.7.22) and replace with explicit P38 governance and work-package identifiers (P38-G0, P38-G1, P38-G2, P38-WP01..P38-WP13).
- Rebaseline phase progression order: P38-G0 -> P38-G1 -> P38-G2 -> Phase 5C (SearchScope Pushdown).
- No runtime code, dependencies, or schemas modified.

---

## 2. Invariants & Distinctions

- **Public stable release:** `v3.7.13` (on `release/3.7`, tags `v3.7.12`, `v3.7.13`).
- **Development main package metadata:** `3.7.11` in `pyproject.toml`.
- **Release discipline:** `PUBLIC_RELEASE_VERSION != automatically MAIN_PACKAGE_VERSION`. No version bump or release authorized by documentation reconciliation alone.
- **Phase 5C readiness:** `READY FOR SEPARATE ADMISSION / NOT STARTED` (gated by G0, G1, G2).
- **Phase 5D–5H:** `PLANNED / NOT STARTED`.
- **Phases 6–9:** `PLANNED / NOT STARTED`.
- **POWER 3.8.0:** `NO-GO`.

---

## 3. Findings & Decisions Resolved

1. **Finding A (Roadmap Phase Status):**
   Disaggregated Phase 5C–5H into explicit P38-WP identifiers. Phase 5C is ready for separate admission; Phase 5D–5H are planned/unstarted.
2. **Finding B (INFRA-1 Fail-Closed Completeness):**
   Added authoritative fail-closed rule for missing, stale, or contradictory required framework evidence.
3. **Finding C (Packet 05 Handoff Identity):**
   Recorded exact historical immutable evidence for merged PR #420 in `artifacts/project-state/handoffs/2026-09-15T090637Z_infra1_governance_reconciliation.md`.
4. **Finding D (Planning Index Navigation):**
   Updated `artifacts/project-state/planning/README.md` and `docs/plans/README.md` to link both implementation and governance reconciliation handoffs.
5. **PR #421 Disposition:**
   Closed as SUPERSEDED / CLOSED WITHOUT MERGE. Fresh P38-G0 branch created from current protected `main`.
6. **Work-Package SemVer Removal:**
   Removed pseudo-SemVer labels `3.7.12`–`3.7.22` from `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`. Replaced with `P38-G0`..`G2` and `P38-WP01`..`WP13`.

---

## 4. Exact Files Modified

1. `docs/plans/POWER_3.8_CURRENT_STATE.md`
2. `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`
3. `artifacts/project-state/planning/phase5-9-acceptance-gates.md`
4. `artifacts/project-state/planning/README.md`
5. `docs/plans/README.md`
6. `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`
7. `artifacts/project-state/handoffs/2026-09-15T090637Z_infra1_governance_reconciliation.md`
8. `artifacts/project-state/handoffs/2026-09-16T083000Z_p38_g0_governance_rebaseline.md` (this file)

---

## 5. Candidate Tuple

- **Branch:** `docs/p38-g0-governance-rebaseline`
- **Base SHA:** `3cb94ff7f82d18c0f77b336848d1c34f220e58a3`
- **Base Tree:** `03c2689023e2e2213cd47f243f8fb46a6f626fcc`
- **Candidate Head SHA:** (resolved upon signed commit)
- **Candidate Tree:** (resolved upon signed commit)
- **Parent:** `3cb94ff7f82d18c0f77b336848d1c34f220e58a3`
- **Target PR:** (to be opened against main)
