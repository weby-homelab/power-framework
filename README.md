<p align="center">
  <b>ENG</b> | <a href="README.ua.md">UKR</a>
</p>

# P.O.W.E.R. — AI-Native Toolkit for Obsidian

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E74C3C?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-00C853?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io/)
[![CI](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/ci.yml/badge.svg)](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/weby-homelab/P%2EO%2EW%2EE%2ER?logo=github)](https://github.com/weby-homelab/P.O.W.E.R/releases)

Validate, index, and manage your Obsidian vault from the command line — or let AI agents do it through MCP.

## Quick Start

```bash
pip install power-framework

power init ~/my-vault      # Create vault structure
power lint ~/my-vault      # Check for broken links & missing metadata
power index ~/my-vault     # Generate catalog index.md
```

## What's Inside

| Feature | What it does |
|---------|-------------|
| **CLI** | `power init`, `lint`, `index`, `ingest` — manage your vault from terminal |
| **MCP Server** | Exposes `lint_vault`, `generate_index`, `ingest_note` to any AI agent (Claude, Cursor, OpenCode) |
| **OKF Validation** | Pydantic v2 schemas enforce strict metadata on every note |
| **Health Linting** | Finds broken links, missing metadata, and orphan notes |
| **Auto-Sync** | Cron-compatible script with GPG-signed commits for continuous backup |

## Who Is This For

- **Obsidian users** who want AI agents to understand and maintain their vault
- **Developers** building a structured Second Brain with machine-readable metadata
- **Teams** that need consistent note formatting and automated quality checks

## Commands

```
power init <path>              Create a new vault with P.A.R.A. folder structure
power lint <path>              Scan for broken links, missing metadata, orphans
power index <path>             Rebuild index.md catalog from all notes
power ingest <path> [options]  Create a new note with validated OKF metadata
```

### Ingest Examples

```bash
power ingest ~/my-vault --type Project --title "My App" --description "A new project"
power ingest ~/my-vault --type Resource --title "Docker Guide" --description "Docker best practices" --tags [devops, docker] --resource "https://docs.docker.com"
```

## MCP Server Setup

Connect P.O.W.E.R. to any MCP-compatible AI client:

```bash
pip install power-framework mcp
```

**Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "power": {
      "command": "python3",
      "args": ["-m", "mcp_servers.power_server"],
      "env": {
        "POWER_VAULT_DIR": "/path/to/your/obsidian/vault"
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
    "command": ["python3", "-m", "mcp_servers.power_server"],
    "enabled": true
  }
}
```

## Vault Structure

P.O.W.E.R. organizes your vault using the **P.A.R.A.** method with **OKF metadata** on every note:

```
~/my-vault
├── 00_Inbox/          # Quick captures and raw inputs
├── 01_Projects/       # Active projects with deadlines
├── 02_Areas/          # Ongoing responsibilities
├── 03_Resources/      # Reusable guides and references
├── 04_Archive/        # Completed or retired notes
├── 05_Templates/      # Note templates with OKF frontmatter
├── 06_Daily_Logs/     # Chronological session logs
├── PROTOCOLS/         # System specs for AI agents
├── index.md           # Auto-generated catalog
└── log.md             # Append-only change log
```

Every note starts with validated YAML frontmatter:

```yaml
---
type: Project
title: "My App"
description: "A new project with clear goals"
tags: [active, dev]
timestamp: 2026-07-02T19:00:00
---
```

## Architecture Details

<details>
<summary><strong>P.O.W.E.R. Methodology — click to expand</strong></summary>

The framework combines four complementary methodologies:

- **P** — **P.A.R.A.** (Projects, Areas, Resources, Archive) — logical folder structure for human cognition
- **O** — **OKF Overlay** (Open Knowledge Format) — YAML frontmatter on every file for instant AI parsing
- **W** — **LLM-Wiki** — automated catalog indexing, chronological log, and structural link linting
- **E.R.** — **Execution Rules** — GPG-signed commits, PR-only workflow, cron-based sync, branch cleanup

### Visual Framework Diagram

```mermaid
graph TB
    subgraph Human ["👤 Human (Obsidian UI)"]
        PARA["P.A.R.A. Directory Structure"]
    end

    subgraph AI ["🤖 AI Agent (Local / Cloud)"]
        Ingest["Ingest Note"]
        Lint["Lint Vault"]
        Index["Rebuild Index"]
    end

    subgraph OKF ["📄 OKF Overlay (Metadata Schema)"]
        YAML["YAML Frontmatter"]
        IndexMD["index.md (Catalog)"]
        LogMD["log.md (Change Log)"]
    end

    Human -- Writes Notes --> YAML
    YAML -- Parsed by --> AI
    AI -- Updates --> IndexMD
    AI -- Appends --> LogMD
    AI -- Runs Checks --> Lint
```

### Core Library (`power_core`)

| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic v2 schemas for OKF metadata validation |
| `parser.py` | Safe YAML frontmatter parsing (PyYAML-based) |
| `indexer.py` | Vault scanning and index.md generation |
| `linter.py` | Health checks: broken links, missing metadata, orphans |
| `utils.py` | Path traversal protection, atomic writes, backups |
| `cli.py` | Command-line interface (init, lint, index, ingest) |

All components share `power_core` as the single source of truth.

</details>

## Development

```bash
git clone https://github.com/weby-homelab/P.O.W.E.R.git
cd P.O.W.E.R
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint & format
ruff check power_core/ mcp_servers/ scripts/ tests/
ruff format power_core/ mcp_servers/ scripts/ tests/

# Type check
mypy power_core/
```

## License

MIT — use it to build your personal or enterprise knowledge base.

<p align="center">
  Built in Ukraine under air raid sirens &amp; blackouts ⚡<br>
  &copy; 2026 Weby Homelab
</p>
