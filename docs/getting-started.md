# Getting Started from a Clean Knowledge Base

This is the authoritative clean-install path for P.O.W.E.R. `v3.7.8`. It
creates a new vault only. For existing notes, use the
[migration guide](migration-guide.md) instead of running `power init` in place.

> **Release contract:** use `v3.7.8` only after its signed tag and immutable
> wheel appear on the [GitHub release page](https://github.com/weby-homelab/power-framework/releases/tag/v3.7.8).
> This guide names the tag-bound target; the URL alone does not prove that
> publication completed. Check the [platform support matrix](support-matrix.md)
> before applying the procedure to a non-Linux host.

The [Windows installation guide](windows-11-installation.md) is informational
only. Windows and macOS are deferred indefinitely and are not supported release
platforms for `v3.7.8`.

## Choose a supported deployment profile

### Profile A — headless / agent server

Complete the native installation below for a full POWER installation. It
requires one managed `power-framework[mcp]` runtime, the `power` CLI, the
`power-mcp` stdio server, one host-side POWER Skill identity, and one canonical
vault. Docker, Web UI, reverse proxy, and Web cache are not required.

### Profile B — full human + agent server

Complete Profile A first. Then run the matching `power-web` image from the
[Profile B deployment contract](architecture/unified-runtime.md). Profile B uses the same
canonical vault read-write for governed Web proposal/apply operations, a
rebuildable named Web cache, host loopback `127.0.0.1:8080`, and no MCP service
inside the container. Provision the container's non-root UID/GID with the
intended host-side vault permissions.

## 1. Prerequisites

- Python 3.13 or 3.14 (`python3 --version`)
- `venv` and `pip` for that interpreter
- Network access to GitHub Releases and the configured Python package index
- Git only when installing from a Git tag or source checkout

Use an isolated virtual environment. Avoid modifying an operating-system Python
or relying on `--break-system-packages` for a normal installation.

## 2. Install the versioned release

On Linux:

```bash
python3 -m venv "$HOME/.local/share/power/venv"
POWER_PYTHON="$HOME/.local/share/power/venv/bin/python"
POWER_CLI="$HOME/.local/share/power/venv/bin/power"

"$POWER_PYTHON" -m pip install --upgrade pip
"$POWER_PYTHON" -m pip install \
  "power-framework[mcp] @ https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl"
```

The base release wheel remains available as a lean FTS-only library profile. The
official Profile A command above installs the required `mcp` extra; add
`semantic` only when local dense search is explicitly selected.

Verify the executable, package metadata, and lean import:

```bash
"$POWER_CLI" --version
"$POWER_PYTHON" -c \
  'from importlib.metadata import version; print(version("power-framework"))'
"$POWER_PYTHON" -c \
  'import power_framework; print("lean FTS import: OK")'
```

Both version commands must report `3.7.8`; the final command must print
`lean FTS import: OK`.

For local MCP, install the official SDK extra from the same wheel:

```bash
"$POWER_PYTHON" -m pip install \
  "power-framework[mcp] @ https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl"
```

### Alternative: install from the pinned tag

This path requires Git:

```bash
"$POWER_PYTHON" -m pip install \
  'git+https://github.com/weby-homelab/power-framework.git@v3.7.8'
```

Do not use an unpinned `main` install when reproducibility matters.

## 3. Initialize an empty vault

Choose a new path. `power init` refuses a non-empty directory by design.

```bash
POWER_VAULT="$HOME/Documents/power-vault"
"$POWER_CLI" init "$POWER_VAULT"
```

The command creates the canonical vault structure:

```text
power-vault/
├── 00_Inbox/
├── 01_Projects/
├── 02_Areas/
├── 03_Resources/
├── 04_Archive/
├── 05_Templates/
│   └── default.md
├── 06_Daily_Logs/
├── PROTOCOLS/
├── index.md
└── log.md
```

Canonical and nested-folder `_index.md` catalog files are created by `power index`,
not by `power init`; large catalogs are emitted as bounded `_index-N.md` pages.

## 4. Add the first note

```bash
"$POWER_CLI" ingest "$POWER_VAULT" \
  --type Resource \
  --title "First note" \
  --description "Clean-install acceptance note" \
  --tags power acceptance
```

Supported note types are `Project`, `Area`, `Resource`, `Daily Log`, `Archive`,
and `System Guide`. `power ingest` routes them into the canonical POWER folders.

## 5. Run the clean-vault acceptance gate

```bash
"$POWER_CLI" index "$POWER_VAULT" --strict
"$POWER_CLI" lint "$POWER_VAULT"
"$POWER_CLI" markdown-check "$POWER_VAULT"
```

All three commands must exit `0`. An orphan warning for a first note with no
inbound links is informational; invalid OKF metadata and broken internal links
are not acceptable.

Build and verify lightweight search without downloading dense models:

```bash
"$POWER_CLI" sync "$POWER_VAULT" --fts-only
"$POWER_CLI" search "$POWER_VAULT" "acceptance" --mode fts
```

The result must contain `First note`.

## 6. Optional dense search

The first full synchronization downloads and validates pinned model assets and
can require substantial time, network traffic, disk space, and memory:

```bash
"$POWER_CLI" sync "$POWER_VAULT"
"$POWER_CLI" search "$POWER_VAULT" "clean installation" --mode semantic
```

Do not claim semantic or reranked readiness unless both full sync and a search
in the selected mode succeed on the target host. The explicit mode is important:
the default `auto` profile may report a labelled FTS fallback. FTS remains
available if the dense model gate fails.

## 7. Configure MCP for an AI agent

The MCP server requires one existing configured vault root. Point the client to
the same virtual-environment interpreter used above:

```json
{
  "mcpServers": {
    "power": {
      "command": "/home/YOU/.local/share/power/venv/bin/power-mcp",
      "args": [],
      "env": {
        "POWER_VAULT_DIR": "/home/YOU/Documents/power-vault"
      }
    }
  }
}
```

Preflight the exact interpreter and vault before restarting the client:

```bash
  POWER_VAULT_DIR="$POWER_VAULT" "$HOME/.local/share/power/venv/bin/power-mcp" preflight
```

Restart long-lived MCP clients after changing their configuration or Python
environment. See [MCP Server](mcp-server.md) for the 20-tool contract and
stdio transport security boundary.

The Web UI is not a second native product. It is shipped by the same wheel and
runs only in the Web-only container described in the
[Profile B deployment contract](architecture/unified-runtime.md).

## 8. Daily operating sequence

After changing notes:

```bash
"$POWER_CLI" index "$POWER_VAULT" --strict
"$POWER_CLI" lint "$POWER_VAULT"
"$POWER_CLI" markdown-check "$POWER_VAULT"
```

Run `power sync` only when the searchable source set changed and the FTS/dense
index must be refreshed. Read `index.md`, then the relevant canonical
`_index.md`; do not load every Markdown file merely to discover the vault.

## 9. Upgrade or uninstall

Upgrade to an explicitly selected release and re-run the acceptance gate. To
remove the Python application without deleting the vault:

```bash
"$POWER_PYTHON" -m pip uninstall power-framework
```

The vault is ordinary Markdown and is independent of the Python runtime. Back
it up before removing either location.

## Acceptance checklist

- Python is 3.13 or 3.14 and the selected interpreter is inside the dedicated venv.
- CLI and distribution metadata both report `3.7.8`.
- `power_framework` imports successfully and the official Profile A includes the MCP extra.
- MCP preflight validates the configured vault through the public `power-mcp` launcher.
- `init`, `ingest`, `index --strict`, `lint`, and `markdown-check` exit `0`.
- FTS sync exits `0` and FTS search returns the first note.
- MCP preflight uses the same interpreter and prints `MCP preflight: OK`.
- Dense/reranked readiness is recorded only after the optional target-host gate
  passes.
