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
power init [path]
```

### `lint`

Run health checks on a vault.

```
power lint [--vault-path PATH]
```

Checks:
- Missing or invalid YAML frontmatter
- Broken internal links (`[[wikilinks]]`)
- Orphan notes (not linked from any other note)
- Metadata completeness (type, title, description)

### `index`

Generate hierarchical indexes.

```
power index [--vault-path PATH]
```

Creates `index.md` (overview) and per-folder `_index.md` (detailed entries).

### `ingest`

Create a new note with validated OKF metadata.

```
power ingest --type TYPE --title TITLE --description DESC [--tags TAGS] [--resource URL] [--vault-path PATH]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--type` | Yes | Note type (`Project`, `Area`, `Resource`, `Daily Log`, `Archive`, `System Guide`) |
| `--title` | Yes | Note title (max 120 chars) |
| `--description` | Yes | One-line description (max 150 chars) |
| `--tags` | No | Comma-separated tags |
| `--resource` | No | URL to external resource |
| `--vault-path` | No | Path to vault |

### `search`

Full-text search across vault notes.

```
power search QUERY [--vault-path PATH]
```
