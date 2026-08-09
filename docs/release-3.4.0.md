# POWER 3.4.0 release notes

POWER 3.4.0 is the first release in the 3.4 line. It consolidates the
fail-closed operational contract needed for a human- and agent-operated vault:
inspect first, plan before mutation, preserve provenance, and make incomplete
work visible.

## What changed

- `power doctor` provides read-only diagnostics for runtime identity, active
  search generation, index coverage, model cache state, and the provider bound
  by a real ONNX Runtime session. It emits a versioned JSON report and does not
  create a cache namespace merely by probing.
- `power import` builds a deterministic preflight plan for foreign Markdown
  notes. `--dry-run` reports collisions, excluded notes, and additive `x-`
  quarantine changes before any target write.
- `power cache list` and `power cache prune` expose cache namespaces with their
  source-vault provenance and keep read-only inspection side-effect free.
- Hierarchical catalogs are recursive, explicit-link based, and bounded to
  32 KiB UTF-8 pages with deterministic navigation between pages.
- MCP ingestion now has a governed path to search-index synchronization, so an
  agent can make a saved note findable without leaving the MCP surface.
- Dense-loss and explicit-device policies are fail-closed: unavailable or
  silently downgraded providers are reported as errors rather than presented
  as successful GPU execution.
- Batch healer failures are isolated per note, foreign frontmatter is
  quarantined, and Windows failure paths are normalized.
- Both bundled agent skill copies are checked against the executable CLI/MCP
  contract and release version by the documentation-drift gate.

## Validation and evidence boundary

The release workflow runs the repository's full machine-only test, lint, type,
documentation, package smoke, security, and tag-bound release-contract gates.
The release baseline records the exact source commit/tree, model-lock digest,
synthetic benchmark digests, and skipped optional gates.

This is a technical release. It does not certify human-quality retrieval,
production quality, a sealed holdout, or target-host Windows 11 performance.
Dense search remains an exact SQLite/CPU scan rather than an ANN index, and
retrieval quality claims require separately versioned corpus evidence.

## Upgrade

Install the immutable wheel in a clean virtual environment:

```bash
python -m pip install \
  https://github.com/weby-homelab/power-framework/releases/download/v3.4.0/power_framework-3.4.0-py3-none-any.whl
power --version
```

For an existing vault, run `power doctor <vault>` first, then use
`power import <source> --into <target> --dry-run` before applying a migration.
