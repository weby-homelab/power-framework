---
name: power
version: 3.2.1
description: Maintains and validates the P.O.W.E.R. knowledge base (P.A.R.A. + OKF v0.1 + Graph RAG + LLM-Wiki + Execution Rules).
---

# ⚡ P.O.W.E.R. Knowledge Management Skill

This skill automates the management, validation, and lifecycle maintenance of the Obsidian Second Brain knowledge base using the hybrid **P.O.W.E.R.** methodology.

## 🚀 Primary Use Cases

The skill is automatically activated by AI agents (Antigravity CLI and OpenCode) or manually by the user when performing the following tasks:

1.  **Ingest (Knowledge Import)** — adding or editing documents in the knowledge base.
2.  **Indexing (Re-indexing)** — updating the content and listing of concepts.
3.  **Linting (Health Check)** — finding broken links, metadata errors, or orphan pages.
4.  **ROT Audit** — detecting duplicate, outdated, and trivial notes.
5.  **Auto-Archive** — automatically archiving outdated notes to `04_Archive/`.
6.  **Relation Suggestions (Graph RAG v2)** — analyzing keyword, tag, and explicit link intersections for hybrid (vector + graph) Graph RAG search.
7.  **Cron Maintenance** — automatic execution of lint + index + rot audit.
8.  **Sync & Commit** — committing changes to Git according to host security rules.
9.  **Rename & Propagation** — renaming a file and automatically updating links.

---

## 🛠️ Available Tools (Scripts + CLI)

The skill contains automated scripts in the `scripts/` directory and a CLI:

### Scripts

1.  **`lint_brain.py`** — linter + ROT audit script (v3.2.1):

```bash
python3 .agents/skills/power/scripts/lint_brain.py
```

2.  **`generate_index.py`** — script for automatic hierarchical index generation:

```bash
python3 .agents/skills/power/scripts/generate_index.py
```

### CLI (power, 15 commands)

1. `power init <path>` — create vault structure
2. `power lint <path>` — validate metadata, links, orphans
3. `power index <path>` — generate hierarchical index
4. `power ingest <path>` — create note with OKF metadata
5. `power search <path> <query>` — full-text search
6. `power sync <path>` — build FTS and dense index
7. `power rot <path>` — ROT audit (duplicates, outdated, trivial)
8. `power archive <path>` — archive outdated notes
9. `power status <path>` — vault status dashboard
10. `power cron <path>` — automatic maintenance
11. `power heal <path>` — auto-fix frontmatter
12. `power markdown-check <path>` — check Markdown quality
13. `power suggest-related <path>` — Graph RAG link suggestions
14. `power synthesize <path>` — create session summary note
15. `power rename <path> --old <old_path> --new <new_path>` — rename note and update Graph RAG links

### MCP Tools (12) — FastMCP 3.x (v3.2.1)

- `lint_vault`, `generate_index`, `read_sub_index`, `ensure_sub_index`, `ingest_note`
- `search_vault_tool`, `synthesize_session`
- `rot_audit`, `archive_notes`, `suggest_related_tool`
- `heal_frontmatter_tool`, `check_markdown_tool`

### Configuration (v3.2.1)

- **Embedding model** — canonically `BAAI/bge-m3` (1024 dim) via direct ONNX Runtime. BGE-M3 natively supports **dense + sparse + ColBERT** in a single model, enabling hybrid search (RRF) without a separate BM25. The provider is switched via `POWER_EMBED_PROVIDER`; `fastembed`/MiniLM remains a light opt-in fallback.
- **Default reranker** — `onnx-community/bge-reranker-v2-m3-ONNX` (SHA-pinned, Apache-2.0, UA+EN). `jinaai/jina-reranker-v2-base-multilingual` (CC-BY-NC) remains explicit opt-in.
- **Resource controls:**
  - `POWER_EMBED_BATCH_SIZE` (default `8`) — limits peak RAM usage during sync/embedding. On `MemoryError`, batch size is automatically halved.
  - `POWER_EMBED_NUM_THREADS` (default `2`) — caps ONNX/OMP/OpenBLAS threads.
  - `POWER_EMBED_COMMIT_EVERY` (default `50`) — frequency of persisting vectors to SQLite to reduce disk I/O.
  - `POWER_SYNC_VMEM_LIMIT_MB` (default `0` = disabled) — optional virtual memory limit (RLIMIT_AS) for the sync process.
- **ROT audit (A2)** — parallel link checking via `ThreadPoolExecutor(max_workers=16)`.
- **MCP entry-point** — `/root/geminicli/.agents/mcp_servers/power_server.py` → `power_framework.mcp`

---

## 📖 Hierarchical Navigation Protocol (On-Demand Sub-Index Reading)

P.O.W.E.R. uses **hierarchical indexing** to optimize AI agent context:

```
vault/
├── index.md              # Navigation map (small, ~2KB)
├── 01_Projects/
│   └── _index.md         # Detailed entries for Projects
├── 02_Areas/
│   └── _index.md         # Detailed entries for Areas
├── 03_Resources/
│   └── _index.md         # Detailed entries for Resources
└── 06_Daily_Logs/
    └── _index.md         # Detailed entries for Daily Logs
```

### Step-by-Step Agent Navigation Rules:

1.  **Direct Reading / Search First:** If the path is known or a specific file is needed, read it directly or search using `grep_search`.
2.  **Use Indices Only if Unknown:** Read `index.md` or call `read_sub_index` (read `folder/_index.md`) only if the path is unknown and `grep_search` yields no results.
3.  **NEVER glob all `.md` files / list large folders:** Use `grep_search` instead of `list_dir` for large categories to preserve tokens.

### Token Efficiency Comparison:

| Approach                          | Token Cost | Context Quality       |
| --------------------------------- | ---------- | --------------------- |
| Read all `.md` files              | 🔴 ~50K+   | Full but wasteful     |
| Read only `index.md`              | 🟢 ~2K     | Insufficient          |
| `index.md` + relevant `_index.md` | 🟡 ~5-8K   | **Optimal balance**   |
| + specific notes                  | 🟡 ~10-15K | **Precise, targeted** |

---

## 📋 AI Agent Instructions (Step-by-Step Rules)

When working with the knowledge base in the vault workspace (Workspace/Vault Root), ALWAYS follow this chain of actions (PAV + P.O.W.E.R.):

### Step 1. Validate Metadata (OKF Frontmatter)

When creating or editing files, ensure the file starts with the correct frontmatter (OKF v0.1 — `type` is the only required field):

```yaml
---
type: Project | Area | Resource | Daily Log | Archive | System Guide
title: "Page title"
description: "One-line description for the catalog"
tags: [tag1, tag2]
timestamp: YYYY-MM-DDTHH:MM:SS+TZ
---
```

### Step 2. Automatic Hierarchical Index Generation

After adding/changing a file, run the index generation script. It will automatically update `index.md` and all `_index.md` files:

```bash
python3 .agents/skills/power/scripts/generate_index.py
```

### Step 3. Add Entry to Change Log

Record the completed action at the end of the `log.md` file in chronological format:

```markdown
## [YYYY-MM-DD] <operation_type> | <action_title>

- **Action:** Brief description of what was done
- **Result:** Which files were changed/created
```

### Step 4. Linter Validation (Lint check)

Run the linter script to check for new broken links or orphan pages:

```bash
python3 .agents/skills/power/scripts/lint_brain.py
```

_If the linter reports errors (e.g., broken links in Home.md), fix them immediately._

### Step 5. Git Commit & Push (Execution Rules)

- Commits are made **only in separate branches** `feature/*` or `fix/*`.
- Git is configured for GPG-signed commits using developer keys from the `.env` file.
- After push, a Pull Request is opened and merged.
- The `cleanup-branches` skill must be run to clean up merged branches.