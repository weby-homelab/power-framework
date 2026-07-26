# Why P.O.W.E.R. 3.2.1 — TEST-2 evidence

This document is the human-readable interpretation of the canonical WS TEST-2
run. Its measurements are generated only from
`docs/tests/artifacts/3.2.1-test-2-final/benchmark-summary.json` after a clean
source revision has been benchmarked on WS.

TEST-1 results from PRXMX-01 are historical only and are not used here. No
performance, quality, memory, reliability, or egress claim is made until the
matching raw TEST-2 artifact is present.

The final evidence will explicitly distinguish cold CLI, warm in-process, and
warm MCP latency; actual DB materialization from projections; and semantic
results from the opt-in reranked mode. It will also state any limitations of the
specific WS vault and hardware used for the run.
