# P.O.W.E.R. Unified Architecture & Runtime Model

## 1. Executive Architecture Summary

P.O.W.E.R. is a single-repository, single-version, local-first Second Brain framework.
Starting with the 3.7.5 release, the Web UI is physically integrated into the
`power-framework` repository and Python distribution as `power_framework.web`.

```text
                           P.O.W.E.R.
                   one repo / one version / one tag
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
     Native Linux Runtime                Web UI Container
     canonical/default                   optional server UI
             |                                 |
      +------+-------+                    FastAPI/Web UI
      |              |                          |
      v              v                          v
     CLI         stdio MCP               ApplicationService
      |              |                          |
      +-------+------+--------------------------+
              |
        ApplicationService
              |
        canonical services
              |
      Markdown/Git/.power truth
```

## 2. Canonical Invariants

1. **Canonical Repository:** `weby-homelab/power-framework`
2. **Canonical Package:** `power-framework`
3. **Canonical Truth:** Human-owned Markdown vault, Git history, and `.power` durable state.
4. **Business Boundary:** `power_framework.core.application.ApplicationService` is the sole entry point for mutations and reads across CLI, MCP, and Web.
5. **Canonical Native Linux Runtime:**
   - Managed venv at `~/.local/share/power/venv`
   - Canonical binaries: `~/.local/bin/power` and `~/.local/bin/power-mcp`
   - Canonical MCP transport: `stdio`
   - Canonical Skills: shipped host-side in the `power-framework` wheel/distribution.
6. **Web UI Presentation Adapter:**
    - Source resides in `src/power_framework/web/`
    - Production server profile runs as an OCI container (`ghcr.io/weby-homelab/power-framework-web:TARGET_VERSION`)
    - The Web container runs ONLY the FastAPI Web UI service; Compose publishes
      host loopback `127.0.0.1:8080`
    - The Web container interacts directly with `ApplicationService` in-process
    - The container does NOT expose MCP, does NOT launch `power-mcp`, and does NOT require a host daemon.
7. **Docker Role:**
    - Web UI only
    - Non-root user, read-only root filesystem, dropped Linux capabilities
    - Profile B mounts the canonical `/brain` read-write because governed Web
      proposal/apply routes persist through `ApplicationService`
    - Rebuildable Web/search/model cache is mounted separately from canonical
      `/brain`.

## 3. Official deployment profiles

### Profile A — headless / agent server

Profile A is a complete supported POWER installation without Docker or Web UI:

```text
one native power-framework runtime
power CLI
power-mcp over stdio
one host-side POWER Skill identity
one canonical vault
Web UI containers: 0
```

Install the base wheel for FTS-only operation, add the explicit `mcp` extra for
stdio MCP, and use the same managed venv for `power` and `power-mcp`. Docker,
reverse proxy, Web cache, and Web dependencies are not prerequisites.

### Profile B — full human + agent server

Start from a valid Profile A installation, then run exactly one
`power-web` container from the matching release image:

```text
Profile A
+ one power-web container
+ same canonical vault mounted read-write
+ rebuildable named Web/search/model cache
Web MCP services: 0
```

The non-root container UID/GID must have the intended host-side vault
permissions. The host native runtime and Web container use the same
`ApplicationService` semantics, locking, preimage checks, atomic writes, receipts,
and canonical Markdown/Git/`.power` truth. Removing the Web cache must not remove
canonical state.
