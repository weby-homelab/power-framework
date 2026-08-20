# P.O.W.E.R. 3.6.6 release notes

P.O.W.E.R. 3.6.6 is the machine-only retrieval/runtime evidence release
following the generation-bound source read model in 3.6.5. It keeps the
application API v2 contract stable and records the reproducible release gates
needed for the next RC-hardening cycle.

## What changed

- Bumped the package, model-lock, runtime fallback, skill, and documentation
  metadata to 3.6.6.
- Bound the Linux upgrade evidence and CI artifacts to the content-free
  `3.6.5 -> 3.6.6` transition.
- Preserved fail-closed generation, cache, provider, and publication contracts.
- Kept POWER-GUI as a separate consumer release. The existing GUI 0.7.4 image
  is not rebuilt by this core-only metadata/evidence release.

## Evidence boundary

Linux is the supported release platform for `v3.6.6`. macOS and Windows remain outside the supported release boundary. Synthetic fixtures and locked runtime
receipts are mechanical diagnostics only; this release makes no real-vault quality or human-quality claim.

Human-annotated M2 evaluation and sealed judgment data are excluded from the
release contract and are not opened, commissioned, or substituted with an LLM
judge, synthetic qrels, or a lexical proxy.

## Release gates

The tag workflow requires a clean signed `v3.6.6` tag, locked dependency and
documentation checks, the full test suite with warnings treated as errors, the
content-free `3.6.5 -> 3.6.6` upgrade matrix, wheel and source-archive smoke
tests outside the checkout, an SPDX SBOM, provenance attestation, and GitHub
release asset/body readback.
