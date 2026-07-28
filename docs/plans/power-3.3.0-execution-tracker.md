# POWER 3.3.0 execution tracker

**Status:** repository mirror; remote epic ID is required before Phase 1 may
merge. **Owner:** Weby Homelab. **Baseline:** `v3.2.4` commit
`7411140515497bc9d8b74be3f26ef0bbbb15dc70`, tree
`38adc02c740155164b9a26316542c57a6a3b1022`.

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

## Remote synchronization requirement

Before Phase 1 merges, create the GitHub epic **POWER 3.3.0 — execution
tracker and release gates**, create child issues for the ten rows in the phase
table, and replace this sentence with their canonical links. The remote issue
content must preserve the same owner, target host, command, artifact, and gate
for every row.
