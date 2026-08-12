# Getting Started from a Clean Knowledge Base

This is the authoritative clean-install path for P.O.W.E.R. `v3.5.0`. It
creates a new vault only. For existing notes, use the
[migration guide](migration-guide.md) instead of running `power init` in place.

> **Candidate boundary:** `v3.5.0` is not a published GitHub Release or tag in
> the current worktree. The immutable wheel and pinned-tag commands below are
> the post-publication contract and must not be run until the signed release
> and remote readback gates pass. For the current candidate, use the checkout's
> locked development environment from the repository's `CONTRIBUTING.md`.

Windows 11 25H2 users should follow the complete
[Windows installation guide](windows-11-installation.md), which uses exact
PowerShell paths and includes MCP acceptance checks.

## 1. Prerequisites

- Python 3.11 or newer (`python3 --version`)
- `venv` and `pip` for that interpreter
- Network access to GitHub Releases and the configured Python package index
- Git only when installing from a Git tag or source checkout

Use an isolated virtual environment. Avoid modifying an operating-system Python
or relying on `--break-system-packages` for a normal installation.

## 2. Install the versioned release (after publication)

On Linux or macOS:

```bash
python3 -m venv "$HOME/.local/share/power-framework/venv"
POWER_PYTHON="$HOME/.local/share/power-framework/venv/bin/python"
POWER_CLI="$HOME/.local/share/power-framework/venv/bin/power"

"$POWER_PYTHON" -m pip install --upgrade pip
"$POWER_PYTHON" -m pip install \
  https://github.com/weby-homelab/power-framework/releases/download/v3.5.0/power_framework-3.5.0-py3-none-any.whl
```

The base release wheel is FTS-only: it does not install ONNX Runtime, model
tokenizers, numerical packages, or the optional MCP transport. Add the explicit
`remote` extra before configuring MCP, and add `semantic` only for local dense
experiments.

Verify the executable, package metadata, and lean import:

```bash
"$POWER_CLI" --version
"$POWER_PYTHON" -c \
  'from importlib.metadata import version; print(version("power-framework"))'
"$POWER_PYTHON" -c \
  'import power_framework; print("lean FTS import: OK")'
```

Both version commands must report `3.5.0`; the final command must print
`lean FTS import: OK`.

For local MCP, install the optional remote transport from the same wheel:

```bash
"$POWER_PYTHON" -m pip install \
  "power-framework[remote] @ https://github.com/weby-homelab/power-framework/releases/download/v3.5.0/power_framework-3.5.0-py3-none-any.whl"
```

### Alternative: install from the pinned tag

This path requires Git:

```bash
"$POWER_PYTHON" -m pip install \
  'git+https://github.com/weby-homelab/power-framework.git@v3.5.0'
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
"$POWER_CLI" search "$POWER_VAULT" "clean installation"
```

Do not claim semantic or reranked readiness unless both full sync and a search
in the selected mode succeed on the target host. FTS remains available if the
dense model gate fails.

## 7. Configure MCP for an AI agent

The MCP server requires one existing configured vault root. Point the client to
the same virtual-environment interpreter used above:

```json
{
  "mcpServers": {
    "power": {
      "command": "/home/YOU/.local/share/power-framework/venv/bin/python",
      "args": ["-m", "power_framework.mcp"],
      "env": {
        "POWER_VAULT_DIR": "/home/YOU/Documents/power-vault"
      }
    }
  }
}
```

Preflight the exact interpreter and vault before restarting the client:

```bash
POWER_VAULT_DIR="$POWER_VAULT" "$POWER_PYTHON" -c \
  'import os; from pathlib import Path; import power_framework.mcp; p=Path(os.environ["POWER_VAULT_DIR"]); assert p.is_dir(); print("MCP preflight: OK")'
```

Restart long-lived MCP clients after changing their configuration or Python
environment. See [MCP Server](mcp-server.md) for the 20-tool contract and
transport security boundary.

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

- Python is 3.11+ and the selected interpreter is inside the dedicated venv.
- CLI and distribution metadata both report `3.5.0`.
- `power_framework` imports successfully without neural or MCP extras.
- If MCP is configured, the explicit `remote` extra is installed and MCP
  preflight imports `power_framework.mcp` successfully.
- `init`, `ingest`, `index --strict`, `lint`, and `markdown-check` exit `0`.
- FTS sync exits `0` and FTS search returns the first note.
- MCP preflight uses the same interpreter and prints `MCP preflight: OK`.
- Dense/reranked readiness is recorded only after the optional target-host gate
  passes.
