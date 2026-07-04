# MCP Server

The P.O.W.E.R. Framework exposes its full functionality via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io), enabling AI agents to interact with your Obsidian vault directly.

## Running

```bash
python -m power_framework.mcp
```

Or via a direct script:

```python
from power_framework.mcp.power_server import run
import asyncio

asyncio.run(run())
```

## Available Tools

### `lint_vault`

Run health checks on a vault. Returns metadata issues, broken links, and orphans.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `vault_path` | `string` | No | Path to vault root |

### `generate_index`

Compile hierarchical index (`index.md` + per-folder `_index.md` files).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `vault_path` | `string` | No | Path to vault root |

### `read_sub_index`

Read a specific P.A.R.A. category sub-index on-demand.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | `string` | Yes | Folder name (e.g. `01_Projects`) |
| `vault_path` | `string` | No | Path to vault root |

### `ingest_note`

Create a new note with strict OKF metadata frontmatter.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `string` | Yes | Note filename |
| `note_type` | `string` | Yes | Type (`Project`, `Area`, etc.) |
| `title` | `string` | Yes | Page title |
| `description` | `string` | Yes | Short description |
| `content` | `string` | Yes | Body content |
| `resource` | `string` | No | External URL |
| `tags` | `string[]` | No | List of tags |
| `vault_path` | `string` | No | Path to vault root |

### `search_vault_tool`

Full-text search across vault notes.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | `string` | Yes | Search query |
| `max_results` | `integer` | No | Max results (default: 20) |
| `vault_path` | `string` | No | Path to vault root |
