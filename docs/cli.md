# CLI Reference

## Synopsis

```
power [-h] [-v] {init,lint,index,ingest,search} ...
```

## Global options

| Flag | Description |
|------|-------------|
| `-h`, `--help` | Show help message |
| `-v`, `--version` | Show version |

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
