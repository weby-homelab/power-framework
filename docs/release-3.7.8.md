# POWER 3.7.8 release boundary

POWER 3.7.8 is the corrected unified Linux release target: one repository, one
Python distribution, one version, one signed tag, and one tag-push-bound
publication workflow. It carries the snapshot-integrity and release-SBOM fixes
from issue #360 together with a reproducible locked dependency graph.

## Runtime contract

- Native Profile A installs the exact `power-framework[mcp]` wheel and exposes
  only `~/.local/bin/power` and `~/.local/bin/power-mcp`.
- `power-mcp` is local stdio and receives the authoritative vault through
  `POWER_VAULT_DIR`.
- Profile B adds exactly one Web-only `power-web` container from the matching
  immutable OCI digest. The image installs the locked `[web,semantic,rerank]`
  dependency graph and exposes port `8080` only.
- CLI, MCP, and Web UI delegate reads and mutations through
  `ApplicationService`; Markdown/Git/`.power` remain the source of truth.
- The Web container launches no MCP process, exposes no MCP transport, and does
  not create a second canonical vault.

## Changes in 3.7.8

- Snapshot promotion now compares one deterministic relative-path ordering and
  rejects a changed live-vault source without replacing the active generation.
- Dense chunk IDs include their ordinal and stale schema-2 manifests rebuild
  automatically, preserving repeated identical sections.
- Package SBOM generation receives the wheel through the Anchore file input.
- The checked-in `uv.lock` and release constraints agree on MCP 2.1.0,
  filelock 3.32.4, fsspec 2026.7.0, charset-normalizer 3.5.1, and the stable
  Pydantic 2.13.5 / pydantic-core 2.46.5 pair.

## Supported boundary

Linux with Python `>=3.13,<3.15` is the documented release boundary. macOS,
Windows, GPU performance, host-independent latency, retrieval quality, and
multi-tenant or compliance claims are not certified by this release note.

## Publication evidence

The tag-triggered release workflow must bind and publish:

1. one reproducible wheel and normalized source archive;
2. `SHA256SUMS` and `power-release-manifest.json` bound to the tag commit;
3. `power-framework-3.7.8.spdx.json` for the package artifact/runtime graph;
4. `power-web-3.7.8.spdx.json` for the exact public Web image digest;
5. signed-tag provenance and attestation identifiers for the wheel, sdist, and
   Web image digest;
6. `power-profile-acceptance.json`, `power-framework.release-baseline.json`,
   and `power-framework.release-receipt.json` with the Profile A/B and Web
   capability evidence boundary.

The release is not considered published until the GitHub Release assets,
attestations, and container-registry digest are read back from outside the
source checkout.
