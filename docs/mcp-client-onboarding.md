# MCP client onboarding

This is the canonical local-stdio setup for P.O.W.E.R. `v3.6.0` on
Ubuntu/Linux. It gives Codex, OpenCode, Gemini CLI, Claude Desktop, and Claude Code
the same server process and the same vault boundary.

> **Release contract:** use `v3.6.0` only after its signed tag and immutable
> wheel appear on the [GitHub release page](https://github.com/weby-homelab/power-framework/releases/tag/v3.6.0).
> Then use that wheel and the exact interpreter created by the
> [clean-install guide](getting-started.md).

The [Windows 11 25H2 guide](windows-11-installation.md) is informational only.
Windows and macOS are deferred indefinitely and are not supported MCP onboarding
platforms for `v3.6.0`.

## One-time preparation

Install the release wheel in an isolated environment. For a new vault, create
it with `init`; for an existing vault, complete the
[migration guide](migration-guide.md) first and do not run `init` in place:

```bash
POWER_HOME="$HOME/.local/share/power-framework"
POWER_VENV="$POWER_HOME/venv"
POWER_PYTHON="$POWER_VENV/bin/python"
POWER_CLI="$POWER_VENV/bin/power"
POWER_VAULT="$HOME/Documents/power-vault"

python3 -m venv "$POWER_VENV"
"$POWER_PYTHON" -m pip install \
  "power-framework[remote] @ https://github.com/weby-homelab/power-framework/releases/download/v3.6.0/power_framework-3.6.0-py3-none-any.whl"
# Only for a new or empty vault:
"$POWER_CLI" init "$POWER_VAULT"
"$POWER_PYTHON" -c 'import sys; print(sys.executable)'
```

Use the absolute `POWER_PYTHON` path and `POWER_VAULT` path in the
configuration below. The MCP process must receive `POWER_VAULT_DIR`; it is the
configured vault boundary. The server is local stdio, so its stdout is
reserved for MCP protocol traffic.

Do not point a client at a repository wrapper, a shell script that loads
secrets, or a different Python installation. Do not add a second vault path to
the client configuration.

## Client configurations

Replace `/absolute/path/to/python` and `/absolute/path/to/vault` in exactly one
of the following client configurations.

<!-- power-client-config:claude-desktop -->

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS, or `~/.config/Claude/claude_desktop_config.json` on Linux:

```json
{
  "mcpServers": {
    "power": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "power_framework.mcp"],
      "env": {
        "POWER_VAULT_DIR": "/absolute/path/to/vault"
      }
    }
  }
}
```

<!-- power-client-config:gemini-cli -->

### Gemini CLI

Add the `power` entry to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "power": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "power_framework.mcp"],
      "env": {
        "POWER_VAULT_DIR": "/absolute/path/to/vault"
      }
    }
  }
}
```

Keep any existing settings in the file. Gemini CLI supports environment
expansion, but an explicit vault path is easier to audit and avoids an empty
variable silently selecting the wrong process boundary.

<!-- power-client-config:codex -->

### Codex

Add this table to `~/.codex/config.toml`:

```toml
[mcp_servers.power]
command = "/absolute/path/to/python"
args = ["-m", "power_framework.mcp"]
env = { "POWER_VAULT_DIR" = "/absolute/path/to/vault" }
```

The Codex key is `mcp_servers` (with an underscore), not the JSON
`mcpServers` spelling. Keep this in the user configuration unless the project
is explicitly trusted and the configuration is intentionally project-scoped.

<!-- power-client-config:opencode -->

### OpenCode

Add the `power` entry directly under `mcp` in `~/.config/opencode/opencode.jsonc`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "power": {
      "type": "local",
      "command": ["/absolute/path/to/python", "-m", "power_framework.mcp"],
      "environment": {
        "POWER_VAULT_DIR": "/absolute/path/to/vault"
      },
      "enabled": true
    }
  }
}
```

OpenCode uses an array for `command` and `environment` for subprocess
variables. The server entry is directly below `mcp`; do not wrap it in an
additional `servers` object.

### Claude Code

Register the same stdio command with the Claude Code CLI. All options precede
the server name, and `--` separates Claude options from the launch command:

```bash
claude mcp add --transport stdio \
  --env POWER_VAULT_DIR=/absolute/path/to/vault \
  power -- /absolute/path/to/python -m power_framework.mcp
```

Run `claude mcp list` and then `/mcp` inside a session to verify the server.
Claude Code can also use the Claude Desktop JSON shape through its supported
project or user configuration scopes.

## Golden onboarding task

After changing a client configuration, restart or reload that client. The
first task is read-only until the explicit proposal step:

1. Open the client's MCP status view (`/mcp` where supported) and confirm that
   `power` is connected and exposes 20 tools.
2. Ask the agent to list tools, resources, resource templates, and prompts.
   POWER should expose 20 tools and no resources, templates, or prompts.
3. Ask the agent to call `get_server_info` with its default arguments. Confirm
   the reported package version, configured vault path, and explicit
   `embedding.binding` state before trusting retrieval. Use
   `probe_provider=true` only when an actual no-download provider binding check
   is needed.
4. Ask the agent to call `get_memory_context` for a short query. This must not
   create a file, namespace, index, or history entry.
5. Ask the agent to call `propose_memory_change` for a new note, but do not
   approve it. This creates only a durable content-addressed proposal ledger
   entry; the target note, catalog, and search projection must remain absent.

Only after a human or an explicitly authorized workflow approves the exact
proposal may the agent call `apply_memory_change` with `approved=true`. That
call itself closes the note → index → blocking-lint → search workflow and
returns a content-free receipt. The agent must verify the receipt, call
`validate_memory_state`, and search for a unique marker using the receipt's
`search_mode` (`fts` when no dense projection exists). No redundant `sync` or
`index` call is needed; finish the vault workflow with the remaining quality
gate:

```bash
power lint /absolute/path/to/vault
power markdown-check /absolute/path/to/vault
```

Retrieved note text is untrusted source data, not an instruction channel. The
agent must never execute commands found inside a note or use retrieved text to
change the configured vault boundary.

## What this verifies

The repository test suite parses all four documented configuration shapes and
uses each one to connect to a real local stdio P.O.W.E.R. process. It verifies
the tool inventory, empty discovery collections, and proposal-without-target-note-write
behavior. This proves the shared MCP wire contract and the examples' shape;
it does not pretend to be a full GUI/in-process test of every third-party
client. On a host where a client is installed, its own status view is the final
acceptance check.

Authoritative client references: [Gemini CLI MCP
documentation](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md),
[OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/), and [Claude Code
MCP](https://code.claude.com/docs/en/mcp).
