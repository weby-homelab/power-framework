# Issue #187 — executable production-validation checklist

**Status:** Open evidence gate

**Scope:** this checklist turns Issue #187 into a reproducible acceptance
record. It does not convert historical 3.2.1 measurements into release
guarantees.

## Preconditions

- [ ] Check out the exact release-candidate commit with a clean tree.
- [ ] Record a redacted vault snapshot hash and opaque vault ID; do not record
  an absolute private vault path.
- [ ] Verify pinned model files and revisions from `release/models.lock.json`.
- [ ] Create a `benchmark-manifest.json` conforming to
  `release/evidence/benchmark-manifest.schema.json`.

```bash
python scripts/verify_benchmark_manifest.py benchmark-manifest.json
```

## Required acceptance matrix

| Gate | Required artifact | Acceptance condition | Command or procedure |
| --- | --- | --- | --- |
| Source | commit, tree hash, clean status | manifest matches the tested source | `git rev-parse HEAD`; `git status --porcelain` |
| Model supply chain | revision and SHA-256 inventory | every runtime file matches `models.lock.json` | `sha256sum` each listed model file |
| Cold CLI latency | raw per-mode samples | independent process samples; p50/p95/p99 reported separately from warm | run each `power search` in a fresh process |
| Warm CLI latency | raw per-mode samples | in-process samples after explicit warm-up; p50/p95/p99 reported | benchmark persistent process separately |
| Persistent MCP latency | client/server timing CSV | loopback MCP round trips include startup state and mode | `python scripts/benchmark_mcp_latency.py ...` |
| Memory | cgroup matrix and peak RSS | FTS, semantic, reranked, and full sync measured under each target cgroup | record `memory.max`, RSS, exit code, and OOM events |
| Quality | frozen qrels and per-query output | UA/EN slices and confidence intervals reported; holdout remains unchanged | `python scripts/check_search_quality.py --gt-mode semantic ...` |
| Reranker comparison | semantic vs reranked artifact | quality and latency comparison uses the same frozen queries and corpus | execute both modes from the same manifest |
| Determinism | repeated raw result hashes | repeat matrix has documented equality/tolerance policy | run the frozen query set at least five times |
| Recovery | crash/OOM/disk-full/lock artifacts | failed sync leaves the prior active result set unchanged | execute dedicated fixtures from the Phase 1 recovery matrix |
| Egress and security | traces and path tests | offline search has no network egress; traversal and symlink cases fail safely | execute security tests under blocked network |

## Claim-state rule

- [ ] Mark implementation and focused-test results as `source-verified`.
- [ ] Mark a result `measured` only when its manifest, raw artifacts, and
  environment all match.
- [ ] Mark opt-in or incomplete capabilities as `experimental`.
- [ ] Mark every historical or unmatched result as `unverified`; it cannot be
  used as a release guarantee.

## Closing condition

Issue #187 may close only after every acceptance-matrix row links to a valid
manifest and retained artifact checksums. A passing unit suite alone does not
close the evidence gate.
