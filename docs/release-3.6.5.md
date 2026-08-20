# P.O.W.E.R. 3.6.5 release notes

P.O.W.E.R. 3.6.5 adds a generation-bound source read model for the Application
API v2. Source listing, statistics, bounded reads, and graph traversal now consume
one verified immutable projection rather than reparsing the vault independently.

## What changed

- Added the staged `source_metadata`, `source_links`, `source_link_ambiguities`,
  and `source_projection_meta` projection tables.
- Bound projection coverage and `source_revision` to the active index generation.
- Added explicit completed/activated timestamps to generation readback metadata.
- Preserved fail-closed behavior for missing, corrupt, or incomplete projections.

## Evidence boundary

Linux is the supported release platform for `v3.6.5`. Dense, reranked, and
provider-backed workflows remain conditional on a verified model snapshot and an
actually bound provider. macOS and Windows remain outside the supported release
boundary. macOS and Windows remain outside the supported release boundary. This
release does not make a real-vault quality or human-quality claim.

## Release gates

The tag workflow requires a clean signed `v3.6.5` tag, locked dependency and
documentation checks, the full test suite with warnings treated as errors, the
content-free `3.6.4 -> 3.6.5` upgrade matrix, wheel and source-archive smoke tests
outside the checkout, an SPDX SBOM, provenance attestation, and GitHub release
asset/body readback.
