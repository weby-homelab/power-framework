# POWER 3.3.0 execution tracker

**Status:** historical repository mirror of [GitHub epic #195](https://github.com/weby-homelab/power-framework/issues/195).
The current authoritative phase map is
[`brain/01_Projects/Fact_n_Plan_Power_3.2.5-3.3.0.md`](https://github.com/weby-homelab/knowledge-base/blob/main/01_Projects/Fact_n_Plan_Power_3.2.5-3.3.0.md).
**Owner:** Weby Homelab. **Current release baseline:** `v3.2.6` release
candidate; the final tag commit/tree is recorded in
`release/evidence/baselines/v3.2.6.json` after publication.

**Phase 0–1 delivery:** release `v3.2.5` contains the release foundation and
crash-atomic generation store. Release `v3.2.6` carries the Phase 3 mutation
safety implementation. Phase 2 is now the release-truth and
reproducible-CI gate described in the linked authoritative roadmap.

**Phase 3 local delivery:** branch
`feature/power-3-3-phase-3-mutation-safety` removes the daemon index worker and
global active-vault state, adds per-vault in-process plus OS file locking, and
routes CLI/MCP writes through the shared mutation boundary. The local Gate 3
evidence is `607 passed, 17 skipped`, `76.02%` coverage, strict resource-warning
gates, Mypy, Ruff, documentation, release-contract, and clean package smoke.
Remote CI, review, and merge remain unverified until publication.

**Runtime policy for 3.3.0:** Python `>=3.11`; required CI matrix is
3.11–3.14. Python 3.10 compatibility is not part of the 3.3.0 contract.

This document retains the earlier repository-side execution tracker for
reference. It is not the current phase authority; a GitHub epic with child
issues for Phases 1–10 must not override the linked roadmap.
An issue being closed is never proof that a release gate passed.

## Phase ownership and merge gates

| Phase | Owner | Target host | Required command/evidence | Merge gate |
| --- | --- | --- | --- | --- |
| 1 — crash-atomic generations | Weby Homelab | hermetic CI + target vault host | subprocess fault matrix, retained prior-generation readback | no crash path can expose partial or missing active data |
| 2 — Execution Kernel | Weby Homelab | hermetic CI | queue lifecycle, two-vault isolation, receipt tests | all writers use typed per-vault jobs |
| 3 — memory governance | Weby Homelab | hermetic CI | temporal/sensitivity/relation round-trip tests | no lossy relation or unauthorised historical result |
| 4 — Evaluation v2 | Weby Homelab | CI + adjudication workspace | versioned human qrels, slice reports, confidence intervals | synthetic and human claims remain separate |
| 5 — retrieval profiles | Weby Homelab | hermetic CI | profile contract and envelope-v2 integration tests | profile selection is explicit and reproducible |
| 6 — Method Profiles | Weby Homelab | hermetic CI | init, migration, manifest and recipe conformance tests | P.A.R.A. remains the compatible default |
| 7 — consolidation | Weby Homelab | hermetic CI + review host | candidate, approval, supersession and rollback receipts | no automatic durable promotion without review |
| 8 — performance and doctor | Weby Homelab | CI + target vault host | incremental reuse, complexity and doctor reports | optimisation preserves Phase 1 correctness invariants |
| 9 — security and observability | Weby Homelab | CI + target vault host | offline/model/sensitivity/telemetry checks | release evidence contains no secrets or private paths |
| 10 — RC and final | Weby Homelab | CI + release host | signed tag, SBOM, attestations and final evidence bundle | all prior gates match one release source |

## Migrated acceptance rows from Issue #187

| Row | Phase | Target host | Command/procedure | Required retained artifact | Gate |
| --- | --- | --- | --- | --- | --- |
| Source | 0, 10 | CI/release host | `git rev-parse HEAD HEAD^{tree}` and clean-status check | source manifest | exact commit/tree and clean source agree |
| Model supply chain | 0, 9 | CI/release host | `python scripts/verify_release_contract.py` and file checksums | model-lock checksum record | package version, lock and file inventory agree |
| Cold CLI latency | 4, 10 | target vault host | fresh-process `power search` samples | raw CSV + manifest | p50/p95/p99 per retrieval profile |
| Warm CLI latency | 4, 10 | target vault host | warmed persistent-process samples | raw CSV + manifest | distinct from cold measurement |
| Persistent MCP latency | 4, 10 | target vault host | `python scripts/benchmark_mcp_latency.py ...` | timing CSV + manifest | startup state and mode recorded |
| Memory | 1, 8, 10 | target vault host | cgroup matrix for search and sync | RSS/OOM matrix | each profile has memory limit and exit code |
| Quality | 4, 5, 10 | adjudication workspace | frozen human qrels and slice evaluation | per-query output + confidence intervals | UA/EN and temporal/graph slices reported |
| Reranker comparison | 4, 5 | evaluation host | same corpus/query set for semantic and reranked profiles | paired quality/latency report | no cross-run comparison |
| Determinism | 1, 4 | CI + target vault host | repeat frozen query set at least five times | result hashes/tolerance policy | equality or documented tolerance passes |
| Recovery | 1, 10 | CI + target vault host | Phase 1 crash/OOM/disk/lock fixtures | failure receipts + prior-generation readback | old active result remains readable |
| Egress and security | 9, 10 | CI/release host | blocked-network, traversal and symlink tests | security report | offline search makes no network call |

## Phase 0 evidence

- `release/models.lock.json` release equals `pyproject.toml` version.
- `release/evidence/baselines/v3.2.6.json` records release source, Python/OS,
  test and warning counts, skipped optional gates, model-lock checksum, and
  frozen benchmark hashes.
- `python scripts/verify_release_contract.py` validates that contract.
- `pytest benchmarks/power31/tests -q --no-cov --override-ini=addopts=` is a
  separate hermetic CI job; it never downloads models or reads a private vault.
- The historical warning baseline is recorded without filtering. Current CI
  additionally fails on `ResourceWarning` and
  `PytestUnraisableExceptionWarning`; the Phase 3 local suite passes both gates.

## Canonical remote issues

- [#196 — Phase 1](https://github.com/weby-homelab/power-framework/issues/196)
- [#197 — Phase 2](https://github.com/weby-homelab/power-framework/issues/197)
- [#198 — Phase 3](https://github.com/weby-homelab/power-framework/issues/198)
- [#199 — Phase 4](https://github.com/weby-homelab/power-framework/issues/199)
- [#200 — Phase 5](https://github.com/weby-homelab/power-framework/issues/200)
- [#201 — Phase 6](https://github.com/weby-homelab/power-framework/issues/201)
- [#202 — Phase 7](https://github.com/weby-homelab/power-framework/issues/202)
- [#203 — Phase 8](https://github.com/weby-homelab/power-framework/issues/203)
- [#204 — Phase 9](https://github.com/weby-homelab/power-framework/issues/204)
- [#205 — Phase 10](https://github.com/weby-homelab/power-framework/issues/205)

Each issue mirrors the owner, target host, command, artifact, and gate in this
repository tracker. Before Phase 1 merges, link the CI result for this branch
to epic #195 and retain it with the Phase 0 evidence.
