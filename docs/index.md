# About P.O.W.E.R. - Hybrid Knowledge Management Framework (P.A.R.A. + OKF Overlay + LLM-Wiki + Execution Rules)

P.O.W.E.R. is a hybrid system built to bridge the gap between human workflows, automated scripts, and LLM-based autonomous agents. The name is an acronym representing its core components: P.A.R.A., OKF, Wiki, and Execution Rules. It integrates these distinct architectural frameworks to construct a coherent, self-validating, and token-efficient Second Brain.

## Why P.O.W.E.R.?

Unlike generic knowledge management tools, P.O.W.E.R. is designed from the ground up for AI-first knowledge management:

- **AI-native metadata** — Pydantic v2 schemas enforce strict OKF frontmatter, so every note is machine-readable; includes governance fields (`owner`, `status`, `expiry`) and Graph RAG links (`related`)
- **Token-efficient indexing** — hierarchical `index.md` + per-folder `_index.md` cuts AI agent context usage by ~75%
- **Knowledge Graph** — `related` field connects notes across the vault; visualized in sub-indexes for Graph RAG workflows
- **Freshness Monitoring** — linter detects stale/expired notes based on `expiry` metadata field; A2 scoring adds type-based exponential decay freshness
- **Content Deduplication** — TF-Vector cosine similarity detects near-duplicate notes without external embeddings
- **Link Rot Detection** — HTTP HEAD checks for broken external links (SSRF-protected)
- **Frontmatter Healer** — auto-fills missing title, description, type, and timestamp across the vault
- **Markdown Quality Checks** — detects trailing whitespace, inconsistent list markers, header jumps, missing code language
- **Agent Auto-Ingest** — `synthesize_session` MCP tool lets agents autonomously create permanent knowledge artifacts with governance + graph links + full catalog maintenance
- **MCP-native** — all 12 tools exposed to any MCP-compatible AI client (Claude, OpenCode, Cursor), powered by FastMCP 3.x
- **Production-grade** — 270 tests, 81%+ coverage, CodeQL scanning, Automated GitHub Releases

## Features

- **`power init`** — Scaffold an OKF-compliant vault directory structure
- **`power lint`** — Health-check metadata, broken links, orphans, stale/expired notes
- **`power index`** — Compile hierarchical indexes (`index.md` + per-folder `_index.md`)
- **`power ingest`** — Create new notes with validated frontmatter (supports `owner`, `status`, `expiry`, `related`)
- **`power search`** — Full-text vault search with relevance scoring (FTS5/Vector/Hybrid)
- **`power rot`** — ROT Audit: detect redundant, outdated, trivial notes; `--extended` for A2 scoring
- **`power archive`** — Auto-archive stale notes to `04_Archive/` with dry-run preview
- **`power heal`** — Auto-fill missing frontmatter fields (title, description, type, timestamp)
- **`power markdown-check`** — Detect trailing whitespace, inconsistent list markers, header jumps, missing code language
- **`power suggest-related`** — Suggest cross-note relations for Graph RAG enrichment
- **`power cron`** — Run automated maintenance (lint + index + rot audit)
- **MCP Server** — 12 tools (`lint_vault`, `generate_index`, `read_sub_index`, `ensure_sub_index`, `ingest_note`, `search_vault_tool`, `synthesize_session`, `rot_audit`, `archive_notes`, `suggest_related_tool`, `heal_frontmatter_tool`, `check_markdown_tool`)
- **Knowledge Graph** — `related` field for explicit cross-note graph links
- **Governance** — `owner`, `status`, `expiry` fields tracked in sub-indexes

## Quick start

```bash
pip install git+https://github.com/weby-homelab/power-framework.git@v2.0.1

power init ~/my-vault
power lint ~/my-vault
power index ~/my-vault
```

## License

GPLv3 — Built in Ukraine ⚡
