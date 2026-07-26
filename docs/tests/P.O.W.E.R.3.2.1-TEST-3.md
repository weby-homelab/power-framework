---
type: Test Report
title: "P.O.W.E.R. v3.2.1 — TEST-3: consolidated validation record"
description: "Canonical index of source validation, post-merge WS full-sync evidence, artifact integrity, historical baselines, and deferred validation."
status: consolidated-record
source_commit: 8f03847f557f80c567920f07a0e35acd62feb00e
merged_via_pr: 186
post_merge_evidence_pr: 188
tracking_issue: 187
timestamp: 2026-07-26T17:16:41Z
tags: [power-framework, testing, evidence, ws, test-3, consolidated]
---

# P.O.W.E.R. v3.2.1 — TEST-3: consolidated validation record

> [!IMPORTANT]
> This is the canonical navigation and fact record for P.O.W.E.R. 3.2.1
> validation. It consolidates only verified facts from the committed artifacts;
> it does not replace their raw sanitized files and does not turn deferred work
> into a release claim.

## Scope and provenance

| Item | Verified value |
| --- | --- |
| Tested source commit | `8f03847f557f80c567920f07a0e35acd62feb00e` |
| Source-validation merge | PR #186, `b793af65afc1e4843c16c75cc8df706528b7233c` |
| Post-merge evidence merge | PR #188, `599af7ff72b01baeb012240c5f0aa2e5f4d431bd` |
| Evidence-review commit | `52393100bfd272b39d2d16e98c482d19ba2de3b3` |
| Canonical source report | [TEST-2](P.O.W.E.R.3.2.1-TEST-2.md) |
| Historical baseline | [TEST-1](P.O.W.E.R.3.2.1-TEST.md), PRXMX-01 only |
| Deferred validation | [issue #187](https://github.com/weby-homelab/power-framework/issues/187) |

The source commit and all four commits above are ancestors of `main` at the
time this record was assembled. TEST-1 is historical context only: it did not
materialize a complete neural index and must not be used as current WS or
release evidence.

## Verified source validation (PR #186)

The following validates source code and tooling for the tested source commit;
it is separate from the later clean WS full sync.

| Check | Result |
| --- | --- |
| Pytest | 562 passed, 0 failed, 10 skipped |
| Coverage | 75.06% |
| Ruff | PASS |
| MyPy | PASS — 32 source files |
| CI | Python 3.10–3.14, CodeQL, and security checks PASS |
| Failure comparison | 0 new failures; 1 executed fix; 9 baseline failures skipped or unverified |

Source-validation artifacts are retained in
`docs/tests/artifacts/3.2.1-test-2-final/`. This compact package contains the
JUnit report, coverage, source SHA, Git-state records, benchmark summary, and
pytest baseline comparison. It is evidence for the source-validation result,
not a substitute for the post-merge database evidence below.

## Final post-merge WS full-sync evidence

The clean dedicated WS full sync completed after PR #186. Its checked database
is a dedicated test database, not the production vault database. The canonical
machine-readable source is
`docs/tests/artifacts/3.2.1-ws-evidence/benchmark-summary.json`; the
human-readable source is TEST-2.

| Metric | Final actual value |
| --- | --- |
| Sync exit code | 0 |
| Elapsed wall time | 8,701 seconds (2:25:01) |
| Peak RSS | 2,981,832 KiB (2,911.95 MiB; about 2.84 GiB) |
| FTS notes | 561 |
| TF vectors | 561 |
| Document embeddings, actual | 561 |
| Chunk embeddings, actual | 3,884 |
| Documents with chunks | 561 |
| SQLite integrity | `ok` |
| Foreign-key result | No rows; the schema declares no foreign-key constraints |
| Dense index | schema v2; BGE-M3 ONNX; 1,024 dimensions; 3,884 chunks |
| Duplicate chunk IDs | 0 |
| Exact duplicate content within one document | 0 groups |
| Global repeated-content groups | 2; reported separately and not treated as database corruption |

These are actual materialized counts. Earlier projections, partial sync counts,
and exploratory RSS/latency observations are historical only and are not
current release guarantees.

## Sanitized evidence inventory and integrity

The post-merge evidence package contains 25 committed files. `files.sha256`
contains 24 checksums and deliberately excludes itself. Verification from the
repository-root extraction context must produce 24 `OK`, 0 `FAILED`, and 0
missing entries.

<details>
<summary>Committed post-merge WS evidence files</summary>

- `README.md`
- `benchmark-summary.json`
- `coverage.json`
- `db-schema-chunk-embeddings.txt`
- `db-schema-full.txt`
- `db-state-final.txt`
- `dense-index-manifest.txt`
- `duplicate-chunk-ids.txt`
- `duplicate-content-summary.txt`
- `files.sha256`
- `git-commit.txt`
- `git-status-after-sync.txt`
- `git-status-start.txt`
- `known-baseline-failures.md`
- `mypy.log`
- `pytest-baseline-comparison.json`
- `pytest-baseline-comparison.md`
- `pytest-pr-ws.xml`
- `pytest.log`
- `ruff.log`
- `run-manifest.json`
- `search-db-path.txt`
- `sync-end.txt`
- `sync.exit-code`
- `tested-source-commit.txt`

</details>

The raw full-sync log is intentionally not committed because it contains
private vault paths. Do not add it to Git. Future evidence must remain
sanitized and must have a manifest and checksum verification.

## What remains deferred

Issue #187 remains open for evidence that this record deliberately does not
claim:

- expanded cgroup memory matrix for semantic, reranked, and sync modes;
- statistically sufficient cold CLI latency sampling;
- persistent MCP round-trip matrix;
- extended crash-recovery scenarios;
- neural determinism matrix;
- reranker batch matrix and quality comparison;
- sync thread-scaling benchmark.

Each completed item should add a separate sanitized, immutable run directory
with its own source SHA, timestamp, manifest, checksums, metric units, and
explicit relationship to this record. Do not overwrite this final full-sync
snapshot with a later run.

## Test retention policy

Keep the following in `main`:

1. Hermetic unit, integration, regression, security, low-RAM, crash-recovery,
   reranker-batch, and fixture-based search tests under `tests/`.
2. The versioned `benchmarks/power31/` harness, datasets, schemas,
   configurations, and evaluation verifier.
3. TEST-1 as an explicitly historical baseline; TEST-2 as the canonical
   detailed report; this TEST-3 as the consolidated entry point.
4. Sanitized artifact manifests, summaries, checksums, database state, and
   deterministic test reports needed to verify a published claim.

Do not treat optional real-vault benchmark tests as ordinary CI evidence:
they are marked `bench` and require an explicitly provisioned environment.
Their results belong in a versioned evidence snapshot, not in an unqualified
README or marketing claim.

## Reproducibility checks

Run these read-only checks against the intended `main` commit:

```bash
git fetch origin --prune --tags
main="$(git rev-parse origin/main)"

git show "$main:docs/tests/P.O.W.E.R.3.2.1-TEST-3.md"
git show "$main:docs/tests/artifacts/3.2.1-ws-evidence/benchmark-summary.json" \
  | python3 -m json.tool

audit_dir="$(mktemp -d /tmp/power-evidence.XXXXXX)"
git ls-tree -r --name-only "$main" docs/tests/artifacts/3.2.1-ws-evidence \
  | while IFS= read -r file; do
      mkdir -p "$audit_dir/$(dirname "$file")"
      git show "$main:$file" > "$audit_dir/$file"
    done
(cd "$audit_dir" && sha256sum -c docs/tests/artifacts/3.2.1-ws-evidence/files.sha256)
```

## Claim boundary

The measured 2.84 GiB peak RSS is evidence for this completed full-sync run;
it is not a claim that the full neural stack fits below 2 GiB. No quality,
latency, zero-data-loss, determinism, or crash-recovery guarantee may be made
without the corresponding completed artifacts from issue #187.
