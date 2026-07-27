---
type: Resource
title: "AI Agent Migration Guide: Migrate Any Obsidian Vault to P.O.W.E.R. (v3.2.4)"
description: "Step-by-step protocol for any LLM-based AI agent to autonomously migrate an Obsidian vault to a P.O.W.E.R. 3.2.4 OKF-compliant structure while retaining its chosen folder layout."
tags: [power, migration, guide, ai-agents, mcp, bge-m3, graphrag, methodologies]
timestamp: 2026-07-24T16:00:00
---

# AI Agent Migration Guide: Migrate Any Obsidian Vault to P.O.W.E.R. (v3.2.4)

**Target audience:** AI agents (Antigravity, OpenCode, Claude Code CLI, Gemini 2.0, DeepSeek-R1, Devin) with MCP access to P.O.W.E.R.

**Goal:** Transform any unstructured or existing Obsidian vault into a P.O.W.E.R.-compliant knowledge base with validated OKF metadata, any chosen organizational methodology (P.A.R.A., C.O.D.E., GTD, Zettelkasten, LYT, Johnny.Decimal, or custom/hybrid), and hierarchical indexes — fully autonomously.

---

## Overview

This protocol enables any LLM-based AI agent to migrate an existing Obsidian vault by combining:

- **MCP tools** — `ingest_note`, `lint_vault`, `generate_index`, `read_sub_index`, `search_vault_tool`
- **Filesystem access** — reading existing `.md` files, moving files, updating link paths
- **LLM intelligence** — classifying notes across methodologies (P.A.R.A., C.O.D.E., GTD, Zettelkasten, LYT, Johnny.Decimal), extracting titles, generating descriptions
- **Folder-layout compatibility** — P.O.W.E.R. 3.2.4 can index and validate notes in an existing folder tree. `power init` creates the default P.A.R.A. scaffold only; selectable methodology templates are not implemented. OKF validation and supported search modes operate independently of the folder layout.

The agent follows 6 phases. Each phase has clear success criteria.

---

## Phase 1: Discovery

**Goal:** Understand the vault's current state and detect its existing or intended methodology.

### Steps

1. **Scan the vault directory** — list all `.md` files recursively, excluding `.git/`, `node_modules/`, `__pycache__/`, `.venv/`.

2. **Read each `.md` file** — capture full content. Note:
    - Does it already have YAML frontmatter?
    - Does it have `type`, `title`, `description` fields?
    - What is the current folder structure and naming convention?

3. **Identify existing patterns & DETECT VAULT METHODOLOGY**:
    - **P.A.R.A.** — folders `01_Projects`, `02_Areas`, `03_Resources`, `04_Archive`.
    - **C.O.D.E.** — workflow folders `01_Capture`, `02_Organize`, `03_Distill`, `04_Express`.
    - **GTD (Getting Things Done)** — folders `00_Inbox`, `01_Next_Actions`, `02_Waiting_For`, `03_Someday`, `04_Projects`.
    - **Zettelkasten** — UID presence in filenames (`202607242115_...`), folders `fleeting`, `literature`, `permanent`, `index`.
    - **LYT (Linking Your Thinking)** — content maps `Home.md`, `*_MOC.md`, `MOCs/` folder.
    - **Johnny.Decimal** — decimal folder index (`10-19_...`, `20-29_...`).
    - **Unstructured / Hybrid** — flat folder structure or arbitrary directory tree.

4. **Run `lint_vault(vault_path)`** — baseline health check. Record how many notes are missing metadata and broken links.

5. **🛡️ Create Mandatory Safety Backup (Zero Data Loss Rule)** — BEFORE modifying, moving, or ingesting files, create an intact tarball or snapshot of the vault:
   ```bash
   tar -czf vault_backup_$(date +%Y%m%d_%H%M%S).tar.gz /path/to/vault
   ```
   *Never proceed with destructive operations without a verified backup.*

**Success criteria:** You have a complete inventory of all notes, detected vault methodology, baseline lint metrics, and an intact raw backup archive.

---

## Phase 2: Classification & Methodology Mapping

**Goal:** Analyze each note, determine its OKF metadata (`type`, `title`, `description`, `tags`), and map it to the selected methodology.

### Methodology Support & OKF Type Mapping

Every note is assigned a valid `type` from the OKF `NoteType` enum (or extended semantic types in custom setups). The table below is a migration-planning aid, not a set of CLI templates:

| Methodology | Primary Focus | Folder Skeleton | Initial Mapping to OKF `NoteType` |
| :--- | :--- | :--- | :--- |
| **P.A.R.A.** | Actions & Deadlines | `01_Projects`, `02_Areas`, `03_Resources`, `04_Archive` | `Project`, `Area`, `Resource`, `Archive`, `Daily Log`, `System Guide` |
| **C.O.D.E.** | Distillation & Content Pipeline | `01_Capture`, `02_Organize`, `03_Distill`, `04_Express` | `Capture` (`Resource`), `Organize` (`Area`/`Project`), `Distill` (`Resource`), `Express` (`Project`/`Resource`) |
| **GTD** | Task Processing & Inbox Zero | `00_Inbox`, `01_Next_Actions`, `02_Waiting_For`, `03_Someday`, `04_Projects` | `Resource` (Inbox/Ref), `Project` (Next/Projects), `Area` (Waiting), `Archive` (Someday) |
| **Zettelkasten** | Atomic UID Concept Graph | `fleeting/`, `literature/`, `permanent/`, `index/` | `Resource` (Fleeting/Lit), `Area`/`Resource` (Permanent), `System Guide` (Index/Hubs) |
| **LYT** | Maps of Content (MOCs) | `Home.md`, `MOCs/`, `Notes/`, `Archives/` | `System Guide` (Home), `Area` (MOCs), `Resource` (Notes), `Archive` (Archives) |
| **Johnny.Decimal** | Strict Decimal Index | `10-19_...`, `20-29_...`, `30-39_...` | `Area` (Category index), `Project` (Sub-category), `Resource` (Leaf notes) |
| **Custom / Hybrid** | Arbitrary Tree | Custom (User/Agent choice) | Assign `type:` based on semantic content |

### For each note, extract:

1. **`title`** — the note's H1 heading or filename (1-200 chars)
2. **`description`** — one-line summary of what this note is about (1-150 chars)
3. **`type`** — the corresponding OKF `NoteType` (see table above)
4. **`tags`** — relevant keywords (optional, list of strings)
5. **`resource`** — if the note references an external URL (optional)
6. **`owner`** — owner or responsible developer/agent (optional)
7. **`status`** — status of the note: `active`, `review`, or `archived` (optional, defaults to `active`)
8. **`related`** — structured list of relationships to other files for GraphRAG (optional)

### Classification heuristics

- **Folder & Methodology hints:** Use folder hints (e.g., `01_Capture/` in C.O.D.E. → `Resource`, `permanent/` in Zettelkasten → `Area`/`Resource`).
- **Content Analysis:** Journal entries → `Daily Log`; AI operational rules → `System Guide`; reference guides → `Resource`.
- **Link Graph Density:** Notes with high incoming wikilinks (MOCs / Indexes) → `Area` or `System Guide`.
- **Default fallback:** When uncertain, assign `Resource`.

**Success criteria:** Every note has a draft `(type, title, description, tags, target_path)` tuple ready.

---

## Phase 3: Migration & Skeleton Generation

**Goal:** Create each note in the designated methodology folder with validated OKF frontmatter and rebuild indexes.

### Step 3a: Prepare the vault skeleton

`power init /path/to/vault` creates the default P.A.R.A. structure. Do not run it in a non-empty vault unless that structure is intended. For C.O.D.E., GTD, Zettelkasten, LYT, Johnny.Decimal, or a custom layout, retain or create the required folders directly, then run `lint` and `index`. The `--template` option is not currently supported.

### Step 3b: Ingest each note

For every classified note, call the MCP tool `ingest_note`:

```jsonc
{
    "name": "01_Projects/My-Project", // Methodology path + filename (no .md)
    "note_type": "Project", // From NoteType enum
    "title": "My Project", // Human title
    "description": "Building the next big thing", // 1-150 chars
    "content": "<full markdown body here>", // Original content
    "tags": ["active", "dev"], // Optional
    "resource": "https://github.com/...", // Optional
}
```

For Zettelkasten:
```jsonc
{
    "name": "permanent/202607242115-my-atomic-idea",
    "note_type": "Resource",
    "title": "Atomic Concept of Vector Indexing",
    "description": "Explaining ONNX vector indexing in Zettelkasten format",
    "content": "<markdown content>"
}
```

For C.O.D.E.:
```jsonc
{
    "name": "01_Capture/Raw-Idea-Note",
    "note_type": "Resource",
    "title": "Raw Idea Note",
    "description": "Captured raw note for future distillation",
    "content": "<markdown content>"
}
```

**Important rules:**

- `name` includes the target methodology folder path + filename (hyphens or underscores, no spaces)
- `note_type` must match OKF enum (`Project`, `Area`, `Resource`, `Archive`, `Daily Log`, `System Guide`)
- `content` is the **full original markdown body** — strip any old YAML frontmatter first
- The `ingest_note` tool automatically:
    - Validates all metadata via Pydantic v2
    - Writes the file with proper OKF frontmatter
    - Regenerates the hierarchical index
    - Appends an entry to `log.md`
    - Runs a lint check

### Step 3c: Batch efficiency

For large vaults (>50 notes), group ingests by category. This keeps the index regenerations predictable.

### Step 3d: Vector Embedding Indexing (`power sync`)

After completing note ingests, compute BGE-M3 dense vector embeddings to enable `reranked` and `semantic` search modes:

```bash
power sync /path/to/vault
```
*Note:* Running `power sync` chunks documents, extracts GraphRAG entity connections, and generates 1024d dense embeddings into `.power_search.db`.

**Success criteria:** All notes are created in the target methodology folders with valid OKF frontmatter. Navigation indexes and vector embedding databases (`.power_search.db`) are synchronized.

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

3. **Test hierarchical indexing** — call `read_sub_index(category="<methodology_folder>", vault_path=...)` (e.g. `01_Projects`, `permanent`, or `01_Capture`) and verify it returns a valid sub-index.

4. **Verify Vector & Reranked Search** — call `search_vault_tool(query="test", search_mode="reranked", vault_path=...)` and verify results return without `power sync` warnings.

**Success criteria:** Lint passes with zero errors. Vector search operates cleanly without warnings. Spot checks pass.

---

## Phase 5: Cleanup (Optional)

**Goal:** Remove old, unstructured files once migration is verified.

### Steps

1. List remaining files outside target methodology folders
2. For each:
    - If it was successfully migrated (content now exists in a target methodology folder), delete it
    - If it wasn't migrated, investigate and classify it
3. After all deletions, run `generate_index(vault_path)` to refresh
4. Run final `lint_vault(vault_path)` to confirm

**⚠️ Warning:** Only delete files after **full verification**. Prefer moving to archive folders (e.g., `04_Archive/` or `Archives/`) over deletion for safety.

---

## Phase 6: Post-Migration Self-Maintenance & Git Sync

**Goal:** Ensure the knowledge base remains healthy between AI agent sessions, and synchronize the changes with a remote repository.

---

### Step 6a: Installing and Configuring P.O.W.E.R. Framework (v3.2.4)

For autonomous operation on the target host, install the P.O.W.E.R. toolkit (v3.2.4) globally or in the project's virtual environment:

```bash
pip install git+https://github.com/weby-homelab/power-framework.git
```

#### 🧠 Embedding & Reranker Stack Configuration (v3.2.4 canonical stack)

Starting with version 3.0+, the canonical default embedding engine is **`bge-m3`** (`aapot/bge-m3-onnx`, embedding dimension **1024**), running on direct **ONNX Runtime** + `tokenizers` (`BGEM3OnnxManager`). This is paired with the Apache-2.0 **`onnx-community/bge-reranker-v2-m3-ONNX`** cross-encoder reranker.

Direct ONNX loading resolves fastembed registry issues, tames the BFCArena memory allocator, and enables adaptive batch halving to prevent OOM spikes on 8–12 GB RAM hosts.

To configure thread bounds and memory limits, set environment variables (loaded automatically from `.env`):

```bash
export POWER_EMBED_PROVIDER=bge-m3           # Canonical default provider (aapot/bge-m3-onnx)
export POWER_EMBED_NUM_THREADS=2             # Cap CPU execution threads
export POWER_EMBED_BATCH_SIZE=8              # Batch size for embedding generation
```

When using `bge-m3` or other ONNX models from HuggingFace, set the following to prevent symlink traversal issues:

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
### Step 6c: Configure AI Agent Instructions and Rules

Provide project rules and context to your agent using system rule files (e.g., `.clinerules`, `.cursorrules`, `.windsurfrules`) or an instructions array in the agent's client configuration.
Recommended instruction file structure:

- **`RULES.md` / `INSTRUCTIONS.md`** — General agent behavior and guidelines.
- **`MASTER-LESSONS-LEARNED.md`** — A log of lessons learned and edge-cases to prevent repeat errors.
- **`power/SKILL.md`** — Guidelines for adhering to vault knowledge methodologies.

---

### Step 6d: Fixing Internal Wikilinks

Since files are moved into target methodology folders (e.g., `01_Projects/`, `01_Capture/`, `permanent/`, etc.), old direct wikilinks may require updating. The AI agent must verify and update references like `[[Note Name]]` to the relative path format `[[Methodology Folder/Note Name|Alias]]`.
The P.O.W.E.R. Linter automatically checks for broken links, and corrections can be made using a link repair script or code editing tools.

---

### Step 6e: Automating Index Updates (`_index.md`)

The `_index.md` file in each target methodology category folder serves as a navigation map and is generated automatically using the `power index` command.
_Agent Rule:_ After any change to the note structure (adding, moving, or deleting files), always regenerate the indexes using the MCP tool `generate_index` or the CLI `power index`.

---

### Step 6f: Excluding System Folders

Ensure that the vault validator and indexer ignore system and configuration directories (e.g., `.git/`, `.obsidian/`) to prevent false alarms about missing metadata or broken links in temp files.

---

### Step 6g: Daily Maintenance Protocol

Each session working with the vault should conclude with a maintenance cycle:

1. **Save session log** — Create a note in `06_Daily_Logs/` (type: `Daily Log`) describing the work done.
2. **Rebuild index** — Run `power index` to update `index.md` and `_index.md`.
3. **Synchronize Vector Database** — Run `power sync` to compute BGE-M3 embeddings and refresh GraphRAG links.
4. **Log the change** — Add a brief entry to the central `log.md`.
5. **Validate status (Lint)** — Run `power lint` to confirm no regressions are present (zero errors required).

---

### Step 6h: Cross-Session Continuity Checklist

Before beginning a new work session, the AI agent should:

1. Read the general project rules and system instructions.
2. Read the `MASTER-LESSONS-LEARNED.md` error log.
3. Run `power lint` to check the current health of the database.
4. Read the index `index.md` and the change log `log.md`.

---

### Step 6i: Git Sync, Credentials Purge & GPG Signing

Set up a synchronization pipeline to preserve history and enable collaboration without risking credential leaks:

1. **🔒 Credentials Purge Mandate (CRITICAL)**: Never hardcode or commit tokens, passwords, API keys, private keys (`.pem`, `.key`), or `.env` files into Git. Verify `git diff --cached` before committing to ensure no credentials are stage-exposed.
2. **Committer Identity**: Configure Git's `user.name` and `user.email` to match your developer profile. Avoid committing as unconfigured system users like `root`.
3. **Security Configurations**: Add confidential files (keys, passwords, `.env`, temporary export files, `.power_search.db`) to `.gitignore`.
4. **GPG Signing**: Enable GPG-signed commits (`commit -S`) using your configured GPG key fingerprint (`2D49E810C7F2527E` or personal key).
5. **Git Workflow (PR Workflow)**:
    - Perform work on dedicated feature branches (`feature/*` or `fix/*`).
    - Audit changes via dual-side `git diff` inspection (verify added `+` and removed `-` lines).
    - Merge changes into the main branch via a Pull Request after local tests (`verify.sh`, `pytest`) pass.
    - Clean up merged branches post-merge via GitHub API/scripts without deleting unmerged branches with active PRs.

---

### Step 6j: Multi-Mode Search (FTS + Vector + Hybrid + Semantic + Reranked)

The P.O.W.E.R. framework (v3.2.4) includes a built-in search engine supporting distinct search strategies:

| Mode                 | Description                                                                                              | Best for                                    |
| -------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `reranked` (default) | Canonical POWER 3.2 pipeline: RRF merge of FTS5 + BGE-M3 Dense + BGE Reranker v2 M3                      | Highest-precision multilingual ranking      |
| `fts`                | SQLite FTS5 with weighted BM25 scoring                                                                   | Exact keyword & phrase matching             |
| `vector`             | TF-vector cosine similarity (pure Python, zero deps)                                                     | Lexical similarity comparison               |
| `hybrid`             | RRF (Reciprocal Rank Fusion) merge of FTS + Vector                                                       | Balanced lexical recall                     |
| `semantic`           | Dense embedding cosine similarity (**BGE-M3** 1024d via direct ONNX Runtime)                             | Fast multilingual semantic discovery        |

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
Agent: Detected multi-methodology vault structure (Zettelkasten + C.O.D.E. + P.A.R.A.)
Agent: 31 have frontmatter, 16 are raw markdown
Agent: Running classification on all notes into OKF NoteTypes...

Note "Daily Thoughts 2026-06-15" → Daily Log (06_Daily_Logs/)
Note "Project Alpha Requirements" → Project (01_Projects/)
Note "Raw Idea Note" → Resource (01_Capture/)
Note "202607242115-vector-indexing" → Resource (permanent/)
Note "Docker Cheatsheet" → Resource (03_Resources/)
Note "Old Meeting Notes 2024" → Archive (04_Archive/)
...

Agent: Migrating via ingest_note MCP tool into target methodology folders...
  ✅ 01_Projects/Project-Alpha-Requirements.md
  ✅ 01_Capture/Raw-Idea-Note.md
  ✅ permanent/202607242115-vector-indexing.md
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
| `_index.md` has no frontmatter               | Using an older version of the framework       | Upgrade to v3.2.4 or re-run `generate_index`                  |
| `pip install` fails with PEP 668             | System Python blocks direct install           | Use a venv: `/path/to/venv/bin/pip install ...`               |
| `External data path escapes model directory` | ONNX Runtime security constraint              | Set `HF_HUB_DISABLE_SYMLINKS=1` in environment before running |

---

## Appendices

### A. Folder-Type Mapping for All Methodologies

| Methodology | Folder / Skeleton | `note_type` | Typical Content |
| :--- | :--- | :--- | :--- |
| **P.A.R.A.** | `00_Inbox/` | Any | Unprocessed drafts (classified and moved) |
| | `01_Projects/` | `Project` | Active projects with deadlines & deliverables |
| | `02_Areas/` | `Area` | Ongoing areas of responsibility |
| | `03_Resources/` | `Resource` | Reference material, guides, external links |
| | `04_Archive/` | `Archive` | Completed or obsolete material |
| | `06_Daily_Logs/` | `Daily Log` | Temporal journal entries & session logs |
| | `PROTOCOLS/` | `System Guide` | AI agent instructions & system rules |
| **C.O.D.E.** | `01_Capture/` | `Resource` | Incoming clippings, bookmarks & raw ideas |
| | `02_Organize/` | `Area` / `Project` | Notes organized by area or active project |
| | `03_Distill/` | `Resource` | Distilled summaries & core insights |
| | `04_Express/` | `Project` / `Resource` | Published articles, reports & outputs |
| **GTD** | `00_Inbox/` | `Resource` | Raw incoming tasks & notes |
| | `01_Next_Actions/` | `Project` | Specific immediate actionable items |
| | `02_Waiting_For/` | `Area` | Delegated / pending response tasks |
| | `03_Someday/` | `Archive` / `Resource` | Future / optional ideas & aspirations |
| | `04_Projects/` | `Project` | Multi-step goal-oriented projects |
| **Zettelkasten** | `fleeting/` | `Resource` | Temporary quick thoughts |
| | `literature/` | `Resource` | Book / source reading notes |
| | `permanent/` | `Area` / `Resource` | Atomic conceptual notes with UID prefixes |
| | `index/` | `System Guide` | Navigation hubs, MOCs & structured indexes |
| **LYT** | `Home.md` | `System Guide` | Home entry point navigation hub |
| | `MOCs/` | `Area` | Maps of Content (topic maps) |
| | `Notes/` | `Resource` | Atomic thematic notes |
| | `Archives/` | `Archive` | Outdated MOC maps & notes |
| **Johnny.Decimal** | `10-19_Admin/` | `Area` | Administrative & organizational documents |
| | `20-29_Engineering/`| `Area` / `Project` | Engineering specs & development |
| | `30-39_Ops/` | `Area` | Operations instructions & monitoring |
| **Custom / Hybrid** | Custom tree | `type:` from OKF enum | `type:` assigned based on semantic content |

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
