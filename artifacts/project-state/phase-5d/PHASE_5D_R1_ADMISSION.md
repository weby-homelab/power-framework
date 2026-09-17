# Phase 5D (P38-WP02) Closure Correction Admission — P38-WP02-R1 (PR-R1A)

```text
EVIDENCE_TYPE: phase5d_r1_admission
CREATED_AT_UTC: 2026-09-17T05:30:00Z
BASE_SHA: 0ea7a92a853c128165f5dcabd9283f5be241263b
BASE_TREE: 08b7f095be8a09053bd9b7ffc64e3918066ad201
BASE_PARENTS: 19bab5a8b23f79a69a54ba110bfbffe7a35f64c8, 65bee0d5501e596e07e5e922de891d93a5f65d85
PUBLIC_STABLE: v3.7.13
MAIN_PACKAGE_VERSION: 3.7.11
POWER_3_8_0: NO-GO
STATUS: P38-WP02-R1 IN PROGRESS / FORENSIC ADMISSION
```

## 1. Gate Status

```text
PHASE 5D: CLOSURE CORRECTION ADMITTED
P38-WP02-R1: IN PROGRESS (PR-R1A admission; PR-R1B runtime correction pending)
PHASE 5E / P38-WP03: BLOCKED BY P38-WP02-R1 / NOT STARTED
POWER 3.8.0: NO-GO
```

Phase 5E shadow benchmarks, holdout tuning, default planner switch, Phase 5F dirty-set/index validity work,
Phase 5G public MCP context tools, Phase 6 capture, A2A, AGE, pgvector, PostgreSQL, version bumps, tags,
and releases are strictly forbidden until P38-WP02-R1 is closed, merged protected, and post-merge verified.

This PR-R1A branch introduces forensic errata, governance admissions, and red tests only. No production runtime changes.

## 2. Live Starting State (Independently Re-Fetched from GitHub API & Git Objects)

```text
LIVE MAIN: 0ea7a92a853c128165f5dcabd9283f5be241263b
LIVE MAIN TREE: 08b7f095be8a09053bd9b7ffc64e3918066ad201
LIVE MAIN PARENTS: 19bab5a8b23f79a69a54ba110bfbffe7a35f64c8, 65bee0d5501e596e07e5e922de891d93a5f65d85
REQUIRED MAIN CONTEXTS: 11
PUBLIC RELEASE: v3.7.13
DEV PACKAGE VERSION: 3.7.11
POWER 3.8.0: NO-GO
```

Required contexts from live branch protection (`branches/main/protection`, exact 11):

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

## 3. Forensic Errata Admitted

### Erratum F1 — PR #439 Tuple Verification

Live Git objects for PR #439 resolve to:

```text
PR: #439
base SHA: 6ee9f34a09fdfd02a0122bdac95ae32a5485220f
base tree: b2a2ac57d62d7548165497a7dadc918849a75818
head SHA: 79888f6f1ccae77b91feb815e6a5bb4d5dc2afec
head tree: f87f6a33395a0d5e02ca162b3567637024d8dd01
head parents: 484bd9c657fa1629244e65060ff9ed79c608de65
merge SHA: b8ee40ae7df2faf40509b6c6760d884e59cac65a
merge tree: f87f6a33395a0d5e02ca162b3567637024d8dd01
merge parents: 6ee9f34a09fdfd02a0122bdac95ae32a5485220f, 79888f6f1ccae77b91feb815e6a5bb4d5dc2afec
merged_at: 2026-09-16T14:26:19Z
verification: valid (GitHub web-flow key B5690EEEBB952194)
```

### Erratum F2 — PR #440 Tuple Verification

Live Git objects for PR #440 resolve to:

```text
PR: #440
base SHA: b8ee40ae7df2faf40509b6c6760d884e59cac65a
base tree: f87f6a33395a0d5e02ca162b3567637024d8dd01
head SHA: c6a9a68398ad32cf82ec2af6e838691d43b76aaf
head tree: 9071a95b1cfd072a64d008afd488c5c847f374c8
head parents: d10558d3ee8e2ee2ba739055b7eff9aea07f40f2
merge SHA: 19bab5a8b23f79a69a54ba110bfbffe7a35f64c8
merge tree: 9071a95b1cfd072a64d008afd488c5c847f374c8
merge parents: b8ee40ae7df2faf40509b6c6760d884e59cac65a, c6a9a68398ad32cf82ec2af6e838691d43b76aaf
merged_at: 2026-09-16T19:20:13Z
verification: valid (GitHub web-flow key B5690EEEBB952194)
```

Narrative shorthand `c6a9a68a...` or stale tree references are superseded by exact Git object inspection.

### Erratum F3 — Invalid Phase 5D Evidence Base SHA

Historical `artifacts/project-state/phase-5d/phase5d_verification.json` and `PHASE_5D_REPORT.md` recorded:

```text
base_sha: b8ee40ab1286c12ad12a78f28877bc9da924ebf4
```

That SHA does not exist in the repository object store. The correct base SHA for PR #440 is `b8ee40ae7df2faf40509b6c6760d884e59cac65a`.
Historical artifacts remain preserved append-only; this admission and `PHASE_5D_R1_ERRATUM.md` provide canonical errata.

### Erratum F4 — Required-Check Accounting

Live branch protection requires 11 contexts. Historical closure narratives claiming `12/12 required including CodeRabbit`
confused total check-runs (12: 11 required SUCCESS + 1 deploy SKIPPED) with required protection contexts. CodeRabbit is an
external informational app, not a required branch-protection status check.

### Erratum F5 — ContextPack Byte Limit Documentation Drift

Actual runtime constant:

```text
MAX_CONTEXT_PACK_BYTES = 2_000_000
```

Historical report claimed `256_000`. Runtime constant is preserved at 2,000,000; documentation is corrected to match code.

## 4. Suspected Runtime Defects Admitted for PR-R1B Reproduction

1. **Defect R1 (Unsupported Project Scope Must Fail Closed):**
   `QueryIntent.project_ids` -> `RetrievalPlanner` -> `SearchScope.project_ids`. Non-empty `project_ids` is currently unsupported by the SQLite storage layer. `RetrievalPlanner.retrieve()` previously caught `compile_search_scope` exceptions and continued with broad retrieval. Invariant requires fail-closed typed error before any candidate read.

2. **Defect R2 (Domain/Path and Dense Stage Authority Promotion):**
   FTS results in `01_Projects/`, `02_Areas/`, `03_Resources/` and all dense vector hits were unconditionally promoted to `Authority.CURATED`, `TrustState.CURATED`, `AuthorityBasis.CURATED_NOTE`. This violates `DOMAIN != AUTHORITY`, `PATH != AUTHORITY`, and `RETRIEVAL STAGE != AUTHORITY`. Authority must default to `UNVERIFIED` unless proven by explicit provenance.

3. **Defect R3 (Execution Trace False Accounting):**
   `GRAPH_ASSISTED`, `RERANK`, and `RAW_FALLBACK` were added to `attempted_stages` without actual execution boundary invocation. Required invariant: `ATTEMPTED` means actual runtime execution attempt. No-op stages must be marked `SKIPPED` with explicit skip reasons.

4. **Defect R4 (Provenance Revisions, Freshness, and Contradictions):**
   Ordinary search results used `rel_path` as fake `source_revision`, assumed `Freshness.CURRENT` without temporal proof, and assumed `ContradictionState.NONE` without contradiction analysis. Source revisions must use real content digests or explicit `"unknown"`. Unproven freshness and contradiction must be `UNKNOWN`.

5. **Defect R5 (Domain Policy & Scope Compilation Failure Behavior):**
   `_get_domain_registry()` swallowed exceptions and fell back to empty registry on corrupt configuration. Corrupt explicit policy must fail closed.

6. **Defect R6 (Multi-Domain Dedup Authority Preservation):**
   Dedup must not detach authority claims from supporting provenance or combine high unverified semantic scores with canonical ledger provenance.

## 5. Pre-Fix Red Tests

Executable reproduction tests have been authored in `tests/test_phase5d_r1_closure.py` covering all 13 required defect items.
In PR-R1A, these tests are marked with `@pytest.mark.xfail(strict=True)` to confirm pre-fix failure while preserving clean CI gates.
In PR-R1B, the runtime fix will unmark them and verify that all 13 pass.
