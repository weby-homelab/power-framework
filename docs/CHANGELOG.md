# Changelog

## 3.3.0

- Technical release with explicit M2 remediation scope and sealed holdout closure.
- No new human judgments were generated; the prior development receipt remains
  the measured source and the original threshold is preserved.

## 3.2.7

- Added explicit candidate-graph decisions, temporal retrieval semantics,
  fail-closed remote egress, and governed transactional memory operations.
- Added a versioned repository threat model for vault, MCP, mutation, and
  egress boundaries.
- Added `power memory` and five MCP memory tools.

## 3.2.6

- Added shared per-vault mutation safety for CLI and MCP writers, with
  reentrant in-process locks and cross-process file locking.
- Removed the daemon index worker and process-global active-vault state.
- Added coverage and regression tests for concurrent writers, cancellation,
  failure cleanup, and resource-safe read-only inspection.

## 3.2.5

- Added crash-atomic per-vault generation publication, failure-invariant tests
  and versioned raw fault receipts.
- Raised the supported Python floor to 3.11.

## 3.2.4

- Fixed typed YAML `related` mappings and preserved plain-string compatibility.
- Resolved GFM links relative to their source note and reported ambiguous
  duplicate-basename wiki links as blocking lint errors.
- Ignored links inside inline/fenced code examples during graph extraction.
- Indexed `PROTOCOLS/` and root-level daily logs in the hierarchical catalog.
- Added regression coverage for all of the above behavior.

## 3.2.3

- Refused publication of a staged search generation when a source note changes
  during `power sync`; the previous active index remains available.
- Added the additive OKF Memory Contract v0.2: optional typed lifecycle,
  provenance, write-policy, and sensitivity metadata with forward-compatible
  preservation of extension fields.
- Added provenance digests for notes produced by session synthesis and MCP
  ingest. See the [3.2.3 release notes](release-3.2.3.md).

## 3.2.2

- Isolated search databases by stable vault identity, so independent vaults do
  not overwrite one another's FTS, vector, or graph data.
- Staged, validated index generations now publish atomically and retain the
  previous active database if a sync fails.
- Added an evidence manifest schema and documentation-drift checks for release
  claims. See the [3.2.2 release notes](release-3.2.2.md).

## 3.2.1

The release remains a beta evidence record. See
[P.O.W.E.R. 3.2.1 test evidence](tests/P.O.W.E.R.3.2.1-TEST.md) and the
[POWER 3.2 release evidence](release-3.2.md) for scoped results and open gates.

## 3.1.0

See the [POWER 3.1 release evidence](release-3.1.md) and its
[trust-release baseline](adr/0001-power-3.1-trust-release-baseline.md).

## Evidence policy

Claims are classified and validated under
[ADR 0002](adr/0002-memory-os-principles.md). Historical measurements are not
release guarantees without a matching benchmark manifest and raw artifacts.
