# About P.O.W.E.R. - Hybrid Knowledge Management Framework (P.A.R.A. + OKF Overlay + LLM-Wiki + Execution Rules)

P.O.W.E.R. is a hybrid system built to bridge the gap between human workflows, automated scripts, and LLM-based autonomous agents. The name is an acronym representing its core components: P.A.R.A., OKF, Wiki, and Execution Rules. It integrates these distinct architectural frameworks to construct a coherent, self-validating, and token-efficient Second Brain:

P.A.R.A. Method (Tiago Forte) — Organizes files based on actionability into Projects, Areas, Resources, and Archives. P.O.W.E.R. adopts this directory structure to dictate the lifecycle of notes. Information moves organically from raw inbox captures to active project execution, long-term reference areas, and eventual archives.
OKF (Open Knowledge Format) Overlay — Imposes a strict schema layer over standard Markdown files. Built on Pydantic v2 schemas, OKF requires every note to be explicitly typed and validated (containing required frontmatter attributes such as title, description, tags, and timestamps). This turns unstructured markdown folders into a predictable, queryable, and machine-readable local database.
LLM-Wiki & Execution Rules — Integrates operational rules and guidelines specifically formatted for AI agents (like RULES.md, PROMPTS.md, and system-level guidelines). By coupling these rules with Hierarchical Indexing (generating top-level index.md maps and folder-level _index.md sub-catalogs), it slashes AI agent context usage by 75% to 94% and enforces safe, non-destructive editing boundaries.

## Why P.O.W.E.R.?

Unlike generic knowledge management tools, P.O.W.E.R. is designed from the ground up for AI-first knowledge management:

- **AI-native metadata** — Pydantic v2 schemas enforce strict OKF frontmatter, so every note is machine-readable; includes governance fields (`owner`, `status`, `expiry`) and Graph RAG links (`related`)
- **Token-efficient indexing** — hierarchical `index.md` + per-folder `_index.md` cuts AI agent context usage by ~75%
- **Knowledge Graph** — `related` field connects notes across the vault; visualized in sub-indexes for Graph RAG workflows
- **Freshness Monitoring** — linter detects stale/expired notes based on `expiry` metadata field; A2 scoring adds type-based exponential decay freshness
- **Content Deduplication** — TF-Vector cosine similarity detects near-duplicate notes without external embeddings
- **Link Rot Detection** — HTTP HEAD checks for broken external links
- **Frontmatter Healer** — auto-fills missing title, description, type, and timestamp across the vault
- **Markdown Quality Checks** — detects trailing whitespace, inconsistent list markers, header jumps, missing code language
- **Agent Auto-Ingest** — `synthesize_session` MCP tool lets agents autonomously create permanent knowledge artifacts with governance + graph links + full catalog maintenance
- **MCP-native** — 11 tools exposed to any MCP-compatible AI client (Claude, OpenCode, Cursor) with zero glue code
- **Production-grade** — 270 tests, 81%+ coverage, CodeQL scanning, OIDC-signed GitHub Releases

## Features

- **`power init`** — Scaffold an OKF-compliant vault directory structure
- **`power lint`** — Health-check metadata, broken links, orphans, stale/expired notes
- **`power index`** — Compile hierarchical indexes (`index.md` + per-folder `_index.md`)
- **`power ingest`** — Create new notes with validated frontmatter (supports `owner`, `status`, `expiry`, `related`)
- **`power search`** — Full-text vault search with relevance scoring
- **`power rot`** — ROT Audit: detect redundant, outdated, trivial notes; `--extended` for A2 scoring
- **`power archive`** — Auto-archive stale notes to `04_Archive/`
- **`power heal`** — Auto-fill missing frontmatter fields (title, description, type, timestamp)
- **`power markdown-check`** — Detect trailing whitespace, inconsistent list markers, header jumps, missing code language
- **`power suggest-related`** — Suggest cross-note relations for Graph RAG enrichment
- **`power cron`** — Run automated maintenance (lint + index + rot audit)
- **MCP Server** — 11 tools (`lint_vault`, `generate_index`, `read_sub_index`, `ingest_note`, `search_vault_tool`, `synthesize_session`, `rot_audit`, `archive_notes`, `suggest_related_tool`, `heal_frontmatter_tool`, `check_markdown_tool`)
- **Knowledge Graph** — `related` field for explicit cross-note graph links
- **Governance** — `owner`, `status`, `expiry` fields tracked in sub-indexes

## Quick start

```bash
pip install power-framework
power init my-vault
power lint
power index
```

## License

GPLv3 — Built in Ukraine ⚡
