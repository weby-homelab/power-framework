---
type: Resource
title: "AI Agent Migration Guide: Migrate Any Obsidian Vault to P.O.W.E.R."
description: "Step-by-step protocol for any LLM-based AI agent to autonomously migrate an existing Obsidian vault to P.O.W.E.R. OKF-compliant structure."
tags: [power, migration, guide, ai-agents, mcp]
timestamp: 2026-07-03T12:30:00
---

# AI Agent Migration Guide: Migrate Any Obsidian Vault to P.O.W.E.R.

**Target audience:** AI agents (Claude, GPT, Gemini, OpenCode) with MCP access to P.O.W.E.R.

**Goal:** Transform any unstructured Obsidian vault into a P.O.W.E.R.-compliant knowledge base with validated OKF metadata, P.A.R.A. folder structure, and hierarchical indexes — fully autonomously.

---

## Overview

This protocol enables any LLM-based AI agent to migrate an existing Obsidian vault by combining:

- **MCP tools** — `ingest_note`, `lint_vault`, `generate_index`, `read_sub_index`, `search_vault_tool`
- **Filesystem access** — reading existing `.md` files, moving/cleaning up old files
- **LLM intelligence** — classifying notes into P.A.R.A. categories, extracting titles, generating descriptions

The agent follows 5 phases. Each phase has clear success criteria.

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

| Type | P.A.R.A. Folder | When to use |
|------|-----------------|-------------|
| `Project` | `01_Projects/` | Active work with a deadline or deliverable |
| `Area` | `02_Areas/` | Ongoing responsibility without a fixed deadline |
| `Resource` | `03_Resources/` | Reference material, guides, external links |
| `Archive` | `04_Archive/` | Completed or obsolete projects |
| `Daily Log` | `06_Daily_Logs/` | Temporal entries, session logs, journals |
| `System Guide` | `PROTOCOLS/` | AI agent instructions, operational protocols |

### For each note, extract:

1. **`title`** — the note's H1 heading or filename (1-200 chars)
2. **`description`** — one-line summary of what this note is about (1-150 chars)
3. **`type`** — the P.A.R.A. category (see table above)
4. **`tags`** — relevant keywords (optional, list of strings)
5. **`resource`** — if the note references an external URL (optional)

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
  "name": "01_Projects/My-Project",           // P.A.R.A. path + filename (no .md)
  "note_type": "Project",                     // From NoteType enum
  "title": "My Project",                      // Human title
  "description": "Building the next big thing", // 1-150 chars
  "content": "<full markdown body here>",     // Original content
  "tags": ["active", "dev"],                  // Optional
  "resource": "https://github.com/..."        // Optional
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

Agent: Migration complete. Vault is P.O.W.E.R.-compliant.
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `ingest_note` returns "Note already exists" | Note was already migrated | Skip and move to next |
| Lint reports missing `type` | Note lacks frontmatter | Re-ingest with explicit `note_type` |
| Broken links after migration | Internal `[[links]]` target filenames changed | Update link targets to match new filenames, then re-run lint |
| `read_sub_index` returns "No notes found" | Category folder is empty or not indexed | Run `generate_index(vault_path)` first |
| Too many orphans in `04_Archive/` | Archived notes by definition have few links | This is expected — archive orphans are normal |

---

## Appendices

### A. Folder-Type Mapping

| Folder | `note_type` | Typical Content |
|--------|-------------|-----------------|
| `00_Inbox/` | Any | Unprocessed drafts (agent should classify and move) |
| `01_Projects/` | `Project` | Active projects with deliverables |
| `02_Areas/` | `Area` | Ongoing responsibilities |
| `03_Resources/` | `Resource` | References, guides, external links |
| `04_Archive/` | `Archive` | Completed/dead projects |
| `06_Daily_Logs/` | `Daily Log` | Temporal journal entries |
| `PROTOCOLS/` | `System Guide` | Agent instructions, rules |

### B. Required MCP Tools

| Tool | Used in Phase |
|------|--------------|
| `ingest_note(name, note_type, title, description, content, tags?, resource?)` | Phase 3 |
| `lint_vault(vault_path?)` | Phase 1, 4, 5 |
| `generate_index(vault_path?)` | Phase 5 |
| `read_sub_index(category, vault_path?)` | Phase 4 |
| `search_vault_tool(query, vault_path?)` | Phase 4 |

### C. Quick-Reference: OKF Frontmatter Fields

```yaml
---
type: Project | Area | Resource | Daily Log | Archive | System Guide
title: "Human-readable title (1-200 chars)"
description: "Single-line summary (1-150 chars)"
resource: "https://..."          # Optional
tags: [tag1, tag2]               # Optional
timestamp: 2026-07-03T12:00:00   # Auto-generated
---
```

---

<p align="center">
  Built for AI agents, by AI agents ⚡<br>
  &copy; 2026 Weby Homelab
</p>
