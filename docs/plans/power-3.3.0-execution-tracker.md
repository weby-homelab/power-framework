# POWER 3.3.0 execution tracker

**Status:** repository mirror of [GitHub epic #195](https://github.com/weby-homelab/power-framework/issues/195).
**Owner:** Weby Homelab. **Baseline:** `v3.2.4` commit
`7411140515497bc9d8b74be3f26ef0bbbb15dc70`, tree
`38adc02c740155164b9a26316542c57a6a3b1022`.

**Phase 0 delivery:** [PR #206](https://github.com/weby-homelab/power-framework/pull/206).
Its CI, CodeQL, and documentation checks must be green before Phase 1 merges.

This is the authoritative repository-side receipt for the 3.3.0 execution
plan. A GitHub epic with child issues for Phases 1–10 must mirror this table.
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
- `release/evidence/baselines/v3.2.4.json` records release source, Python/OS,
  test and warning counts, skipped optional gates, model-lock checksum, and
  frozen benchmark hashes.
- `python scripts/verify_release_contract.py` validates that contract.
- `pytest benchmarks/power31/tests -q --no-cov --override-ini=addopts=` is a
  separate hermetic CI job; it never downloads models or reads a private vault.
- The 47-warning release baseline is recorded without filtering. Phase 1 owns
  removal of the current ResourceWarning sources before strict new-warning
  enforcement is enabled.

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
