#!/usr/bin/env python3
"""Render TEST-2 and WHY_POWER only from the generated benchmark summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _metric(summary: dict, section: str, mode: str, key: str) -> str:
    return f"{summary[section][mode][key]:.6f}"


def _latency(summary: dict, section: str, mode: str) -> str:
    row = summary[section][mode]
    return f"{row['p50_ms']:.3f}/{row['p95_ms']:.3f} ms (n={row['n']}, errors={row['errors']})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--test2", type=Path, required=True)
    parser.add_argument("--why", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    db = summary["db_actual"]
    source = summary["tested_source_commit"]
    test2 = f'''---
type: Test Report
title: "P.O.W.E.R. 3.2.1 — TEST-2 WS verification"
description: "Canonical reproducible TEST-2 evidence generated from raw WS artifacts."
platform: WS
timestamp: {summary["evidence_generated_at_utc"]}
---

# P.O.W.E.R. 3.2.1 — TEST-2 (WS)

Tested source commit: `{source}`

Evidence generation timestamp: `{summary["evidence_generated_at_utc"]}`

Platform: `{summary["platform"]}`

## Actual DB state

| fts notes | TF vectors | doc embeddings | chunk embeddings | documents with chunks |
| ---: | ---: | ---: | ---: | ---: |
| {db["fts_notes"]} | {db["tf_vectors"]} | {db["doc_embeddings"]} | {db["chunk_embeddings"]} | {db["documents_with_chunks"]} |

All values above are actual dedicated-DB counts, not projections.

## Tests

- pytest: {summary["pytest"]["tests"]} tests, {summary["pytest"]["failures"]} failures, {summary["pytest"]["errors"]} errors, {summary["pytest"]["skipped"]} skipped
- coverage: {summary["coverage_percent"]:.2f}%
- new failures vs `origin/main`: {len(summary["pytest"]["new_failures"])}

## Quality (nDCG@5)

| Set | Semantic | Reranked |
| --- | ---: | ---: |
| Development | {_metric(summary, "quality_development", "semantic", "ndcg_at_5")} | {_metric(summary, "quality_development", "reranked", "ndcg_at_5")} |
| Holdout | {_metric(summary, "quality_holdout", "semantic", "ndcg_at_5")} | {_metric(summary, "quality_holdout", "reranked", "ndcg_at_5")} |

## Latency

| Mode | Warm in-process p50/p95 | Warm MCP p50/p95 |
| --- | --- | --- |
| Semantic | {_latency(summary, "latency_warm_inprocess", "semantic")} | {_latency(summary, "latency_warm_mcp", "semantic")} |
| Reranked | {_latency(summary, "latency_warm_inprocess", "reranked")} | {_latency(summary, "latency_warm_mcp", "reranked")} |

Cold CLI measurements are retained separately in `cold-latency.csv`.

## Limitations

The quality results apply to the WS vault captured by this run. Reranked is
reported separately from semantic and remains opt-in. See every raw command
output, egress capture, DB check, cgroup run, determinism run, and recovery
log in `docs/tests/artifacts/3.2.1-test-2-final/`.
'''
    why = f'''# Why P.O.W.E.R. 3.2.1 — measured TEST-2 evidence

The following values come only from the WS TEST-2 summary for source commit
`{source}`. The dedicated DB contained {db["doc_embeddings"]} actual document
embeddings and {db["chunk_embeddings"]} actual chunk embeddings.

- Development nDCG@5: semantic {_metric(summary, "quality_development", "semantic", "ndcg_at_5")}; reranked {_metric(summary, "quality_development", "reranked", "ndcg_at_5")}.
- Holdout nDCG@5: semantic {_metric(summary, "quality_holdout", "semantic", "ndcg_at_5")}; reranked {_metric(summary, "quality_holdout", "reranked", "ndcg_at_5")}.
- Warm semantic latency: {_latency(summary, "latency_warm_inprocess", "semantic")}; MCP: {_latency(summary, "latency_warm_mcp", "semantic")}.
- Warm reranked latency: {_latency(summary, "latency_warm_inprocess", "reranked")}; MCP: {_latency(summary, "latency_warm_mcp", "reranked")}.

If semantic scores higher than reranked, semantic is the stronger measured mode
for this vault; reranked remains opt-in/experimental. Full synchronization and
memory constraints are documented in the raw cgroup and sync artifacts. Cold
CLI latency is not interchangeable with a warm persistent MCP server.
'''
    args.test2.write_text(test2, encoding="utf-8")
    args.why.write_text(why, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
