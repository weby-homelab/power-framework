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

## Phase 6: Post-Migration Self-Maintenance

**Goal:** Ensure the vault stays healthy across AI agent sessions without manual intervention.

This phase covers what the agent MUST do after migration to guarantee 100% self-sustaining operation.

### Step 6a: Install the Official P.O.W.E.R. Framework

Do **not** rely on a custom `power_core.py` copy. Install the official package:

```bash
pip install git+https://github.com/weby-homelab/P.O.W.E.R.git
# Or from the project's venv:
/path/to/venv/bin/pip install git+https://github.com/weby-homelab/P.O.W.E.R.git
```

Configure the MCP server in `opencode.jsonc` (or equivalent agent config):

```jsonc
"power": {
  "type": "local",
  "command": [
    "/path/to/venv/bin/python",
    "-m",
    "power_framework.mcp"
  ],
  "enabled": true
}
```

This exposes 5 MCP tools: `lint_vault`, `generate_index`, `read_sub_index`, `ingest_note`, `search_vault_tool`.

### Step 6b: Create `.geminiignore` (Token Optimization)

Without an ignore file, the agent's context fills with `.git/` objects, `node_modules/`, `__pycache__/`, `*.db`, `*.key`, and `.env` files — all unnecessary. Create this at the workspace root:

```
# Context optimization: exclude heavy/unnecessary files
.git/
.gitignore
.gitattributes
.geminiignore
__pycache__/
*.pyc
node_modules/
.venv/
venv/
*.db
*.key
*.pem
*.crt
*.log
dist/
build/
.env
*.bak
*.swp
.sass-cache/
.vite/
```

**Estimated savings:** 30-50% of agent context tokens in multi-project workspaces.

### Step 6c: Configure Agent Instructions Array

Ensure the agent loads critical files at session start via the `instructions` array in `opencode.jsonc`:

```jsonc
"instructions": [
  "/path/to/AGENTS.md",              // Startup protocol + P.A.R.A. rules
  "/path/to/brain/README.md",        // Vault overview
  "/path/to/brain/PROTOCOLS/LLM_WIKI_SCHEMA.md",  // OKF frontmatter spec
  "/path/to/brain/06_Daily_Logs/MASTER-LESSONS-LEARNED.md",  // Safety
  "/path/to/.agents/skills/power/SKILL.md"  // P.O.W.E.R. skill
]
```

### Step 6d: Fix `[[Home]]` and Other Migrated Wikilinks

After moving files to P.A.R.A. folders, old wikilinks like `[[Home]]`, `[[Security]]`, `[[Servers]]` break because the target files no longer exist at root level. Run an auto-repair script:

```python
import os, re

VAULT = "/path/to/vault"

# Build basename-to-path mapping
name_to_path = {}
for root, dirs, files in os.walk(VAULT):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for f in files:
        if f.endswith(".md"):
            rel = os.path.relpath(os.path.join(root, f), VAULT)
            name_to_path[f[:-3].lower()] = rel

# Iterate all .md files and fix broken [[links]]
for root, dirs, files in os.walk(VAULT):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for fname in files:
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath) as fh:
            content = fh.read()
        new_content = content
        for m in re.finditer(r"\[\[([^\]]+?)(?:\|([^\]]*))?\]\]", content):
            target = m.group(1)
            alias = m.group(2)
            original = m.group(0)
            # Skip if file already resolves
            if os.path.exists(os.path.join(VAULT, f"{target}.md")):
                continue
            # Look up by basename
            key = target.lower().rsplit("/", 1)[-1]
            if key in name_to_path:
                new_target = name_to_path[key][:-3]
                display = alias or target
                replacement = f"[[{new_target}|{display}]]"
                new_content = new_content.replace(original, replacement, 1)
        if new_content != content:
            with open(fpath, "w") as fh:
                fh.write(new_content)
```

**Critical:** The linter's regex MUST handle `[[path|alias]]` syntax — P.O.W.E.R. v1.5.0+ does. If using an older version, update `power_core.py` line:

```python
# Before (broken for aliases):
wiki_links = re.findall(r"\[\[([^\]]+)\]\]", body)

# After (handles [[path|alias]]):
wiki_links = re.findall(r"\[\[([^\]]+?)(?:\|[^\]]*)?\]\]", body)
```

### Step 6e: Understand `_index.md` Behavior

`_index.md` files are **auto-generated** by `generate_index`. They receive OKF frontmatter automatically in P.O.W.E.R. v1.5.0+.

**Important caveat:** If a folder has zero direct `.md` files (e.g., `02_Areas/` when all notes are in `02_Areas/Infrastructure/` and `02_Areas/Deployments/`), the indexer previously skipped it. Since v1.5.0, the generator forces all top-level P.A.R.A. folders + any detected subfolders. Run `generate_index` after every change.

### Step 6f: Exclude `.git/` from All Operations

Both the linter and index generator **must** skip `.git/`. In P.O.W.E.R. v1.5.0+ this is automatic via:

```python
dirs[:] = [d for d in dirs if not d.startswith(".")]
```

Without this, the linter will find 200+ `.md` files inside `.git/` (commit objects, ref logs) and report them as notes, inflating the total count and potentially writing `_index.md` files into `.git/` subdirectories.

### Step 6g: Daily Maintenance Protocol

Every AI agent session should end with:

1. **Save session summary** — create a `06_Daily_Logs/YYYY-MM-DD_session-name.md` with `type: Daily Log`
2. **Regenerate index** — call `generate_index(vault_path)`
3. **Log the change** — append to `log.md` in the same format
4. **Run lint** — call `lint_vault(vault_path)` to catch any regressions

```yaml
# Example Daily Log frontmatter
---
type: Daily Log
title: "YYYY-MM-DD What was done"
description: "One-line summary of the session"
timestamp: 2026-07-03T18:55:00
---

# YYYY-MM-DD Session: What was done

## Summary
...
```

### Step 6h: Cross-Session Continuity Checklist

Before starting work, the agent should:

1. Read `AGENTS.md` (auto-loaded via `instructions` array)
2. Read `MASTER-LESSONS-LEARNED.md` (auto-loaded)
3. Run `lint_vault(vault_path)` to check for regressions since last session
4. Read `index.md` to understand current vault state
5. Read `log.md` tail to see what happened in the last session

### Step 6i: Git Sync & GPG-Signed Publication

Since Obsidian and P.O.W.E.R. vaults are usually version-controlled, the final part of any session or migration is synchronization and publication:

1. **Load Git Credentials**: Always source `GITHUB_USER_NAME` and `GITHUB_USER_EMAIL` from your `.env` file to configure your local Git identity (`git config user.name`/`user.email`). This prevents commits from being attributed to `root` or local hostnames.
2. **GPG Signing Configuration**:
   - Verify the availability of the private key using `gpg --list-secret-keys`.
   - If missing, import the key from `.asc` file (`gpg --import key.asc`) and immediately delete the `.asc` file for security.
   - Configure Git to sign commits by default: `git config commit.gpgsign true`.
3. **Branching & Signing**:
   - Create a feature branch: `git checkout -b feature/migration-name`.
   - Add modified/new files and commit with a GPG signature: `git commit -S -m "docs: complete migration to P.O.W.E.R."`.
4. **Push & Pull Request**:
   - Push the branch: `git push origin feature/migration-name`.
   - Open and merge a Pull Request on GitHub. If the terminal sandbox prevents `gh` CLI authentication, use raw `curl` API requests with `GITHUB_RELEASE_TOKEN` loaded from `.env`.
5. **CI/CD Verification**: Check the status of your documentation website deployment workflows (e.g. GitHub Actions executing MkDocs builds).

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
  ✅ MkDocs build success: https://weby-homelab.github.io/P.O.W.E.R/

Agent: Migration and publication completed successfully. Vault is P.O.W.E.R.-compliant.
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `ingest_note` returns "Note already exists" | Note was already migrated | Skip and move to next |
| Lint reports missing `type` | Note lacks frontmatter | Re-ingest with explicit `note_type` |
| Broken links after migration | Internal `[[links]]` target filenames changed | Run the auto-repair script from Step 6d |
| `read_sub_index` returns "No notes found" | Category folder is empty or not indexed | Run `generate_index(vault_path)` first |
| Too many orphans in `04_Archive/` | Archived notes by definition have few links | This is expected — archive orphans are normal |
| Lint reports 200+ extra notes | `.git/` directory is not excluded | Update linter to skip hidden dirs (v1.5.0+ does) |
| `_index.md` has no frontmatter | Using an older version of the framework | Upgrade to v1.5.0+ or re-run `generate_index` |
| `pip install` fails with PEP 668 | System Python blocks direct install | Use a venv: `/path/to/venv/bin/pip install ...` |

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
| `lint_vault(vault_path?)` | Phase 1, 4, 5, 6 |
| `generate_index(vault_path?)` | Phase 5, 6 |
| `read_sub_index(category, vault_path?)` | Phase 4, 6 |
| `search_vault_tool(query, vault_path?)` | Phase 4, 6 |

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
