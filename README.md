<p align="center">
  <b>ENG</b> | <a href="README.ua.md">UKR</a>
</p>

# P.O.W.E.R. — AI-Native Toolkit for Second Brain

Validate, index, search, and manage your knowledge base from the command line — or let AI agents do it through MCP. Built for knowledge workers who want machine-readable notes, automated quality checks, and token-efficient AI access to their Second Brain.

[![CI](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen?logo=pytest)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/weby-homelab/power-framework?logo=github)](https://github.com/weby-homelab/power-framework/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CodeQL](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-8A2BE2?logo=materialformkdocs)](https://weby-homelab.github.io/power-framework/)

## About P.O.W.E.R. - Hybrid Knowledge Management Framework

P.O.W.E.R. is a hybrid system built to bridge the gap between human workflows, automated scripts, and LLM-based autonomous agents. The name is an acronym representing its core components: **P**.A.R.A., **O**KF, **W**iki, and **E**xecution **R**ules. It integrates these distinct architectural frameworks to construct a coherent, self-validating, and token-efficient Second Brain.

## Why P.O.W.E.R.?

Unlike generic knowledge management tools, P.O.W.E.R. is designed from the ground up for **AI-first knowledge management**:

- **AI-native metadata** — Pydantic v2 schemas enforce strict OKF frontmatter, so every note is machine-readable; includes governance fields (`owner`, `status`, `expiry`) and Graph RAG links (`related`)
- **Token-efficient indexing** — hierarchical `index.md` + per-folder `_index.md` cuts AI agent context usage by ~75%
- **Knowledge Graph** — `related` field connects notes across the vault; visualized in sub-indexes for Graph RAG workflows
- **Freshness Monitoring** — linter detects stale/expired notes based on `expiry` metadata field
- **Agent Auto-Ingest** — `synthesize_session` MCP tool lets agents autonomously create permanent knowledge artifacts with governance + graph links + full catalog maintenance
- **MCP-native** — expose all 12 tools to any MCP-compatible AI client (Claude, OpenCode, Cursor) with zero glue code, powered by FastMCP 3.x
- **Production-grade** — 360+ tests, 80%+ coverage, CodeQL scanning, Automated GitHub Releases

## Quick Start

```bash
pip install git+https://github.com/weby-homelab/power-framework.git@v2.0.3

power init ~/my-vault          # Create vault structure
power lint ~/my-vault          # Check for broken links & missing metadata
power index ~/my-vault         # Generate catalog index.md
power heal ~/my-vault          # Auto-fix missing/invalid frontmatter
power markdown-check ~/my-vault  # Check markdown quality issues
```

## What's Inside

| Feature                         | What it does                                                                                                                                                                                                                                                                      |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CLI**                         | `power init`, `lint`, `index`, `ingest`, `search`, `rot`, `archive`, `cron`, `heal`, `markdown-check`, `suggest-related` — 11 commands for full vault management                                                                                                                  |
| **MCP Server**                  | Exposes `lint_vault`, `generate_index`, `read_sub_index`, `ensure_sub_index`, `ingest_note`, `search_vault_tool`, `synthesize_session`, `rot_audit`, `archive_notes`, `suggest_related_tool`, `heal_frontmatter_tool`, `check_markdown_tool` — 12 tools for AI agents             |
| **OKF Validation**              | Pydantic v2 schemas enforce strict metadata on every note with governance (`owner`, `status`, `expiry`)                                                                                                                                                                           |
| **Knowledge Graph (Graph RAG)** | `related` field in OKF frontmatter supporting `TypedRelation` (path, relation, confidence) with BFS traversal and Mermaid diagram export (`to_mermaid`)                                                                                                                           |
| **Freshness Monitoring**        | Linter flags stale/expired notes by checking `expiry` dates, ensuring your vault stays current                                                                                                                                                                                    |
| **Agent Auto-Ingest**           | `synthesize_session` MCP tool — agents autonomously create permanent notes with governance + graph links + full index rebuild                                                                                                                                                     |
| **ROT Audit**                   | Detects redundant, outdated, and trivial notes using dense embedding semantic deduplication and LLM fact contradiction checks                                                                                                                                                     |
| **Auto-Archive**                | Automatically archives stale notes to `04_Archive/` — `power archive <path>` with dry-run preview                                                                                                                                                                                 |
| **Healer**                      | Auto-fixes missing/invalid frontmatter fields (title, description, type, timestamp) — `power heal <path>`                                                                                                                                                                         |
| **Markdown Checks**             | Detects trailing whitespace, inconsistent list markers, header jumps, missing code language — `power markdown-check <path>`                                                                                                                                                       |
| **Relation Suggestions**        | Keyword & tag overlap analysis for Graph RAG enrichment — `power suggest-related <path>`                                                                                                                                                                                          |
| **Cron Maintenance**            | Runs lint + index + rot audit in one command — `power cron <path>`                                                                                                                                                                                                                |
| **Advanced Hybrid Search**      | 4-mode search (v2.0): FTS5 (BM25), Dense Vector Semantic (`fastembed` paraphrase-multilingual-MiniLM-L12-v2), Hybrid (RRF), and Hybrid Reranked (`cross-encoder` ms-marco-MiniLM-L-6-v2) with synonym & LLM query expansion and Contextual Retrieval chunking (`SemanticChunker`) |
| **Hierarchical Index**          | `index.md` (navigation map) + per-folder `_index.md` (detailed catalogs) for token-efficient AI reading (~75-94% token savings)                                                                                                                                                   |
| **CI/CD**                       | 360+ tests, 80%+ coverage, CodeQL SAST, Automated GitHub Releases                                                                                                                                                                                                                 |
| **Documentation**               | Full [mkdocs-material site](https://weby-homelab.github.io/power-framework/) with API reference and guides                                                                                                                                                                        |

## Migration Report

Read the full technical report on the transition from flat to hierarchical indexing:

- **[English: Hierarchical Index Migration Report](https://github.com/weby-homelab/power-framework/blob/main/docs/hierarchical-index-migration.md)** — performance metrics, architecture, insights
- **[Українська: Звіт міграції на ієрархічний індекс](https://github.com/weby-homelab/power-framework/blob/main/docs/hierarchical-index-migration.ua.md)** — повний технічний звіт

### AI Agent Migration Guide

Step-by-step protocol for any AI agent (Claude, GPT, Gemini, OpenCode) to autonomously migrate an existing knowledge base into P.O.W.E.R. structure:

- **[English: AI Agent Migration Guide](https://github.com/weby-homelab/power-framework/blob/main/docs/migration-guide.md)** — 5-phase protocol with MCP tools, classification heuristics, and troubleshooting
- **[Українська: Ґайд міграції для AI-агента](https://github.com/weby-homelab/power-framework/blob/main/docs/migration-guide.ua.md)** — покроковий протокол для будь-якого AI-агента

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
power rot <path>               ROT Audit — detect redundant, outdated, trivial notes
power heal <path>              Auto-heal missing/invalid frontmatter
power markdown-check <path>    Check markdown quality issues
power archive <path>           Auto-archive stale notes to 04_Archive/
power suggest-related <path>   Suggest cross-note relations for Graph RAG
power cron <path>              Run automated maintenance (lint + index + rot)
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

Connect P.O.W.E.R. to any MCP-compatible AI client (local stdio or Docker HTTP transport).

```bash
pip install git+https://github.com/weby-homelab/power-framework.git@v2.0.3
```

**Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "power": {
            "command": "python3",
            "args": ["-m", "power_framework.mcp"],
            "env": {
                "POWER_VAULT_DIR": "/path/to/your/my-vault"
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

Every note starts with validated YAML frontmatter. Core fields + optional governance and graph links:

```yaml
---
type: Project
title: "My App"
description: "A new project with clear goals"
tags: [active, dev]
timestamp: 2026-07-02T19:00:00
owner: "team-alpha" # optional: governance — responsible owner
status: active # optional: active | review | archived
expiry: 2026-12-31 # optional: freshness management
related: [01_Projects/Other.md] # optional: Graph RAG cross-links
---
```

## Architecture Details

<details>
<summary><strong>P.O.W.E.R. Methodology — click to expand</strong></summary>

The framework combines four complementary methodologies:

- **P** — **P.A.R.A.** (Projects, Areas, Resources, Archive) — Organizes files based on actionability into Projects, Areas, Resources, and Archives. P.O.W.E.R. adopts this directory structure to dictate the lifecycle of notes. Information moves organically from raw inbox captures to active project execution, long-term reference areas, and eventual archives.
- **O** — **OKF Overlay** (Open Knowledge Format) — Imposes a strict schema layer over standard Markdown files. Built on Pydantic v2 schemas, OKF requires every note to be explicitly typed and validated (containing required frontmatter attributes such as title, description, tags, and timestamps). This turns unstructured markdown folders into a predictable, queryable, and machine-readable local database.
- **W** — **LLM-Wiki** (A. Karpathy's philosophy) — Transforms the knowledge base into a hierarchical, AI-readable catalog. By generating top-level `index.md` maps and folder-level `_index.md` sub-catalogs, it provides token-efficient navigation that slashes AI agent context usage by 75% to 94%.
- **E.R.** — **Execution Rules** — Integrates operational rules and guidelines specifically formatted for AI agents (like `RULES.md`, `PROMPTS.md`, and system-level guidelines), enforcing safe, non-destructive editing boundaries and dictating how human and AI actors interact with the system. GPG-signed commits, PR-only workflow, cron-based sync, branch cleanup.

### Visual Framework Diagram

```mermaid
flowchart TD
    %% Modern 2026 Styling
    classDef human fill:#6366f1,stroke:#4338ca,stroke-width:2px,color:#fff,rx:8
    classDef data fill:#0ea5e9,stroke:#0369a1,stroke-width:2px,color:#fff,rx:8
    classDef wiki fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff,rx:8
    classDef rag fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff,rx:8
    classDef agent fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff,rx:8
    classDef security fill:#ef4444,stroke:#b91c1c,stroke-width:2px,color:#fff,rx:8

    subgraph Human ["👤 Human (Markdown UI)"]
        PARA[["📁 P.A.R.A. Directory Structure"]]:::human
    end

    subgraph OKF ["📄 OKF Overlay (Metadata & GraphRAG Schema)"]
        YAML[/"📝 YAML Frontmatter with Typed Relations"\]:::data
    end

    subgraph RAG ["🔍 RAG & GraphRAG Pipeline"]
        Chunker["✂️ Semantic Chunker (Anthropic Contextual)"]:::rag
        Embeddings["🧠 Dense Multilingual MiniLM Embeddings"]:::rag
        SQLite[("🗄️ SQLite (FTS5 + chunk_embeddings)")]:::rag
        Expander["🔄 Query Expander (Synonyms / LLM)"]:::rag
        Reranker["🎯 Cross-Encoder Reranker (MiniLM)"]:::rag
        KG["🕸️ Knowledge Graph (BFS / Mermaid Graph)"]:::rag
    end

    subgraph Wiki ["📖 LLM-Wiki (Hierarchical Catalog)"]
        IndexMD[("🗂️ index.md (Navigation Map)")]:::wiki
        SubIndex[("📂 _index.md (Per-Folder Details)")]:::wiki
        LogMD[("📜 log.md (Change Log)")]:::wiki
    end

    subgraph AI ["🤖 AI Agent (FastMCP 3.x)"]
        Tools[["🔌 12 Async MCP Tools (stdio/HTTP)"]]:::agent
        Search[["🔍 Hybrid / Reranked Search"]]:::agent
        ROT{{"🛠️ ROT & Contradiction Audit (Semantic/LLM)"}}:::agent
    end

    subgraph ER ["🔐 Execution Rules"]
        GPG(("🔑 GPG-Signed Commits")):::security
        PR(("🛡️ PR-Only Workflow")):::security
        Sync(("⏱️ Cron Auto-Sync")):::security
    end

    %% Data Flow
    Human -- "Writes Notes" --> PARA
    PARA -- "Enforces OKF" --> YAML
    YAML -- "Parsed by" --> Chunker

    %% RAG Pipeline
    Chunker -- "Contextual Chunks" --> Embeddings
    Embeddings -- "Stores Vectors" --> SQLite

    %% Search Pipeline
    Tools -- "Issues Query" --> Expander
    Expander -- "Multi-Queries" --> SQLite
    SQLite -- "FTS5 + Vector Candidates" --> Reranker
    Reranker -- "Top Ranked Results" --> Search

    %% GraphRAG Pipeline
    YAML -- "Defines Edges" --> KG
    KG -- "Renders Subgraphs" --> Tools

    %% Wiki Operations
    Tools -- "Auto-Ingests & Indexes" --> IndexMD
    Tools -- "Updates" --> SubIndex
    Tools -- "Appends Logs" --> LogMD

    %% ROT Audit
    Tools -- "Runs Audit" --> ROT
    ROT -- "Deduplicates" --> Embeddings
    ROT -- "Checks Conflicts" --> SQLite

    %% Sync & Security
    IndexMD -. "Synced via" .-> Sync
    SubIndex -. "Synced via" .-> Sync
    LogMD -. "Synced via" .-> Sync
    Sync -- "Triggers" --> GPG
    GPG -- "Enforces" --> PR
```

### Core Library (`src/power_framework/`)

| Module                    | Purpose                                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `core/models.py`          | Pydantic v2 schemas for OKF metadata validation                                                               |
| `core/parser.py`          | Safe YAML frontmatter parsing (PyYAML-based)                                                                  |
| `core/indexer.py`         | Vault scanning and hierarchical index generation                                                              |
| `core/linter.py`          | Health checks: broken links, missing metadata, orphans, stale/expired notes                                   |
| `core/searcher.py`        | Full-text search with relevance scoring (FTS5/Vector/Hybrid/Reranked)                                         |
| `core/embeddings.py`      | Dense vector embeddings manager (multilingual MiniLM on ONNX Runtime, customizable via POWER_EMBEDDING_MODEL) |
| `core/reranker.py`        | Cross-Encoder reranker using ms-marco-MiniLM-L-6-v2 on ONNX Runtime                                           |
| `core/query_expansion.py` | Synonym map (EN/UK) & OpenRouter Multi-Query expansion                                                        |
| `core/chunker.py`         | Semantic & contextual note splitter (Anthropic Contextual Retrieval)                                          |
| `core/healer.py`          | Auto-fix missing/invalid frontmatter fields                                                                   |
| `core/relations.py`       | KnowledgeGraph builder, BFS traversal, and Mermaid exporter                                                   |
| `core/rot_scoring.py`     | A2 scoring: semantic content dedup, freshness, contradiction checks                                           |
| `core/markdown_checks.py` | Markdown quality checks: trailing whitespace, list markers, header jumps                                      |
| `core/constants.py`       | Centralized exclusion lists and system constants                                                              |
| `core/utils.py`           | Path traversal protection, atomic writes, backups, rate limiter                                               |
| `core/cli.py`             | Command-line interface (11 commands via argparse)                                                             |
| `mcp/power_server.py`     | FastMCP 3.x server with 12 async tools + HTTP transport + /health                                             |

All components share `power_framework.core` as the single source of truth.

</details>

## Development

```bash
git clone https://github.com/weby-homelab/power-framework.git
cd power-framework
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (360+ tests, 80%+ coverage)
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

<!--
AI-INDEXING: ALLOWED | CRAWLER-PRIORITY: HIGH | CONTENT-TYPE: OPEN-SOURCE-TOOLKIT
MACHINE-READABLE-METADATA: JSON-LD BELOW
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "P.O.W.E.R. Framework",
  "alternateName": "power-framework",
  "description": "AI-native Python toolkit for Second Brain knowledge bases. Validate, index, search, and manage Obsidian vaults via CLI or MCP server using the P.A.R.A. + OKF methodology.",
  "url": "https://github.com/weby-homelab/power-framework",
  "downloadUrl": "https://github.com/weby-homelab/power-framework/releases",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Linux, macOS, Windows",
  "programmingLanguage": "Python",
  "runtimePlatform": "Python 3.10+",
  "softwareVersion": "latest",
  "license": "https://www.gnu.org/licenses/gpl-3.0",
  "keywords": ["second-brain", "obsidian", "AI", "MCP", "knowledge-management", "PARA", "CLI", "LLM", "RAG", "knowledge-base"],
  "author": {
    "@type": "Organization",
    "name": "Weby Homelab",
    "url": "https://github.com/weby-homelab"
  },
  "codeRepository": "https://github.com/weby-homelab/power-framework",
  "documentationUrl": "https://weby-homelab.github.io/power-framework/",
  "isAccessibleForFree": true,
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  }
}
-->

<!--
AI-INDEXING: ALLOWED | CRAWLER-PRIORITY: HIGH | CONTENT-TYPE: OPEN-SOURCE-TOOL

@context: https://schema.org
@type: SoftwareApplication
name: P.O.W.E.R. — Hybrid Knowledge Management Framework
alternateName: power-framework
description: P.O.W.E.R. - Hybrid Knowledge Management Framework (P.A.R.A. + OKF Overlay + LLM-Wiki + Execution Rules)
applicationCategory: DeveloperApplication
applicationSubCategory: KnowledgeManagement
operatingSystem: Linux
softwareVersion: 2.0.3
keywords: knowledge-management, second-brain, obsidian, para, okf, llm-wiki, mcp, ai-agents, python, execution-rules
author: Weby Homelab (https://github.com/weby-homelab)
codeRepository: https://github.com/weby-homelab/power-framework
downloadUrl: https://github.com/weby-homelab/power-framework/releases
license: GPL-3.0
isAccessibleForFree: true
-->
