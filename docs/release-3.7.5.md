# POWER 3.7.5 release boundary

POWER 3.7.5 is the unified monorepo release: one Git repository, one Python
distribution, one version, and one signed tag.

## Runtime contract

- Native Linux installs use the exact `power-framework` wheel and expose only
  `~/.local/bin/power` and `~/.local/bin/power-mcp`.
- `power-mcp` is local stdio and receives the authoritative vault through
  `POWER_VAULT_DIR`.
- The Web UI is shipped by the same wheel under `power_framework.web` and runs
  only as the Web-only `power-web` container on port `8080`.
- CLI, MCP, and Web UI delegate reads and mutations through
  `ApplicationService`; Markdown/Git/`.power` remain the source of truth.
- No standalone Web UI wheel, `power-gui` launcher, or Docker MCP service is a
  supported release surface.

## Supported deployment profiles

- **Profile A — headless / agent server:** one native `power-framework` runtime,
  `power`, local stdio `power-mcp`, the host-side POWER Skill, and one canonical
  vault. Docker and Web UI are not required.
- **Profile B — full human + agent server:** Profile A plus one matching
  `power-web` container. Compose publishes host loopback `127.0.0.1:8080`,
  mounts the same canonical vault read-write for governed Web proposal/apply,
  and uses a separate rebuildable named cache. The container is non-root and
  contains no MCP process or MCP TCP port.
- Profile B operators must provision the configured non-root UID/GID for the
  vault. Remote Web access belongs behind an authenticated reverse proxy,
  Tailscale, or an equivalent trusted access layer.

## Required publication evidence

The release workflow publishes and binds:

1. the exact wheel and source archive;
2. `power-release-manifest.json` with commit, wheel hash, Skill hash, MCP
   contract hash, and Web image digest;
3. the SPDX SBOM, `SHA256SUMS`, signed-tag readback, and release receipt;
4. Web container health, non-root, read-only filesystem, dropped-capability,
    loopback publication, read-write disposable-vault mutation, and `/healthz`
    verification;
5. native install, stdio preflight, rollback, and stale-launcher cleanup gates.

The release is not considered published until all identities are read back from
the GitHub release and container registry.
