# ADR 0002: P.O.W.E.R. Memory OS Principles

**Status:** Accepted

**Date:** 2026-07-27

## Context

POWER indexes Markdown vaults through SQLite FTS, TF vectors, dense embeddings,
and graph data. These representations improve recall, but they are derived
from files and can be rebuilt. Treating an index as authoritative would permit
a partial or stale materialization to silently change what an agent recalls.

The 3.2.1 evidence record contains useful historical measurements, but it does
not establish universal release guarantees. In particular, a measurement is
only comparable when it records its source, vault snapshot, models, execution
environment, commands, and raw artifacts.

## Decision

1. Markdown plus OKF frontmatter is the authoritative knowledge source.
   SQLite, embeddings, graph tables, and generated indexes are materialized
   views. A view is disposable and must never become the only copy of a fact.
2. Retrieval contracts are explicit. The executable
   `SEARCH_MODE_REGISTRY` in `power_framework.core.searcher` is canonical for
   the supported modes. `semantic` is the current default; `reranked` is an
   explicit opt-in until comparative quality evidence supports another default.
3. Every public capability or performance claim has exactly one state:
   - `source-verified`: implementation and focused tests confirm the code path;
   - `measured`: a complete, valid benchmark manifest and retained artifacts
     support the claim for the recorded environment only;
   - `experimental`: an opt-in or incomplete capability with known limits;
   - `unverified`: a hypothesis, roadmap item, or historical observation that
     must not be presented as a release guarantee.
4. A release guarantee requires `measured` evidence. It must not be inferred
   from `source-verified` code, a synthetic benchmark, or a measurement made on
   another host, cgroup, model revision, or vault snapshot.
5. A benchmark manifest is valid only when it conforms to
   `release/evidence/benchmark-manifest.schema.json` and passes
   `scripts/verify_benchmark_manifest.py`. The manifest records source and
   vault identities, model files, hardware and cgroup constraints, exact
   commands, cold/warm classification, artifact checksums, and claim states.
6. Phase 1 uses a stable per-vault identity and an atomic staged DB publication
   path. Failed generations are recorded as `failed` and do not replace the
   active DB. The remaining crash/OOM/disk-full matrix is still required before
   making a release guarantee about every target environment.

## Consequences

- Documentation must describe the current retrieval registry and models from
  code, rather than preserve superseded defaults. The CI doc-drift gate checks
  the public architecture and API contract against the registry.
- Historical records remain useful diagnostic evidence but are labelled
  `unverified` unless represented by a valid manifest and matching artifacts.
- Future index work must ensure a failed build does not modify the active
  generation. This is intentionally a Phase 1 implementation requirement, not
  a property claimed by this ADR.

## Verification

```bash
python scripts/check_doc_drift.py
python scripts/verify_benchmark_manifest.py --schema-only
pytest tests/test_doc_drift.py tests/test_benchmark_manifest.py -v
```
