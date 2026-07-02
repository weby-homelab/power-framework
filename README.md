<p align="center">
  <b>ENG</b> | <a href="README.ua.md">UKR</a>
</p>

# 🚀 P.O.W.E.R. Framework — Hybrid Knowledge Management System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Format: GFM](https://img.shields.io/badge/Format-GFM-blue.svg)](https://github.github.com/gfm/)

A hybrid knowledge management system (Obsidian Second Brain) that bridges human-friendly directory organization with strict machine-readability for AI agents.

Built on the synergy of **P.A.R.A.** + **OKF Overlay** + **LLM-Wiki** + **Execution Rules**.

---

## 🎯 System Architecture (P.O.W.E.R.)

The framework consists of four complementary methodologies:

*   **P** — **P.A.R.A.** (Projects, Areas, Resources, Archive) — a logical folder structure optimized for human cognitive layout.
*   **O** — **OKF Overlay** (Open Knowledge Format) — metadata (YAML frontmatter) at the top of every file to enable instant AI parsing.
*   **W** — **LLM-Wiki** (A. Karpathy's philosophy) — automated catalog indexing, chronological log, and structural link linting.
*   **E.R.** — **Execution Rules / Enforced Routines** (custom automation rules) — GPG-signed commits, PR-only workflow, cron-based 5-minute sync, and branch cleanup policies.

### 📊 Visual Framework Diagram

```mermaid
graph TB
    subgraph Human ["👤 Human (Obsidian UI)"]
        PARA["P.A.R.A. Directory Structure"]
        PARA_P["01_Projects"]
        PARA_A["02_Areas"]
        PARA_R["03_Resources"]
        PARA_AR["04_Archive"]
        PARA --> PARA_P
        PARA --> PARA_A
        PARA --> PARA_R
        PARA --> PARA_AR
    end

    subgraph AI ["🤖 AI Agent (OpenCode / Antigravity)"]
        Ingest["Ingest Note"]
        Lint["Lint Vault (lint_brain.py)"]
        Index["Rebuild Index (generate_index.py)"]
    end

    subgraph OKF ["📄 OKF Overlay (Metadata Schema)"]
        YAML["YAML Frontmatter"]
        IndexMD["index.md (Catalog)"]
        LogMD["log.md (Change Log)"]
    end

    subgraph ER ["🔐 Execution Rules & Enforced Routines"]
        GPG["GPG Signature (Verified Commit)"]
        PR["PR-Only Workflow (GitHub)"]
        Sync["Cron Autosync (sync-brain.sh)"]
        Clean["Branch Cleanup (cleanup_branches.py)"]
    end

    Human -- Writes Notes --> YAML
    YAML -- Parsed by --> AI
    AI -- Updates --> IndexMD
    AI -- Appends --> LogMD
    AI -- Runs Checks --> Lint
    
    IndexMD -- Synchronized via --> Sync
    LogMD -- Synchronized via --> Sync
    
    Sync -- Requires --> GPG
    Sync -- Follows --> PR
    PR -- Triggers --> Clean
    
    classDef human fill:#1A365D,stroke:#3182CE,stroke-width:2px,color:#FFF;
    classDef ai fill:#2C3E50,stroke:#E74C3C,stroke-width:2px,color:#FFF;
    classDef okf fill:#1B4D3E,stroke:#2ECC71,stroke-width:2px,color:#FFF;
    classDef er fill:#5D3F6A,stroke:#BB8FCE,stroke-width:2px,color:#FFF;
    
    class PARA,PARA_P,PARA_A,PARA_R,PARA_AR human;
    class Ingest,Lint,Index ai;
    class YAML,IndexMD,LogMD okf;
    class GPG,PR,Sync,Clean er;
```

---

## 📂 Vault Directory Structure

The knowledge base is organized in the repository as follows:

```text
/brain
├── 00_Inbox/                    # Temporary folder for quick scratchnotes and raw inputs
├── 01_Projects/                 # Active projects with specific deadlines and targets
├── 02_Areas/                    # Long-term responsibilities (infrastructure, finance, health)
├── 03_Resources/                # General resources (guides, stack, snippets, scripts)
│   └── lint_brain.py            # Automated link validation and cleanup script
├── 04_Archive/                  # Completed projects and stale/outdated notes
├── 05_Templates/                # Templates with predefined OKF metadata blocks
├── 06_Daily_Logs/               # Chronological daily logs and lessons (MASTER-LESSONS-LEARNED)
├── PROTOCOLS/                   # System configurations and specifications for AI agents
│   └── LLM_WIKI_SCHEMA.md       # Formatting and linting standards for AI operations
├── index.md                     # Automatically generated catalog index of all notes
└── log.md                       # Chronological append-only change log of the vault
```

---

## 📄 Metadata Specification (OKF)

Every note must contain a strict YAML block (frontmatter) at the very top of the file. This allows AI agents to instantly index and filter documents:

```yaml
---
type: Project | Area | Resource | Daily Log | Archive | System Guide  # Note category
title: "Document Title"                                                # Human-friendly title
description: "Single-line summary (up to 150 chars) for the catalog"  # Short description
resource: "https://github.com/..."                                    # External source code (if any)
tags: [active, guide]                                                 # Obsidian tags
timestamp: YYYY-MM-DDTHH:MM:SS+TZ                                      # Last modified date
---
```

---

## 🤖 Health Linting Process

The `lint_brain.py` script is used to perform on-demand or automated vault checks.

### Features:
1.  **Broken Links**: Finds internal wikilinks `[[Note]]` and GFM markdown links `[Title](Path.md)` that point to non-existent files.
2.  **Metadata Validation**: Identifies notes with missing YAML frontmatter or missing required `type` field.
3.  **Orphan Check**: Reports notes that have no inbound links (excluding core files).

---

## 🔐 Security & Automation (E.R.)

1.  **Zero-Secrets**: No passwords, API keys, or private IP addresses in the repository. All credentials live in a local `.env` file on the host (added to `.gitignore`).
2.  **Verified Commits (GPG)**: All commits must be signed with the developer's GPG key to verify the committer identity in public repositories.
3.  **PR-only Workflow**: Direct pushes to `main` are disabled. All updates are pushed to `feature/*` branches and merged via Pull Requests.
4.  **Auto-Sync Cron**: A server cron job runs every 5 minutes, automatically committing and pushing vault changes to GitHub.

---

## 📄 License

This framework is distributed under the MIT License. Feel free to use it to build your own personal or enterprise knowledge bases.
