---
type: Resource
title: "AI Agent Migration Guide: Migrate Any Obsidian Vault to P.O.W.E.R. (v2.0.2)"
description: "Step-by-step protocol for any LLM-based AI agent to autonomously migrate an Obsidian vault to P.O.W.E.R. OKF-compliant structure under v2.0.2."
tags: [power, migration, guide, ai-agents, mcp, multilingual-minilm, graphrag]
timestamp: 2026-07-15T02:00:00
---

# AI Agent Migration Guide: Migrate Any Obsidian Vault to P.O.W.E.R. (v2.0.2)

**Target audience:** AI agents (Claude, GPT, Gemini, OpenCode) with MCP access to P.O.W.E.R.

**Goal:** Transform any unstructured Obsidian vault into a P.O.W.E.R.-compliant knowledge base with validated OKF metadata, P.A.R.A. folder structure, and hierarchical indexes — fully autonomously.

---

## Overview

This protocol enables any LLM-based AI agent to migrate an existing Obsidian vault by combining:

- **MCP tools** — `ingest_note`, `lint_vault`, `generate_index`, `read_sub_index`, `search_vault_tool`
- **Filesystem access** — reading existing `.md` files, moving/cleaning up old files
- **LLM intelligence** — classifying notes into P.A.R.A. categories, extracting titles, generating descriptions

The agent follows 6 phases. Each phase has clear success criteria.

---

## Phase 1: Discovery

**Goal:** Understand the vault's current state.

### Steps

1. **Scan the vault directory** — list all `.md` files recursively, excluding `.git/`, `node_modules/`, `__pycache__/`, `.venv/`.

2. **Read each `.md` file** — capture full content. Note:
    - Does it already have YAML frontmatter?
    - Does it have `type`, `title`, `description` fields?
    - What is the current folder structure?

3. **Identify existing patterns** — look for:
    - Tags (`#tag` inline or in frontmatter `tags:`)
    - Wikilinks (`[[Note Name]]`)
    - Embedded files (`![[image.png]]`)
    - Folder names that hint at categories (e.g., "Projects", "Archives")

4. **Run `lint_vault(vault_path)`** — baseline health check. Record how many notes are missing metadata and broken links.

**Success criteria:** You have a complete inventory of all notes and their current state.

---

## Phase 2: Classification

**Goal:** Analyze each note and determine its P.A.R.A. category + OKF metadata.

### Rules

Every note must be assigned exactly one `type` from:

| Type           | P.A.R.A. Folder  | When to use                                     |
| -------------- | ---------------- | ----------------------------------------------- |
| `Project`      | `01_Projects/`   | Active work with a deadline or deliverable      |
| `Area`         | `02_Areas/`      | Ongoing responsibility without a fixed deadline |
| `Resource`     | `03_Resources/`  | Reference material, guides, external links      |
| `Archive`      | `04_Archive/`    | Completed or obsolete projects                  |
| `Daily Log`    | `06_Daily_Logs/` | Temporal entries, session logs, journals        |
| `System Guide` | `PROTOCOLS/`     | AI agent instructions, operational protocols    |

### For each note, extract:

1. **`title`** — the note's H1 heading or filename (1-200 chars)
2. **`description`** — one-line summary of what this note is about (1-150 chars)
3. **`type`** — the P.A.R.A. category (see table above)
4. **`tags`** — relevant keywords (optional, list of strings)
5. **`resource`** — if the note references an external URL (optional)
6. **`owner`** — owner or responsible developer/agent (optional)
7. **`status`** — status of the note: `active`, `review`, or `archived` (optional, defaults to `active`)
8. **`related`** — structured list of relationships to other files for GraphRAG (optional)

### Classification heuristics

- Use folder name as a hint: `old_projects/` → likely `Archive` or `Project`
- Use content analysis: if it reads like a journal → `Daily Log`; like reference → `Resource`
- Use internal links: if linked from multiple other notes → likely active → `Area` or `Project`
- When uncertain, default to `Resource`

**Success criteria:** Every note has a draft `(type, title, description, tags)` tuple ready.

---

## Phase 3: Migration

**Goal:** Create each note in the correct P.A.R.A. folder with validated OKF frontmatter.

### Step 3a: Prepare the vault skeleton (if needed)

If the vault doesn't already have P.A.R.A. folders, run:

```
power init /path/to/vault
```

Or have the agent create the folder structure manually:

```
00_Inbox/
01_Projects/
02_Areas/
03_Resources/
04_Archive/
05_Templates/
06_Daily_Logs/
PROTOCOLS/
```

### Step 3b: Ingest each note

For every classified note, call the MCP tool `ingest_note`:

```jsonc
{
    "name": "01_Projects/My-Project", // P.A.R.A. path + filename (no .md)
    "note_type": "Project", // From NoteType enum
    "title": "My Project", // Human title
    "description": "Building the next big thing", // 1-150 chars
    "content": "<full markdown body here>", // Original content
    "tags": ["active", "dev"], // Optional
    "resource": "https://github.com/...", // Optional
}
```

**Important rules:**

- `name` includes the P.A.R.A. folder prefix + the note's filename (underscores, no spaces)
- `note_type` must match the folder: `01_Projects/` → `type: Project`
- `content` is the **full original markdown body** — strip any old YAML frontmatter first
- The `ingest_note` tool automatically:
    - Validates all metadata via Pydantic v2
    - Writes the file with proper OKF frontmatter
    - Regenerates the hierarchical index
    - Appends an entry to `log.md`
    - Runs a lint check

### Step 3c: Batch efficiency

For large vaults (>50 notes), group ingests by category. Ingest all `Resource` notes first, then `Area`, then `Project`, etc. This keeps the index regenerations predictable.

**Success criteria:** All notes are recreated in P.A.R.A. folders with valid OKF frontmatter. Index is up to date.

---

## Phase 4: Verification

**Goal:** Confirm the vault is fully healthy.

### Steps

1. **Run `lint_vault(vault_path)`** — expect:

    ```
    ✅ OKF Metadata: 0 errors
    ✅ Internal Links: 0 broken
    ✅ Orphans: 0 (or expected daily logs)
    ```

2. **Spot-check a few files** — read 3-5 random notes to verify frontmatter is correct and content is intact.

3. **Test hierarchical indexing** — call `read_sub_index(category="01_Projects", vault_path=...)` and verify it returns a valid sub-index.

4. **Test search** — call `search_vault_tool(query="test", vault_path=...)` and verify results look correct.

**Success criteria:** Lint passes with zero errors. Spot checks pass.

---

## Phase 5: Cleanup (Optional)

**Goal:** Remove old, unstructured files once migration is verified.

### Steps

1. List remaining files outside P.A.R.A. folders
2. For each:
    - If it was successfully migrated (content now exists in a P.A.R.A. folder), delete it
    - If it wasn't migrated, investigate and classify it
3. After all deletions, run `generate_index(vault_path)` to refresh
4. Run final `lint_vault(vault_path)` to confirm

**⚠️ Warning:** Only delete files after **full verification**. Prefer moving to `04_Archive/` over deletion for safety.

---

## Phase 6: Post-Migration Self-Maintenance & Git Sync

**Goal:** Ensure the knowledge base remains healthy between AI agent sessions, and synchronize the changes with a remote repository.

---

### Step 6a: Installing and Configuring P.O.W.E.R. Framework (v2.0.2)

For autonomous operation on the target host, install the P.O.W.E.R. toolkit (v2.0.2) globally or in the project's virtual environment:

```bash
pip install git+https://github.com/weby-homelab/power-framework.git
```

#### 🧠 Embedding Model Configuration (v2.0.2 Update)

Starting with version 2.0.2, the default embedding model has been switched to **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (embedding dimension **384**), reducing RAM usage from ~6.3 GB to ~680 MB. This prevents OOM crashes on resource-constrained hosts (e.g. 12GB RAM VPS, Proxmox LXC containers).

To customize the model, set the `POWER_EMBEDDING_MODEL` environment variable (loaded automatically from `.env`). For example, to use the heavier bilingual model on a host with sufficient memory:

```bash
export POWER_EMBEDDING_MODEL=BAAI/bge-m3
```

When using `BAAI/bge-m3` or other custom ONNX models, set the following to avoid `External data path escapes model directory` errors:

```bash
export HF_HUB_DISABLE_SYMLINKS=1
```

Configure the MCP server integration in your AI agent client or IDE configuration file (e.g., `cline_config.json`, `opencode.jsonc`, Cursor/Windsurf settings, etc.).

Configure LLM endpoints (`POWER_LLM_*`) for automated audits, query expansion, and metadata healing. Use the direct `"opencode"` base option for local OpenCode CLI offloading:

```json
"mcpServers": {
  "power": {
    "command": "python",
    "args": ["-m", "power_framework.mcp"],
    "env": {
      "POWER_VAULT_PATH": "/absolute/path/to/your/second-brain",
      "POWER_LLM_API_BASE": "http://localhost:8080/v1", // Set to "opencode" to run local CLI directly
      "POWER_LLM_API_KEY": "local",
      "POWER_LLM_MODEL": "opencode/deepseek-v4-flash-free"
    },
    "enabled": true
  }
}
```

This grants your agent access to validation (`lint_vault`), automated indexing (`generate_index`, `read_sub_index`), and search (`search_vault_tool`).

---

### Step 6b: Context Optimization (Ignore Files)

To prevent cluttering the AI agent's context with redundant files (binary assets, caches, Git directory logs), create an ignore configuration file (e.g., `.geminiignore`, `.cursorignore`, or `.gitignore` depending on your IDE) in the workspace root:

```
.git/
.gitignore
.geminiignore
.cursorignore
__pycache__/
*.pyc
.venv/
venv/
node_modules/
*.db
*.key
*.pem
*.crt
*.log
```

---

### Step 6c: Configure AI Agent Instructions and Rules

Provide project rules and context to your agent using system rule files (e.g., `.clinerules`, `.cursorrules`, `.windsurfrules`) or an instructions array in the agent's client configuration.
Recommended instruction file structure:

- **`RULES.md` / `INSTRUCTIONS.md`** — General agent behavior and guidelines.
- **`MASTER-LESSONS-LEARNED.md`** — A log of lessons learned and edge-cases to prevent repeat errors.
- **`power/SKILL.md`** — Guidelines for adhering to the P.A.R.A. methodology.

---

### Step 6d: Fixing Internal Wikilinks

Since files are moved into P.A.R.A. folders (`01_Projects/`, `02_Areas/`, etc.), old direct wikilinks become broken. The AI agent must verify and update references like `[[Note Name]]` to the relative path format `[[P.A.R.A. folder/Note Name|Alias]]`.
The P.O.W.E.R. Linter automatically checks for broken links, and corrections can be made using a link repair script or code editing tools.

---

### Step 6e: Automating Index Updates (`_index.md`)

The `_index.md` file in each P.A.R.A. folder serves as a navigation map and is generated automatically using the `power index` command.
_Agent Rule:_ After any change to the note structure (adding, moving, or deleting files), always regenerate the indexes using the MCP tool `generate_index` or the CLI `power index`.

---

### Step 6f: Excluding System Folders

Ensure that the vault validator and indexer ignore system and configuration directories (e.g., `.git/`, `.obsidian/`) to prevent false alarms about missing metadata or broken links in temp files.

---

### Step 6g: Daily Maintenance Protocol

Each session working with the vault should conclude with a maintenance cycle:

1. **Save session log** — Create a note in `06_Daily_Logs/` (type: `Daily Log`) describing the work done.
2. **Rebuild index** — Run `power index` to update `index.md` and `_index.md`.
3. **Log the change** — Add a brief entry to the central `log.md`.
4. **Validate status (Lint)** — Run `power lint` to confirm no regressions are present.

---

### Step 6h: Cross-Session Continuity Checklist

Before beginning a new work session, the AI agent should:

1. Read the general project rules and system instructions.
2. Read the `MASTER-LESSONS-LEARNED.md` error log.
3. Run `power lint` to check the current health of the database.
4. Read the index `index.md` and the change log `log.md`.

---

### Step 6i: Git Sync & Publication

Set up a synchronization pipeline to preserve history and enable collaboration:

1. **Committer Identity**: Configure Git's `user.name` and `user.email` to match your developer profile. Avoid committing as system users like `root`.
2. **Security Configurations**: Add confidential files (keys, passwords, `.env`, temporary export files) to `.gitignore`.
3. **GPG Signing (If Required)**: Enable GPG-signed commits (`commit.gpgsign=true`) using your personal GPG key.
4. **Git Workflow (PR Workflow)**:
    - Perform work on dedicated feature branches (`feature/*`).
    - Merge changes into the main branch via a Pull Request after all local checks and CI/CD validation builds pass.

---

### Step 6j: Multi-Mode Search (FTS + Vector + Hybrid + Semantic)

The P.O.W.E.R. framework (v2.0.2) includes a built-in search engine supporting five distinct strategies:

| Mode              | Description                                                                                              | Best for                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `fts` (default)   | SQLite FTS5 with weighted BM25 scoring                                                                   | Exact keyword & phrase matching             |
| `vector`          | TF-vector cosine similarity (pure Python, zero deps)                                                     | Lexical similarity comparison               |
| `hybrid`          | RRF (Reciprocal Rank Fusion) merge of FTS + Vector                                                       | Balanced lexical recall                     |
| `semantic`        | Dense embedding cosine similarity (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` on CPU) | Lightweight multilingual semantic discovery |
| `hybrid_reranked` | RRF merge of FTS + Vector with Cross-Encoder reranking                                                   | Highest-precision contextual ranking        |

_Search Guidelines for AI Agents:_

1. **Token Efficiency**: Use `search_vault_tool(query, max_results=20, search_mode="semantic")` (or `"hybrid"`) instead of listing files. This saves up to 95%+ of context tokens.
2. **Mode Selection**:
    - **FTS** — for precise keyword match: `search_vault_tool(query='"Docker Compose"')`
    - **Semantic** — for bilingual and conceptual searches: `search_vault_tool(query="оркестрація контейнерів", search_mode="semantic")`
    - **Hybrid Reranked** — for advanced cross-lingual ranking: `search_vault_tool(query="server deployment", search_mode="hybrid_reranked")`
3. **CLI Usage**: `power search /vault "query" --mode semantic`
4. **Query Syntax**:
    - **Phrase Search**: Use double quotes for exact phrases, e.g., `search_vault_tool(query='"Docker Compose"')`
    - **Prefix Matching**: Words are automatically matched using prefix wildcards (e.g., `dock*` matches `docker`, `docking`, etc.)
    - **Sanitization**: Avoid passing special search query operators (except double quotes) as they can cause syntax errors in SQLite FTS5.
5. **Git Hygiene**: The database file `.power_search.db` is ignored via `*.db` in `.gitignore` and `.geminiignore`. Under no circumstances should this file be committed to the repository.

---

### Step 6k: Typed Relationships for GraphRAG

For semantic indexing, the framework supports typed graph relationships inside the `related` block of OKF metadata:

- **`extends`** — Current note extends another note's concept.
- **`depends_on`** — Current note depends on another note/infrastructure.
- **`governed_by`** — Current note is governed by another protocol/rules.
- **`contradicts`** — Current note contradicts details in another note (helps linter/ROT audit detect stale data).
- **`part_of`** — Current note is a sub-module of a larger system.

Example format:

```yaml
related:
    - path: "02_Areas/Infra_Security.md"
      relation: "depends_on"
      confidence: 0.95
```

---

### Step 6l: ROT Audits & Auto-Healing

The framework includes tools to clean up redundant, outdated, and trivial (ROT) notes, and to automatically repair metadata:

- **`power rot /path/to/vault`** — Detects duplicate notes using dense embedding similarity and checks for logical contradictions using the LLM.
- **`power heal /path/to/vault`** — Automatically fixes markdown formatting issues and calls the LLM to generate missing `description` or `tags` based on document content.

---

## Example: Full Migration Transcript

Here is what a complete migration looks like from the agent's perspective:

```
Agent: Scanning vault at /Users/alice/obsidian...
Agent: Found 47 .md files, 12 folders
Agent: 31 have frontmatter, 16 are raw markdown
Agent: Running classification on all notes...

Note "Daily Thoughts 2026-06-15" → Daily Log
Note "Project Alpha Requirements" → Project
Note "Docker Cheatsheet" → Resource
Note "Old Meeting Notes 2024" → Archive
...

Agent: Migrating via ingest_note MCP tool...
  ✅ 01_Projects/Project-Alpha-Requirements.md
  ✅ 01_Projects/Project-Beta-Plan.md
  ✅ 02_Areas/Health-Routine.md
  ✅ 03_Resources/Docker-Cheatsheet.md
  ✅ 04_Archive/Old-Meeting-Notes-2024.md
  ✅ 06_Daily_Logs/2026-06-15_Daily-Thoughts.md
  ... (47 notes total)

Agent: Running lint...
  ✅ OKF Metadata: 0 errors
  ✅ Internal Links: 0 broken
  ✅ Orphans: 3 notes (all in 06_Daily_Logs — exempt)

Agent: Initiating Phase 6: Sync & Publish...
Agent: Importing GPG key and configuring Git identity
Agent: Creating signed commit on branch feature/power-migration
Agent: Pushing changes to GitHub and opening Pull Request
Agent: Verifying CI/CD build workflow status...
  ✅ MkDocs build success: https://weby-homelab.github.io/power-framework/

Agent: Migration and publication completed successfully. Vault is P.O.W.E.R.-compliant.
```

---

## Troubleshooting

| Issue                                        | Cause                                         | Fix                                                           |
| -------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| `ingest_note` returns "Note already exists"  | Note was already migrated                     | Skip and move to next                                         |
| Lint reports missing `type`                  | Note lacks frontmatter                        | Re-ingest with explicit `note_type`                           |
| Broken links after migration                 | Internal `[[links]]` target filenames changed | Run the auto-repair script from Step 6d                       |
| `read_sub_index` returns "No notes found"    | Category folder is empty or not indexed       | Run `generate_index(vault_path)` first                        |
| Too many orphans in `04_Archive/`            | Archived notes by definition have few links   | This is expected — archive orphans are normal                 |
| Lint reports 200+ extra notes                | `.git/` directory is not excluded             | Update linter to skip hidden dirs (v1.5.0+ does)              |
| `_index.md` has no frontmatter               | Using an older version of the framework       | Upgrade to v2.0.2 or re-run `generate_index`                  |
| `pip install` fails with PEP 668             | System Python blocks direct install           | Use a venv: `/path/to/venv/bin/pip install ...`               |
| `External data path escapes model directory` | ONNX Runtime security constraint              | Set `HF_HUB_DISABLE_SYMLINKS=1` in environment before running |

---

## Appendices

### A. Folder-Type Mapping

| Folder           | `note_type`    | Typical Content                                     |
| ---------------- | -------------- | --------------------------------------------------- |
| `00_Inbox/`      | Any            | Unprocessed drafts (agent should classify and move) |
| `01_Projects/`   | `Project`      | Active projects with deliverables                   |
| `02_Areas/`      | `Area`         | Ongoing responsibilities                            |
| `03_Resources/`  | `Resource`     | References, guides, external links                  |
| `04_Archive/`    | `Archive`      | Completed/dead projects                             |
| `06_Daily_Logs/` | `Daily Log`    | Temporal journal entries                            |
| `PROTOCOLS/`     | `System Guide` | Agent instructions, rules                           |

### B. Required MCP Tools

| Tool                                                                          | Used in Phase    |
| ----------------------------------------------------------------------------- | ---------------- |
| `ingest_note(name, note_type, title, description, content, tags?, resource?)` | Phase 3          |
| `lint_vault(vault_path?)`                                                     | Phase 1, 4, 5, 6 |
| `generate_index(vault_path?)`                                                 | Phase 5, 6       |
| `read_sub_index(category, vault_path?)`                                       | Phase 4, 6       |
| `search_vault_tool(query, max_results?, search_mode?, vault_path?)`           | Phase 4, 6       |

### C. Quick-Reference: OKF Frontmatter Fields

```yaml
---
type: Project | Area | Resource | Daily Log | Archive | System Guide
title: "Human-readable title (1-200 chars)"
description: "Single-line summary (1-150 chars)"
resource: "https://..." # Optional
tags: [tag1, tag2] # Optional
owner: "developer-or-agent" # Optional
status: active | review | archived # Optional
timestamp: 2026-07-15T02:00:00 # Auto-generated
related: # Optional GraphRAG links
    - path: "02_Areas/Infra_Security.md"
      relation: depends_on
      confidence: 0.95
---
```

---

<p align="center">
  Built for AI agents, by AI agents ⚡<br>
  &copy; 2026 Weby Homelab
</p>
