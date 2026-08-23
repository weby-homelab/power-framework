# POWER 3.7.6 release boundary

POWER 3.7.6 is the corrected unified Linux release target: one repository, one
Python distribution, one version, one signed tag, and one tag-push-bound
publication workflow. The previous immutable publication remains historical
and superseded; immutable tags and artifacts are never rewritten.

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

## Supported boundary

Linux with Python `>=3.13,<3.15` is the documented release boundary. macOS,
Windows, GPU performance, host-independent latency, retrieval quality, and
multi-tenant or compliance claims are not certified by this release note.

## Publication evidence

The tag-triggered release workflow must bind and publish:

1. one reproducible wheel and normalized source archive;
2. `SHA256SUMS` and `power-release-manifest.json` bound to the tag commit;
3. `power-framework-3.7.6.spdx.json` for the package artifact/runtime graph;
4. `power-web-3.7.6.spdx.json` for the exact public Web image digest;
5. signed-tag provenance and attestation identifiers for the wheel, sdist, and
   Web image digest;
6. `power-profile-acceptance.json`, `power-framework.release-baseline.json`,
   and `power-framework.release-receipt.json` with the Profile A/B and Web
   capability evidence boundary.

The release is not considered published until the GitHub Release assets,
attestations, and container-registry digest are read back from outside the
source checkout.
