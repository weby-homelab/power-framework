# MCP Server (FastMCP 3.x)

The P.O.W.E.R. Framework exposes its full functionality via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io), powered by [FastMCP 3.x](https://gofastmcp.com) (Prefect). This enables AI agents (Claude, OpenCode, Cursor) to interact with your knowledge vault directly.

## Transport modes

### Local (stdio) — default

```bash
python -m power_framework.mcp
```

The server starts with **stdio** transport — ideal for local AI clients like Claude Desktop or OpenCode.

### HTTP (Docker / remote) — v2.0.2

Set `POWER_MCP_TRANSPORT=http` for HTTP mode with `/health` endpoint on port 8000:

```bash
POWER_MCP_TRANSPORT=http python -m power_framework.mcp
```

Docker Compose example:

```yaml
services:
    power-mcp:
        image: weby-homelab/power-framework:v2.0.2
        ports:
            - "8000:8000"
        volumes:
            - ./vault:/vault:ro
        environment:
            - POWER_VAULT_DIR=/vault
            - POWER_MCP_TRANSPORT=http
        cap_drop:
            - ALL
        read_only: true
```

Health check: `GET http://localhost:8000/health`

## Client configuration

**Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "power": {
            "command": "python3",
            "args": ["-m", "power_framework.mcp"],
            "env": {
                "POWER_VAULT_DIR": "/path/to/your/vault"
            }
        }
    }
}
```

**OpenCode** (`~/.config/opencode/opencode.jsonc`):

```jsonc
"mcp": {
  "power": {
    "type": "local",
    "command": ["python3", "-m", "power_framework.mcp"],
    "enabled": true
  }
}
```

## Error handling (v2.0.2)

All tools raise structured `ToolError` exceptions with descriptive messages. The server uses `mask_error_details=True` and `ErrorHandlingMiddleware` — internal stack traces are hidden from clients, only user-facing messages are exposed.

## Available tools

12 MCP tools are exposed, all asynchronous with `asyncio.to_thread()` for filesystem I/O.

### `lint_vault`

Run health checks: missing metadata, broken links, orphans, stale notes.

| Parameter    | Type     | Required | Description        |
| ------------ | -------- | -------- | ------------------ |
| `vault_path` | `string` | No       | Path to vault root |

### `generate_index`

Compile hierarchical index (`index.md` + per-folder `_index.md` files). Rate limited: 5/min.

| Parameter    | Type     | Required | Description        |
| ------------ | -------- | -------- | ------------------ |
| `vault_path` | `string` | No       | Path to vault root |

### `read_sub_index`

Read a specific P.A.R.A. category sub-index. Read-only — does not generate files.

| Parameter    | Type     | Required | Description                      |
| ------------ | -------- | -------- | -------------------------------- |
| `category`   | `string` | Yes      | Folder name (e.g. `01_Projects`) |
| `vault_path` | `string` | No       | Path to vault root               |

### `ensure_sub_index`

Generate and read a sub-index for a category. Write path — use when `_index.md` is missing.

| Parameter    | Type     | Required | Description                      |
| ------------ | -------- | -------- | -------------------------------- |
| `category`   | `string` | Yes      | Folder name (e.g. `01_Projects`) |
| `vault_path` | `string` | No       | Path to vault root               |

### `ingest_note`

Create a new note with strict OKF metadata. Rebuilds index + appends to log.md. Rate limited: 10/min.

| Parameter     | Type       | Required | Description                                                           |
| ------------- | ---------- | -------- | --------------------------------------------------------------------- |
| `name`        | `string`   | Yes      | Note filename                                                         |
| `note_type`   | `string`   | Yes      | `Project`, `Area`, `Resource`, `Daily Log`, `Archive`, `System Guide` |
| `title`       | `string`   | Yes      | Page title                                                            |
| `description` | `string`   | Yes      | Short description (max 150 chars)                                     |
| `content`     | `string`   | Yes      | Body content                                                          |
| `resource`    | `string`   | No       | External URL                                                          |
| `tags`        | `string[]` | No       | List of tags                                                          |
| `vault_path`  | `string`   | No       | Path to vault root                                                    |

### `search_vault_tool`

Full-text search across all vault notes. Three modes: `fts` (BM25, default), `vector` (TF cosine), `hybrid` (RRF fusion).

| Parameter     | Type      | Required | Description                                   |
| ------------- | --------- | -------- | --------------------------------------------- |
| `query`       | `string`  | Yes      | Search query                                  |
| `max_results` | `integer` | No       | Max results (default: 20)                     |
| `search_mode` | `string`  | No       | `fts`, `vector`, or `hybrid` (default: `fts`) |
| `vault_path`  | `string`  | No       | Path to vault root                            |

### `synthesize_session`

Agent Auto-Ingest Feedback Loop. Create session synthesis notes with governance metadata, Graph RAG links, and full index/log maintenance.

| Parameter     | Type       | Required | Description                             |
| ------------- | ---------- | -------- | --------------------------------------- |
| `name`        | `string`   | Yes      | Filename (e.g. `2026-07-06_session.md`) |
| `title`       | `string`   | Yes      | Session title                           |
| `description` | `string`   | Yes      | Short summary                           |
| `content`     | `string`   | Yes      | Body content                            |
| `note_type`   | `string`   | No       | Default: `Daily Log`                    |
| `tags`        | `string[]` | No       | List of tags                            |
| `related`     | `string[]` | No       | Graph RAG links to related notes        |
| `owner`       | `string`   | No       | Responsible person/team                 |
| `vault_path`  | `string`   | No       | Path to vault root                      |

### `rot_audit`

ROT (Redundant, Outdated, Trivial) audit. Use `extended=True` for A2 scoring (content dedup, link rot, freshness, usage).

| Parameter    | Type      | Required | Description                        |
| ------------ | --------- | -------- | ---------------------------------- |
| `vault_path` | `string`  | No       | Path to vault root                 |
| `extended`   | `boolean` | No       | Enable A2 scoring (default: false) |

### `archive_notes`

Move stale/expired notes to `04_Archive/`. Uses `dry_run=True` by default for safe preview.

| Parameter    | Type      | Required | Description                            |
| ------------ | --------- | -------- | -------------------------------------- |
| `dry_run`    | `boolean` | No       | Preview without moving (default: true) |
| `vault_path` | `string`  | No       | Path to vault root                     |

### `suggest_related_tool`

Auto-suggest related notes based on keyword and tag overlap (Graph RAG).

| Parameter     | Type      | Required | Description                           |
| ------------- | --------- | -------- | ------------------------------------- |
| `target_path` | `string`  | No       | Analyze relations for a specific note |
| `max_results` | `integer` | No       | Maximum suggestions (default: 5)      |
| `vault_path`  | `string`  | No       | Path to vault root                    |

### `heal_frontmatter_tool`

Scan and heal missing/invalid frontmatter fields. Dry run by default.

| Parameter    | Type      | Required | Description                             |
| ------------ | --------- | -------- | --------------------------------------- |
| `dry_run`    | `boolean` | No       | Preview without editing (default: true) |
| `vault_path` | `string`  | No       | Path to vault root                      |

### `check_markdown_tool`

Check markdown quality: trailing whitespace, list markers, header jumps, code language hints.

| Parameter    | Type     | Required | Description        |
| ------------ | -------- | -------- | ------------------ |
| `vault_path` | `string` | No       | Path to vault root |

## Security

- **Error masking** — Internal stack traces hidden from clients
- **Rate limiting** — Write tools (ingest, synthesize): 10/min; Index generation: 5/min
- **Path traversal** — All vault paths validated via `Path.relative_to()` boundary check
- **SSRF protection** — Link rot checks block private/loopback/link-local IPs
- **Docker hardening** — `cap_drop: [ALL]`, `read_only: true`, non-root user
