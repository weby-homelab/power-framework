# Why P.O.W.E.R. 3.2.1

PR #186 verifies the source and tooling changes for commit
`8f03847f557f80c567920f07a0e35acd62feb00e`: the automated suite has 562
passed, 0 failed and 10 skipped tests at 75.06% coverage, with no new failures
against `origin/main`.

P.O.W.E.R. retains a local-first search architecture with explicit reranker
batching, defensive model-cache detection and regression/security coverage.
These are source-level claims; they do not imply a completed full neural index
or a performance guarantee.

Final clean-index WS performance evidence is tracked in
[issue #187](https://github.com/weby-homelab/power-framework/issues/187).
Numbers from earlier exploratory runs are not release guarantees. That
follow-up will distinguish actual materialized database state from projections,
and cold CLI from warm in-process and MCP measurements.
