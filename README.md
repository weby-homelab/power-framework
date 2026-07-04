<p align="center">
  <b>ENG</b> | <a href="README.ua.md">UKR</a>
</p>

# P.O.W.E.R. — AI-Native Toolkit for Second Brain

Validate, index, search, and manage your knowledge base from the command line — or let AI agents do it through MCP. Built for knowledge workers who want machine-readable notes, automated quality checks, and token-efficient AI access to their Second Brain.

[![CI](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen?logo=pytest)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/weby-homelab/power-framework?logo=github)](https://github.com/weby-homelab/power-framework/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CodeQL](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-8A2BE2?logo=materialformkdocs)](https://weby-homelab.github.io/power-framework/)

## About P.O.W.E.R. - Hybrid Knowledge Management Framework

P.O.W.E.R. is a hybrid system built to bridge the gap between human workflows, automated scripts, and LLM-based autonomous agents. The name is an acronym representing its core components: **P**.A.R.A., **O**KF, **W**iki, and **E**xecution **R**ules. It integrates these distinct architectural frameworks to construct a coherent, self-validating, and token-efficient Second Brain:

*   **P (P.A.R.A. Method)** — Organizes files based on actionability into **P**rojects, **A**reas, **R**esources, and **A**rchives. P.O.W.E.R. adopts this directory structure to dictate the lifecycle of notes. Information moves organically from raw inbox captures to active project execution, long-term reference areas, and eventual archives.
*   **O (OKF Overlay - Open Knowledge Format)** — Imposes a strict schema layer over standard Markdown files. Built on Pydantic v2 schemas, OKF requires every note to be explicitly typed and validated (containing required frontmatter attributes such as title, description, tags, and timestamps). This turns unstructured markdown folders into a predictable, queryable, and machine-readable local database.
*   **W (LLM-Wiki)** — Transforms the knowledge base into a hierarchical, AI-readable catalog. By generating top-level `index.md` maps and folder-level `_index.md` sub-catalogs, it provides token-efficient navigation that slashes AI agent context usage by **75% to 94%**.
*   **E.R. (Execution Rules)** — Integrates operational rules and guidelines specifically formatted for AI agents (like `AGENTS.md`, `Successor-Hub.md`, and `MASTER-LESSONS-LEARNED.md`), enforcing safe, non-destructive editing boundaries and dictating how human and AI actors interact with the system.



## Why P.O.W.E.R.?

Unlike generic Obsidian helpers, P.O.W.E.R. is designed from the ground up for **AI-first knowledge management**:

- **AI-native metadata** — Pydantic v2 schemas enforce strict OKF frontmatter, so every note is machine-readable
- **Token-efficient indexing** — hierarchical `index.md` + per-folder `_index.md` cuts AI agent context usage by ~75%
- **MCP-native** — expose all tools to any MCP-compatible AI client (Claude, OpenCode, Cursor) with zero glue code
- **Production-grade** — 144 tests, 90% coverage, CodeQL scanning, OIDC-signed PyPI releases

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
| **CLI** | `power init`, `lint`, `index`, `ingest`, `search` — full vault management from terminal |
| **MCP Server** | Exposes `lint_vault`, `generate_index`, `read_sub_index`, `ingest_note`, `search_vault` to any AI agent |
| **OKF Validation** | Pydantic v2 schemas enforce strict metadata on every note |
| **Full-Text Search** | Relevance-scored search across title, body, and tags with context snippets |
| **Hierarchical Index** | `index.md` (navigation map) + per-folder `_index.md` (detailed catalogs) for token-efficient AI reading (~75-94% token savings) |
| **CI/CD** | 144 tests, 90% coverage, CodeQL SAST, OIDC Trusted Publishing to PyPI |
| **Documentation** | Full [mkdocs-material site](https://weby-homelab.github.io/P.O.W.E.R/) with API reference and guides |

## Migration Report

Read the full technical report on the transition from flat to hierarchical indexing:
- **[English: Hierarchical Index Migration Report](docs/hierarchical-index-migration.md)** — performance metrics, architecture, insights
- **[Українська: Звіт міграції на ієрархічний індекс](docs/hierarchical-index-migration.ua.md)** — повний технічний звіт

### AI Agent Migration Guide

Step-by-step protocol for any AI agent (Claude, GPT, Gemini, OpenCode) to autonomously migrate an existing Obsidian vault into P.O.W.E.R. structure:

- **[English: AI Agent Migration Guide](docs/migration-guide.md)** — 5-phase protocol with MCP tools, classification heuristics, and troubleshooting
- **[Українська: Ґайд міграції для AI-агента](docs/migration-guide.ua.md)** — покроковий протокол для будь-якого AI-агента

## Who Is This For

- **Knowledge workers** who want AI agents to understand and maintain their knowledge base
- **Developers** building a structured Second Brain with machine-readable metadata
- **Teams** that need consistent note formatting and automated quality checks

## Commands

```
power init <path>              Create a new vault with P.A.R.A. folder structure
power lint <path>              Scan for broken links, missing metadata, orphans
power index <path>             Generate hierarchical index (index.md + _index.md files)
power search <path> <query>    Full-text search with relevance scoring
power ingest <path> [options]  Create a new note with validated OKF metadata
```

### Ingest Examples

```bash
power ingest ~/my-vault --type Project --title "My App" --description "A new project"
power ingest ~/my-vault --type Resource --title "Docker Guide" --description "Docker best practices" --tags devops,docker --resource "https://docs.docker.com"
```

### Search Examples

```bash
power search ~/my-vault "api authentication"
power search ~/my-vault "deployment guide" --max-results 5
```

## MCP Server Setup

Connect P.O.W.E.R. to any MCP-compatible AI client:

```bash
pip install power-framework
```

**Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "power": {
      "command": "python3",
      "args": ["-m", "power_framework.mcp"],
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
    "command": ["python3", "-m", "power_framework.mcp"],
    "enabled": true
  }
}
```

## Vault Structure

P.O.W.E.R. organizes your vault using the **P.A.R.A.** method with **OKF metadata** on every note:

```
~/my-vault
├── 00_Inbox/
│   └── _index.md        # Detailed sub-index for Inbox notes
├── 01_Projects/
│   └── _index.md        # Detailed sub-index for Projects
├── 02_Areas/
│   └── _index.md        # Detailed sub-index for Areas
├── 03_Resources/
│   └── _index.md        # Detailed sub-index for Resources
├── 04_Archive/
│   └── _index.md        # Detailed sub-index for Archive
├── 05_Templates/        # Note templates with OKF frontmatter
├── 06_Daily_Logs/
│   └── _index.md        # Detailed sub-index for Daily Logs
├── PROTOCOLS/           # System specs for AI agents
├── index.md             # Navigation map (links to sub-indexes)
└── log.md               # Append-only change log
```

### Hierarchical Index Protocol

AI agents read the vault efficiently by following this pattern:

1. **Read `index.md`** — identify the relevant category by note counts
2. **Call `read_sub_index` MCP tool** — get detailed entries for that category
3. **Read specific notes** — only when the sub-index indicates relevance
4. **NEVER glob all `.md` files** — use sub-indexes as a map (~75% token savings)

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
- **W** — **LLM-Wiki** (A. Karpathy's philosophy) — treating your knowledge base as a wiki that LLMs can read, write, and maintain through automated catalog indexing, chronological log, and structural link linting
- **E.R.** — **Execution Rules** — GPG-signed commits, PR-only workflow, cron-based sync, branch cleanup

### Visual Framework Diagram

```mermaid
graph TB
    subgraph Human ["👤 Human (Markdown UI)"]
        PARA["P.A.R.A. Directory Structure"]
    end

    subgraph OKF ["📄 OKF Overlay (Metadata Schema)"]
        YAML["YAML Frontmatter"]
    end

    subgraph Wiki ["📖 LLM-Wiki (Karpathy's Philosophy)"]
        IndexMD["index.md (Navigation Map)"]
        SubIndex["_index.md (Per-Folder Details)"]
        LogMD["log.md (Change Log)"]
        Lint["Link Linting"]
    end

    subgraph AI ["🤖 AI Agent (Local / Cloud)"]
        Ingest["Ingest Note"]
        Index["Rebuild Hierarchical Index"]
        ReadSub["Read Sub-Index On-Demand"]
    end

    subgraph ER ["🔐 Execution Rules"]
        GPG["GPG-Signed Commits"]
        PR["PR-Only Workflow"]
        Sync["Cron Auto-Sync"]
    end

    Human -- Writes Notes --> YAML
    YAML -- Parsed by --> AI
    AI -- Updates --> IndexMD
    AI -- Updates --> SubIndex
    AI -- Appends --> LogMD
    AI -- Runs Checks --> Lint
    ReadSub -- On-Demand --> SubIndex
    IndexMD -. Synced via .-> Sync
    SubIndex -. Synced via .-> Sync
    LogMD -. Synced via .-> Sync
    Sync --> GPG
    GPG --> PR
```

### Core Library (`src/power_framework/`)

| Module | Purpose |
|--------|---------|
| `core/models.py` | Pydantic v2 schemas for OKF metadata validation |
| `core/parser.py` | Safe YAML frontmatter parsing (PyYAML-based) |
| `core/indexer.py` | Vault scanning and index.md generation |
| `core/linter.py` | Health checks: broken links, missing metadata, orphans |
| `core/searcher.py` | Full-text search with relevance scoring |
| `core/utils.py` | Path traversal protection, atomic writes, backups |
| `core/cli.py` | Command-line interface (init, lint, index, ingest, search) |
| `mcp/server.py` | FastMCP server exposing all tools to AI agents |

All components share `power_framework.core` as the single source of truth.

</details>

## Development

```bash
git clone https://github.com/weby-homelab/power-framework.git
cd power-framework
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (144 tests, 90%+ coverage)
pytest tests/ -v

# Lint & format
ruff check src/ tests/
ruff format src/ tests/

# Type check
mypy src/power_framework/
```

## License

GPLv3 — Built in Ukraine ⚡

<p align="center">
  Built in Ukraine under air raid sirens &amp; blackouts ⚡<br>
  &copy; 2026 Weby Homelab
</p>
