---
type: Test Report
title: "P.O.W.E.R. v3.2.1 — TEST-2: source and post-merge WS full-sync evidence"
description: "Verified PR #186 source validation and a completed clean dedicated WS full sync; extended benchmarks remain tracked in issue #187."
status: completed-full-sync-extended-validation-pending
platform: WS
source_commit: 8f03847f557f80c567920f07a0e35acd62feb00e
tracking_issue: 187
---

# P.O.W.E.R. v3.2.1 — TEST-2

> [!IMPORTANT]
> **Status: source validation complete; clean dedicated WS full-sync evidence complete.**
>
> Source code, automated tests and CI were validated for commit
> `8f03847f557f80c567920f07a0e35acd62feb00e`.
>
> The clean full-index WS validation completed successfully. Its sanitized raw
> artifacts are published in `docs/tests/artifacts/3.2.1-ws-evidence/`.
> Extended benchmark matrices remain tracked in
> [issue #187](https://github.com/weby-homelab/power-framework/issues/187).

## VERIFIED IN PR #186

| Item | Verified result |
| --- | --- |
| Source commit | `8f03847f557f80c567920f07a0e35acd62feb00e` |
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

Tested source commit: `8f03847f557f80c567920f07a0e35acd62feb00e`
Merged through PR #186: `b793af65afc1e4843c16c75cc8df706528b7233c`

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

### Deferred extended benchmarks

The following are outside this evidence PR and do not affect the successful
full-sync result:

- expanded cgroup matrix;
- 100-run cold latency matrix;
- full MCP round-trip benchmark;
- extended crash-recovery matrix;
- extended neural determinism matrix.

## PENDING IN ISSUE #187

The following are intentionally not release claims for this source commit:

- fresh quality, latency, MCP, cgroup, egress, determinism and crash-recovery
  evidence.

Tracking: [Post-merge POWER 3.2.1 extended validation — #187](https://github.com/weby-homelab/power-framework/issues/187).

## HISTORICAL RESULTS

Earlier WS measurements, including earlier latency, quality, RSS and database
counts, are historical exploratory results. They are **not final evidence for
source commit `8f03847f557f80c567920f07a0e35acd62feb00e`** and are not used as
release guarantees in this report.

TEST-1 remains the historical PRXMX-01 baseline in
`P.O.W.E.R.3.2.1-TEST.md`.
