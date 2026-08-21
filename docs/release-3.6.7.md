# P.O.W.E.R. 3.6.7 release notes

P.O.W.E.R. 3.6.7 is the suite-runtime hardening release after the 3.6.6
machine-only evidence baseline. The package and CI contract now support only
the two latest stable Python feature releases: Python 3.13 and Python 3.14.

## What changed

- Updated the core package contract, GUI package contract, Docker runtime, and
  active installation documentation to `>=3.13,<3.15`.
- Reduced the supported CI matrix to Python 3.13 and Python 3.14; fixed-purpose
  documentation, security, release, and GUI E2E jobs use Python 3.13.
- Kept the official MCP SDK v2 boundary, ApplicationService contract, source
  projection, fail-closed task persistence, and consensus-aware reranked search
  from the 3.6.6 implementation baseline.
- Retained the Linux release boundary and explicit provider/model evidence gates.

## Evidence boundary

This release makes no real-vault quality or human-quality claim. Synthetic
fixtures remain content-free technical evidence. macOS and Windows remain outside the supported release boundary, and platform-specific performance,
GPU benefit, ANN recall, and reranker quality are not inferred from Linux CI.

## Upgrade and release gates

The content-free upgrade matrix covers `3.6.6 -> 3.6.7`. A clean signed tag,
locked dependencies, the two-version CI matrix, full test suite, wheel/sdist
smoke tests, SPDX SBOM, provenance, and GitHub release readback are required
before publication is considered complete.
