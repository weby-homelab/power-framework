# P.O.W.E.R. 3.6.0 release notes

P.O.W.E.R. 3.6.0 is a Linux-first architecture and release-truth update over
the published `v3.5.0` baseline. It does not add a CLI command or MCP tool: the
public inventory remains 24 CLI commands and 20 MCP tools.

## What changed

- Atomic search-index synchronization now lives in the dedicated
  `power_framework.core.index_sync` module instead of overloading
  `core.searcher`. Compatibility exports remain available and regression tests
  protect the public import surface.
- The CodeQL cleanup removes duplicated and unused paths while preserving the
  generation, crash-recovery, maintenance, low-memory, healer, and search
  contracts.
- Installation, migration, MCP onboarding, and package metadata documentation
  were audited against the executable runtime rather than historical setup
  assumptions.
- The repository MCP launcher metadata now matches the packaged runtime.
- The release evidence pipeline is version-scoped to `3.6.0`, validates the
  `3.5.0 -> 3.6.0` upgrade boundary, and uses fresh `power36-*` receipts so
  source-bound 3.5.0 evidence cannot silently open the 3.6.0 gate.
- Synthetic Phase 8 outcome and continuity receipts use the v2 contract and
  carry the exact release, commit, tree, clean-state, and worktree hash. Final
  publication rejects receipts not produced from the clean tagged checkout.

## Platform boundary

Ubuntu/Linux is the only supported release platform for `v3.6.0`. Every CI,
documentation, CodeQL, package, upgrade, and publication job runs on
`ubuntu-latest`.

macOS and Windows are deferred with an **unscheduled** policy. This release
does not run macOS or Windows CI, does not publish upgrade receipts for those
platforms, and makes no compatibility, performance, GPU, dense-retrieval, or
quality claim for them. Their documentation is informational and is not a
supported-platform certification.

## Upgrade and rollback

The executable Ubuntu matrix covers `3.5.0 -> 3.6.0`, including interrupted
index publication at `before_move`, `after_move`, and `after_pointer`. It must
prove source preservation, restart recovery, stale-build cleanup, active-pointer
consistency, and no data loss before publication.

The package keeps the existing vault/source formats and public command/tool
inventory. If a deployment must roll back, reinstall the immutable `v3.5.0`
wheel and read back `power --version`, package metadata, vault coverage, and the
active search generation before resuming writes.

## Release gates

```bash
uv sync --locked --group dev --extra semantic --extra rerank
uv run ruff check src tests scripts benchmarks/power35
uv run ruff format --check src tests scripts benchmarks/power35
uv run mypy src/power_framework
uv run python scripts/check_doc_drift.py
uv run python scripts/complexity_dashboard.py --baseline-revision v3.4.5 --require-budget
uv run mkdocs build --strict
uv run pytest tests -v --cov=src/power_framework --cov-fail-under=70 \
  -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning
uv run python scripts/verify_upgrade_matrix.py \
  --from-version 3.5.0 --to-version 3.6.0
```

The tag workflow additionally requires a clean signed `v3.6.0` tag, wheel and
source-distribution smoke tests outside the checkout, an SPDX SBOM, provenance
attestation, fresh source-bound Phase 8 evidence, a complete Ubuntu upgrade
aggregate, and GitHub release body/asset readback.

## Evidence boundary

Synthetic technical receipts do not substitute for real-vault or sealed-human
evidence. The stable workflow fails closed unless the protected
`power36-stable-release` environment supplies fresh content-free evidence bound
to `v3.6.0`. Historical `v3.5.0` release assets remain immutable historical
evidence and are not relabelled as 3.6.0 results.
