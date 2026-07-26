---
type: Test Report
title: "P.O.W.E.R. v3.2.1 — TEST-2: source and post-merge WS full-sync evidence"
description: "Verified PR #186 source validation and a completed clean dedicated WS full sync; extended benchmarks remain tracked in issue #187."
status: completed-full-sync-extended-validation-pending
platform: WS
source_commit: 8f03847f557f80c567920f07a0e35acd62feb00e
tracking_issue: 187
source_validation_pr: 186
source_validation_merge: b793af65afc1e4843c16c75cc8df706528b7233c
post_merge_evidence_pr: 188
post_merge_evidence_merge: 599af7ff72b01baeb012240c5f0aa2e5f4d431bd
evidence_commit: 52393100bfd272b39d2d16e98c482d19ba2de3b3
canonical: true
---

# P.O.W.E.R. v3.2.1 — TEST-2

> [!IMPORTANT]
> **Status: source validation complete; clean dedicated WS full-sync evidence complete.**
>
> The clean full-index WS validation completed successfully. Its sanitized raw
> artifacts are published in `docs/tests/artifacts/3.2.1-ws-evidence/`.
> Extended benchmark matrices remain tracked in
> [issue #187](https://github.com/weby-homelab/power-framework/issues/187).

## Provenance

| Item | Verified value |
| --- | --- |
| Tested source commit | `8f03847f557f80c567920f07a0e35acd62feb00e` |
| Source-validation merge | PR #186, `b793af65afc1e4843c16c75cc8df706528b7233c` |
| Post-merge evidence merge | PR #188, `599af7ff72b01baeb012240c5f0aa2e5f4d431bd` |
| Evidence commit | `52393100bfd272b39d2d16e98c482d19ba2de3b3` |
| Historical baseline | [TEST-1](P.O.W.E.R.3.2.1-TEST.md), PRXMX-01 only |
| Deferred validation | [issue #187](https://github.com/weby-homelab/power-framework/issues/187) |

## VERIFIED IN PR #186

| Item | Verified result |
| --- | --- |
| WS host guard | `ws`, expected IPv4 `192.168.2.24` |
| Ruff | PASS |
| MyPy | PASS — 32 source files |
| Pytest | 562 passed, 0 failed, 10 skipped |
| Coverage | 75.06% |
| Failure comparison with `origin/main` | 0 new failures; 1 executed fix; 9 baseline failures skipped/unverified |
| GitHub CI | Python 3.10–3.14, CodeQL and security checks PASS |

The source work includes the reranker batch implementation, conditional
`token_type_ids` handling, cache-sentinel safeguards, environment-isolated
regression tests, runtime batch-size coverage, security exception-contract
coverage, and TEST-2 validation tooling. Raw WS source-validation artifacts are
in `docs/tests/artifacts/3.2.1-test-2-final/`.

## Post-merge WS full-sync evidence

Tracking issue: [#187](https://github.com/weby-homelab/power-framework/issues/187)

| Metric | Result |
| --- | --- |
| Platform | `ws` (`192.168.2.24`) |
| Sync exit code | 0 |
| Elapsed wall time | 2:25:01 (8,701 s) |
| Peak RSS | 2,981,832 KiB (2,911.95 MiB) |
| FTS notes | 561 |
| TF vectors | 561 |
| Document embeddings, actual | 561 |
| Chunk embeddings, actual | 3,884 |
| Documents with chunks | 561 |
| SQLite integrity | `ok` |
| Foreign-key check | N/A — schema declares no `FOREIGN KEY` constraints; check returned no rows |
| Dense manifest | schema v2, BGE-M3 ONNX, 1,024 dimensions, 3,884 chunks |
| Duplicate chunk IDs | 0 |
| Exact duplicate content within a document | 0 groups |

Global repeated content was observed in two groups and is reported separately;
it is not automatically database corruption. All values above are taken from
the sanitized artifacts in `docs/tests/artifacts/3.2.1-ws-evidence/`, not from
projected counts.

## Sanitized evidence inventory and integrity

The post-merge evidence package contains 25 committed files.
`files.sha256` contains 24 checksums and deliberately excludes itself.

Checksum verification must produce:

- 24 `OK`;
- 0 `FAILED`;
- 0 missing entries.

The raw full-sync log is intentionally not committed because it contains private
vault paths. Published evidence must remain sanitized.

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

## Deferred validation tracked in issue #187

The following work is not claimed by this report:

- expanded cgroup memory matrix for semantic, reranked, and sync modes;
- statistically sufficient cold CLI latency sampling;
- persistent MCP round-trip matrix;
- extended crash-recovery scenarios;
- neural determinism matrix;
- reranker batch matrix and quality comparison;
- sync thread-scaling benchmark.

## HISTORICAL RESULTS

Earlier WS measurements, including earlier latency, quality, RSS and database
counts, are historical exploratory results. They are **not final evidence for
the tested source commit** and are not used as release guarantees in this
report.

TEST-1 remains the historical PRXMX-01 baseline in
[P.O.W.E.R.3.2.1-TEST.md](P.O.W.E.R.3.2.1-TEST.md).

## Reproducibility checks

Run these read-only checks against the intended `main` commit:

```bash
set -euo pipefail

git fetch origin --prune --tags
main="$(git rev-parse origin/main)"

git show "$main:docs/tests/P.O.W.E.R.3.2.1-TEST-2.md"
git show "$main:docs/tests/artifacts/3.2.1-ws-evidence/benchmark-summary.json" \
  | python3 -m json.tool

audit_dir="$(mktemp -d /tmp/power-evidence.XXXXXX)"
git ls-tree -r --name-only "$main" docs/tests/artifacts/3.2.1-ws-evidence \
  | sort > "$audit_dir/tree-files.txt"
while IFS= read -r file; do
  mkdir -p "$audit_dir/$(dirname "$file")"
  git show "$main:$file" > "$audit_dir/$file"
done < "$audit_dir/tree-files.txt"

manifest="docs/tests/artifacts/3.2.1-ws-evidence/files.sha256"
awk '{path=$2; sub(/^\\*/, "", path); print path}' "$audit_dir/$manifest" \
  | sort > "$audit_dir/manifest-files.txt"
grep -v "^$manifest$" "$audit_dir/tree-files.txt" \
  > "$audit_dir/tree-files-without-manifest.txt"
diff -u "$audit_dir/manifest-files.txt" "$audit_dir/tree-files-without-manifest.txt"
(cd "$audit_dir" && sha256sum -c "$manifest")
```

## Claim boundary

The measured 2.84 GiB peak RSS applies to this completed full-sync run.

It is not a claim that the full neural stack fits below 2 GiB.

No quality, latency, zero-data-loss, determinism, crash-recovery, MCP, cgroup,
or thread-scaling guarantee may be made without corresponding completed,
sanitized artifacts tracked through issue #187.
