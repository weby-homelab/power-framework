---
type: Test Report
title: "P.O.W.E.R. v3.2.1 — TEST-2: source validation status"
description: "Verified source and CI validation for PR #186; final WS full-index evidence is deferred to issue #187."
status: source-validation-complete-full-ws-evidence-pending
platform: WS
source_commit: 8f03847f557f80c567920f07a0e35acd62feb00e
tracking_issue: 187
---

# P.O.W.E.R. v3.2.1 — TEST-2

> [!IMPORTANT]
> **Status: source validation complete; final WS full-index evidence pending.**
>
> Source code, automated tests and CI were validated for commit
> `8f03847f557f80c567920f07a0e35acd62feb00e`.
>
> The clean full-index WS validation is still running. Final actual database
> counts, full-sync duration, peak RSS and dependent benchmark evidence will be
> published under [issue #187](https://github.com/weby-homelab/power-framework/issues/187)
> in a separate evidence PR.

## VERIFIED IN PR #186

| Item | Verified result |
| --- | --- |
| Source commit | `8f03847f557f80c567920f07a0e35acd62feb00e` |
| WS host guard | `ws`, expected IPv4 `192.168.2.24` |
| Ruff | PASS |
| MyPy | PASS — 32 source files |
| Pytest | 562 passed, 0 failed, 10 skipped |
| Coverage | 75.06% |
| Failure comparison with `origin/main` | 0 new failures; 10 fixed failures |
| GitHub CI | Python 3.10–3.14, CodeQL and security checks PASS |

The source work includes the reranker batch implementation, conditional
`token_type_ids` handling, cache-sentinel safeguards, environment-isolated
regression tests, runtime batch-size coverage, security exception-contract
coverage, and TEST-2 validation tooling. Raw WS source-validation artifacts are
in `docs/tests/artifacts/3.2.1-test-2-final/`.

## PENDING IN ISSUE #187

The following are intentionally not release claims for this source commit until
the current clean full-index WS run completes and a dedicated evidence PR is
opened:

- full-sync exit code, duration, peak RSS and actual database counts;
- SQLite integrity, foreign-key and dense-manifest evidence;
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
