# POWER Web UI container

This is the only Docker runtime shipped by the unified `power-framework`
repository. It installs the `power-framework[web]` extra from the same release
wheel as the native CLI and starts `power-web` on host loopback port `8080`.

The MCP server is not a container service. Native integrations invoke the
single `power-mcp` console script over stdio, while this container calls the
same application service through the Web UI adapter.

```bash
POWER_BRAIN_PATH=/mnt/brain \
POWER_WEB_UID="$(id -u)" POWER_WEB_GID="$(id -g)" \
docker compose -f deploy/web/compose.yaml up -d --build
```

This is Profile B: complete Profile A first, then mount the same canonical vault
read-write so governed proposal/apply routes can persist through
`ApplicationService`. The non-root container UID/GID must have the intended
host-side vault permissions; use the variables above or provision a matching
service account. Rebuildable search/model cache lives in the named
`power-web-cache` volume and is not canonical truth. Authentication remains
enabled by default; provide `POWER_WEB_ADMIN_PASSWORD` or
`POWER_WEB_ADMIN_PASSWORD_HASH` through a secret manager rather than committing
credentials.

The Compose file publishes only `127.0.0.1:8080`; use an authenticated reverse
proxy, Tailscale, or an equivalent trusted access layer for remote access. The
container runs no MCP process and exposes no MCP port.
