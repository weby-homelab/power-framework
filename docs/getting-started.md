# Getting Started

## Installation

```bash
pip install git+https://github.com/weby-homelab/power-framework.git@v1.8.0
```

Alternatively, install from a GitHub Release:

```bash
pip install https://github.com/weby-homelab/power-framework/releases/download/v1.8.0/power_framework-1.8.0-py3-none-any.whl
```

Verify:

```bash
power --version
```

## Create a vault

```bash
power init my-vault
```

Creates the P.A.R.A. directory structure:

```
vault/
├── 00_Inbox/
├── 01_Projects/
├── 02_Areas/
├── 03_Resources/
├── 04_Archive/
├── 05_Templates/
├── 06_Daily_Logs/
├── PROTOCOLS/
├── index.md
└── log.md
```

## Add notes

```bash
power ingest ~/my-vault --type Project --title "My Project" --description "A new project"
```

## Run health checks

```bash
power lint ~/my-vault
```

## Auto-heal frontmatter

```bash
power heal ~/my-vault                  # Preview (dry run)
power heal ~/my-vault --no-dry-run     # Apply fixes
```

## Check markdown quality

```bash
power markdown-check ~/my-vault
```

## Generate index

```bash
power index ~/my-vault
```

## Search the vault

```bash
power search ~/my-vault "my query"
power search ~/my-vault "my query" --mode hybrid --max-results 10
```

## ROT audit with extended scoring

```bash
power rot ~/my-vault --extended
```

## Archive stale notes

```bash
power archive ~/my-vault                  # Preview (dry run)
power archive ~/my-vault --no-dry-run     # Move to 04_Archive/
```

## Suggest related notes (Graph RAG)

```bash
power suggest-related ~/my-vault
```

## Cron maintenance

```bash
power cron ~/my-vault
```

## MCP server

Start the MCP server for AI agent integration:

```bash
# Local (stdio)
python -m power_framework.mcp

# HTTP (Docker / remote)
POWER_MCP_TRANSPORT=http python -m power_framework.mcp
```

See [MCP Server](mcp-server.md) for full documentation.
