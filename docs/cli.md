# CLI Reference

## Synopsis

```
power [-h] [-v] {init,lint,index,ingest,search,rot,archive,cron,heal,markdown-check,suggest-related} ...
```

## Global options

| Flag | Description |
|------|-------------|
| `-h`, `--help` | Show help message |
| `-v`, `--version` | Show version |
| `--verbose` | Enable verbose (DEBUG) logging |

## Commands

### `init`

Scaffold a new OKF-compliant vault.

```
power init path
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to create the vault directory |

### `lint`

Run health checks on a vault.

```
power lint path
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |

Checks:
- Missing or invalid YAML frontmatter
- Broken internal links (`[[wikilinks]]`)
- Orphan notes (not linked from any other note)
- Metadata completeness (type, title, description)

### `index`

Generate hierarchical indexes.

```
power index path
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |

Creates `index.md` (overview) and per-folder `_index.md` (detailed entries).

### `ingest`

Create a new note with validated OKF metadata.

```
power ingest path --type TYPE --title TITLE --description DESC [--tags TAGS] [--resource URL] [--overwrite]
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
| `--type`, `-t` | Yes | Note type (`Project`, `Area`, `Resource`, `Daily Log`, `Archive`, `System Guide`) |
| `--title` | Yes | Note title |
| `--description` | Yes | One-line description (max 150 chars) |
| `--tags` | No | Space-separated tags |
| `--resource` | No | URL to external resource |
| `--overwrite` | No | Overwrite existing note |

### `search`

Full-text search across vault notes.

```
power search path query [--max-results MAX_RESULTS]
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
| `query` | Yes | Search query (supports multiple terms and "quoted phrases") |
| `--max-results`| No | Maximum number of results (default: 20) |
| `--mode` | No | Search mode: `fts` (default), `vector`, `hybrid` |

### `rot`

ROT Audit — detect redundant, outdated, and trivial notes.

```
power rot path [--extended]
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
| `--extended` | No | Enable extended A2 scoring (content dedup, link rot, freshness, usage) |

### `archive`

Auto-archive stale notes to `04_Archive/`.

```
power archive path [--no-dry-run]
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
| `--no-dry-run` | No | Actually move notes (default: dry run, preview only) |

### `suggest-related`

Suggest cross-note relations for Graph RAG enrichment.

```
power suggest-related path [--target TARGET_PATH] [--max-results MAX_RESULTS]
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
| `--target` | No | Analyze relations for a specific note path |
| `--max-results` | No | Maximum number of suggestions (default: 5) |

### `heal`

Heal missing/invalid frontmatter in vault notes.

```
power heal path [--no-dry-run]
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
| `--no-dry-run` | No | Actually apply fixes (default: dry run, preview only) |

Auto-fills: `type` (from folder), `title` (from filename), `description` (from first paragraph), `timestamp` (now), and fixes type casing. Creates timestamped backups before live edits.

### `markdown-check`

Check markdown quality issues across the vault.

```
power markdown-check path
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |

Checks: trailing whitespace, inconsistent list markers (`-` vs `*`), header jumps (e.g. h1→h3), code blocks without language hints.

### `cron`

Run automated maintenance: lint + index + rot audit.

```
power cron path
```

| Argument/Flag | Required | Description |
|---------------|----------|-------------|
| `path` | Yes | Path to the vault directory |
