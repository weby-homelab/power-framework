# P.O.W.E.R. 3.6.3 release notes

P.O.W.E.R. 3.6.3 adds canonical Task v2 and typed decision workflows, strengthens
their durable storage contract, and makes reranked search preserve first-stage
consensus without exposing expanded queries to the reranker.

## What changed

- **Canonical Task v2 CLI**: `power task list`, `read`, `create`, `transition`,
  and `events` expose filtered pagination, event cursors, optimistic revisions,
  actor attribution, and idempotency keys. Completion records include verified
  postconditions or artifact digests.
- **Compatibility handoff path**: `power handoff` remains available and routes
  durable work-packet operations through Task v2. It is a compatibility adapter,
  not a second task authority.
- **Fail-closed task persistence**: task snapshots, events, and completion
  receipts use atomic persistence under a per-vault writer lock. Event sequence
  numbers are monotonic, and malformed journals fail closed instead of being
  silently skipped.
- **Typed decisions**: `DecisionService` binds proposals to a task revision,
  validates structured inputs and allowed actors, checks decision authority,
  hashes proposal content, and emits idempotent resolution receipts.
- **Application envelope v2**: governed application responses now carry the
  actual capability, source revision, and request identifier needed for
  deterministic readback.
- **Reranked search**: the reranker receives only the original user query.
  First-stage FTS, vector, and dense consensus gets a bounded prior during RRF
  merge, while lower-ranked candidates remain eligible in the tail.
- **Search-quality compatibility**: the quality gate exposes `udcg@5` as an
  alias for the existing normalized discounted-gain calculation and evaluates
  both `ndcg@5` and `udcg@5` thresholds.
- **Reproducible neural extras**: semantic and rerank profiles cap NumPy below
  `2.5` for the supported Numba benchmark path. The Linux x86_64 GPU profile
  installs the CUDA 13 runtime, cuBLAS, and cuDNN wheels needed by ONNX Runtime.
- **Executable documentation contract**: the public surface is 25 top-level CLI
  commands and 20 governed MCP tools.

## Evidence boundary

Linux remains the supported release platform for `v3.6.3`. The content-free
upgrade matrix exercises the `3.6.1 -> 3.6.3` state, interrupted-publication,
and maintenance-safety invariants. It does not execute a separately installed
physical `3.6.1` binary, so it is not a claim of full previous-runtime upgrade
certification.

The MCP surface keeps `handoff_work` as a compatibility entry point. A complete
canonical Task v2 MCP filter/event surface and fault-injected migration proof are
not claimed by this release.

macOS and Windows remain outside the supported release boundary and have no
scheduled certification target.

## Release gates

```bash
uv sync --locked --group dev --extra semantic --extra rerank --extra gpu
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/power_framework
uv run pytest
uv run mkdocs build --strict
```

The tag workflow additionally requires a clean signed `v3.6.3` tag, verifies
the version-bound release contract and upgrade aggregate, builds the wheel and
source archive, emits the SPDX SBOM and release receipt, and publishes this file
as the GitHub Release body.
