---
type: Resource
title: "AI Agent Migration Guide: Any Markdown Knowledge Base to P.O.W.E.R. v3.7.3"
description: "Fail-closed, manifest-driven protocol for migrating an existing Markdown knowledge base to a verified P.O.W.E.R. vault without modifying the source."
tags: [power, migration, guide, ai-agents, safety, verification]
timestamp: 2026-08-17T12:00:00+03:00
---

# AI Agent Migration Guide: Any Markdown Knowledge Base to P.O.W.E.R. v3.7.3

This guide is written as an execution contract for any AI agent with filesystem
access. It migrates a Markdown or Obsidian knowledge base into the canonical
P.O.W.E.R. structure while preserving source content, attachments, provenance,
and a rollback path.

For a new empty vault, stop here and use [Getting Started](getting-started.md).
For Windows 11 25H2 runtime setup, first use the
[Windows installation guide](windows-11-installation.md).

This guide targets the `v3.7.3` candidate release. Select the clean-install
guide when the destination is empty. Select this guide when any existing note,
attachment, or configuration must be preserved. Never run `power init` inside
an existing knowledge base.

## Repository instruction index

An agent must read the relevant documents before changing data:

1. [Clean installation](getting-started.md) — isolated runtime, empty vault,
   first note, validation, FTS, and MCP preflight.
2. This migration guide — discovery, backup, manifest, transformation,
   canonical placement, link repair, and acceptance gates.
3. [Windows 11 25H2 installation](windows-11-installation.md) — exact
   PowerShell paths, Visual C++ requirement, and target-host checks.
4. [CLI reference](cli.md) and [MCP server contract](mcp-server.md) — current
   commands, parameters, rate limits, and security boundaries.

## What “migrate any knowledge base” means

- P.A.R.A., C.O.D.E., GTD, Zettelkasten, LYT, Johnny.Decimal, flat folders,
  and hybrid trees are supported as **source classifications**.
- The destination uses canonical P.O.W.E.R. top-level folders so hierarchical
  indexing and the 20 MCP tools have their documented behavior.
- A non-Markdown system must first export notes to Markdown and attachments to
  files. Vendor database extraction is outside P.O.W.E.R.'s current CLI.
- Unknown frontmatter fields may be retained, but the required OKF fields must
  validate.
- The source is never migrated in place. It remains unchanged until the user
  separately decides how long to retain it.

## Current tool boundary (do not assume more)

- `power init` accepts only a new or empty directory.
- `power index` catalogs `00_Inbox`, `01_Projects`, `02_Areas`,
  `03_Resources`, `04_Archive`, `06_Daily_Logs`, and `PROTOCOLS`.
- MCP `ingest_note` writes only within the approved P.A.R.A. folders, is rate
  limited, regenerates the index, appends `log.md`, and runs lint.
- MCP `read_sub_index` and `ensure_sub_index` accept canonical P.A.R.A.
  categories, not arbitrary source folders.
- CLI `power ingest` creates a new note but does not import an existing note
  body. For a bounded batch import, use `power import`; it is the only command
  that accepts an explicit source directory and produces a preflight report.
- `power import` scans Markdown files only. It does not copy attachments,
  configuration files, or vendor databases; inventory and copy those items in
  Phase 2 and Phase 4 with separate hashes.
- `power heal` repairs missing/invalid frontmatter fields; it does not classify
  arbitrary top-level folders, repair wikilinks, or call an LLM.
- `power rename` is dry-run by default and updates `related` metadata paths. It
  does not promise a complete rewrite of every Markdown or Obsidian link.

These constraints are why this protocol uses a staging vault and a migration
manifest instead of pretending that one command performs a lossless migration.

## Version-stamped executable facts

This guide is verified against the `v3.7.3` candidate release contract. CI checks these
facts against the executable capability manifest so an agent does not inherit
an older migration recipe:

- the current surface is 25 top-level CLI commands and 20 MCP tools;
- the default search mode is `auto`; it uses verified dense when ready and
  otherwise labelled FTS; `semantic` and `reranked` are explicit opt-ins;
- database and cache paths are runtime-owned. Use `power doctor DESTINATION
  --json` to read the active paths and state; never hard-code a vault-local
  database filename;
- `power heal` repairs frontmatter, not wikilinks. For foreign frontmatter
  shapes, `power import --policy quarantine` preserves values as `x-status` or
  `x-related` before the strict validation gate;
- VRAM, latency, and dense/reranked readiness are target-host evidence, not a
  fixed promise. Record `power doctor` and sync results for the actual host.

### Bounded import fast path

For a source tree whose destination folder and filename mapping are already
known, `power import` provides the executable preflight without mutating the
source:

```bash
power import /absolute/path/to/source --into 03_Resources \
  --path /absolute/path/to/vault --policy quarantine --dry-run
```

The default `strict` policy rejects a source note whose known field uses a
foreign value. The explicit `quarantine` policy moves a foreign `status` to
`x-status` and a foreign `related` shape to `x-related`, preserving the
original value and Markdown body. `type`, malformed YAML/frontmatter, and
other schema failures remain excluded. The report lists scanned, importable,
quarantined, unchanged, excluded, collision, and per-field counts before any
write.

Apply only after reviewing the report:

```bash
power import /absolute/path/to/source --into 03_Resources \
  --path /absolute/path/to/vault --policy quarantine
power index /absolute/path/to/vault --strict
power search /absolute/path/to/vault "known phrase" --mode fts
```

Use `--allow-partial` only when the named exclusions are acceptable. The
source remains unchanged; a conflicting destination is never overwritten.

This fast path is not a complete methodology migration. It preserves the
source-relative Markdown tree below one chosen canonical folder. Use the
six-phase protocol when notes need classification, filename mapping, link
rewrites, attachment handling, or a rollback record.

## Six-phase protocol

1. Authorization and immutable source snapshot
2. Inventory and classification manifest
3. Destination initialization and staged transformation
4. Attachments, links, and graph relations
5. Executable validation and reconciliation
6. Cutover, rollback record, and maintenance

Do not skip a phase. A later success does not erase an earlier missing gate.

---

## Phase 1: Authorization and immutable source snapshot

### 1.1 Resolve exact paths

Record absolute paths for:

- `SOURCE` — the existing knowledge base;
- `DESTINATION` — a new sibling directory;
- `BACKUP` — a snapshot outside both source and destination;
- `WORK` — manifests, reports, and temporary transformed copies.

Reject a plan where any path is empty, `/`, a user home directory, or an
ancestor of another target. Do not follow unresolved environment variables or
broad globs for deletion or overwrite operations.

### 1.2 Record source state

Before changing anything, record:

- UTC timestamp, host, OS, and P.O.W.E.R. version;
- source file count and total bytes by extension;
- Git commit/status when the source is a Git repository;
- unreadable files, symlinks, duplicate relative paths, and case-only filename
  collisions (important when moving to Windows);
- excluded/generated directories such as `.git`, `.obsidian`, `.venv`,
  `node_modules`, caches, and existing search databases.

### 1.3 Create and verify a backup

Use a filesystem snapshot or an archive/copy appropriate for the host. The
backup must be outside the source tree and must not contain secrets that were
excluded by authorization.

Verification requires:

- archive/copy command exit code `0`;
- the backup can be listed or mounted;
- source and backup inventories agree for all authorized files;
- SHA-256 values agree for attachments and original Markdown bytes.

Do not begin Phase 2 with an unverified backup. Never put a backup archive
inside the vault where it can be indexed or committed.

**Phase 1 receipt:** exact paths, source Git state, inventory totals, backup
location, verification command, exit code, and digest/count comparison.

---

## Phase 2: Inventory and classification manifest

### 2.1 Build the complete inventory

Inventory, without editing:

- every Markdown file and its relative path, size, and SHA-256;
- every attachment and its relative path, size, and SHA-256;
- encoding/BOM and line-ending anomalies;
- existing YAML frontmatter and required-field validity;
- wikilinks, embeds, Markdown links, and `related` paths;
- filename stems that are ambiguous under Obsidian-style basename links;
- external URLs (record only; do not send private content to a remote service).

Exclude only explicitly authorized generated/vendor trees. Preserve the
exclusion list in the manifest so counts are explainable.

### 2.2 Detect source methodology

Use directory and content signals as hints, never as proof:

| Source pattern | Typical signal | Initial POWER target |
| --- | --- | --- |
| P.A.R.A. | Projects, Areas, Resources, Archive | matching canonical folder |
| C.O.D.E. | Capture, Organize, Distill, Express | Inbox/Resource/Area/Project by content |
| GTD | Inbox, Next Actions, Waiting, Someday, Projects | Inbox/Project/Area/Archive |
| Zettelkasten | fleeting, literature, permanent, UID names | Resource; hubs may be Area/System Guide |
| LYT | Home, MOCs, Notes, Archives | System Guide/Area/Resource/Archive |
| Johnny.Decimal | numeric category ranges | Area/Project/Resource by semantic role |
| Flat or hybrid | no reliable folder contract | classify note by note; fallback Resource |

### 2.3 Create a migration manifest

One manifest row per source item must contain at least:

```text
source_path
source_kind                 # markdown | attachment | config | excluded
source_sha256
detected_methodology
target_path
okf_type
title
description
link_rewrites_planned
status                      # planned | transformed | verified | blocked
reason
```

For notes, also store a normalized **body hash** after removing only the old
frontmatter. This allows the destination frontmatter to change while proving
that the note body was not silently lost.

### 2.4 Classify OKF metadata

Required fields:

```yaml
type: Project | Area | Resource | Daily Log | Archive | System Guide
title: "Human-readable title"
description: "Single-line catalog summary"
timestamp: 2026-08-08T12:00:00+03:00
```

Optional current fields include `resource`, `tags`, `owner`, `status`,
`expiry`, `related`, `okf_version`, and `memory`. Preserve unknown metadata
unless it is unsafe or collides with the validated schema.

Classification rules:

- active outcome with a finish condition → `Project`;
- ongoing responsibility → `Area`;
- reference, atomic note, clipping, or uncertain item → `Resource`;
- temporal journal/session record → `Daily Log`;
- completed or intentionally retired material → `Archive`;
- agent protocol, MOC/system hub, or operating rule → `System Guide`.

Do not fabricate provenance, owners, dates, or relationships. Mark uncertain
rows `blocked` or use the conservative `Resource` fallback with a reason.

**Phase 2 receipt:** total/excluded/classified/blocked counts, collision report,
manifest checksum, and zero unaccounted authorized source files.

---

## Phase 3: Destination initialization and staged transformation

### 3.1 Install and preflight P.O.W.E.R.

Use the `v3.7.3` environment from Getting Started and verify:

```bash
POWER_PYTHON=/absolute/path/to/venv/bin/python
POWER_CLI=/absolute/path/to/venv/bin/power
"$POWER_CLI" --version
"$POWER_PYTHON" -c 'import power_framework; print("lean FTS import: OK")'
```

`POWER_PYTHON` must be the interpreter that owns `POWER_CLI`. Use these
variables in all following commands.

### 3.2 Initialize the empty destination

```bash
"$POWER_CLI" init /absolute/path/to/destination
```

The command must exit `0`. Do not copy source files into the destination before
this step, and do not bypass the non-empty-directory guard.

### 3.3 Transform in small batches

For each Markdown note:

1. read the source bytes once;
2. separate old frontmatter from the body without changing the body;
3. build validated OKF frontmatter from the approved manifest row;
4. choose a unique target under a canonical P.O.W.E.R. folder;
5. write to a temporary/staging path, then atomically place the completed file;
6. record destination byte hash and normalized body hash;
7. mark the row `transformed`, never `verified` yet.

Use batches small enough to review and retry. Do not regenerate the entire
index after every note in a large migration.

### 3.4 When MCP `ingest_note` is appropriate

It is suitable for a small number of individual notes when:

- the target begins with an approved P.A.R.A. folder;
- `content` is the complete body without the old frontmatter;
- rate limits and per-note index/lint cost are acceptable;
- the returned lint report is inspected.

For a large vault, use controlled filesystem transformation and run the CLI
gates once per batch. Do not claim that MCP supports arbitrary target folders.

### 3.5 Reconcile each batch

After a batch, prove:

- each transformed source row has exactly one destination;
- every destination has valid required frontmatter;
- source and destination normalized body hashes match;
- no target collision overwrote a prior note;
- blocked rows remain visible in the manifest.

**Phase 3 receipt:** batch range, created files, matching body hashes, failed
rows, and retry actions.

---

## Phase 4: Attachments, links, and graph relations

### 4.1 Copy attachments losslessly

Preserve attachment bytes and, where possible, relative layout. Verify SHA-256
equality after copying. Do not embed attachment contents into prompts merely to
move them.

### 4.2 Rewrite links from the manifest mapping

Handle each syntax independently:

- `[[Note]]` and `[[folder/Note|Alias]]` wikilinks;
- `![[attachment.png]]` embeds;
- `[label](relative/path.md)` Markdown links;
- image/file paths;
- OKF `related[].path` values.

Resolve source-relative Markdown links and vault/basename wikilinks according to
their actual semantics. If two notes share a basename, do not guess; use the
manifest target or mark the link blocked.

`power rename` can help with `related` metadata for one known rename, but it is
not a universal wikilink migration engine.

### 4.3 Build graph relations conservatively

Valid forms include a legacy path string or a typed relation:

```yaml
related:
  - path: 02_Areas/Infrastructure.md
    relation: depends_on
    confidence: 0.95
```

Only carry or add a relationship when evidence exists. Do not infer a graph
edge merely because two filenames share a word.

**Phase 4 receipt:** attachment count/hash reconciliation, links examined,
links rewritten, ambiguous links blocked, and remaining broken-link count.

---

## Phase 5: Executable validation and reconciliation

### 5.1 Markdown and OKF gates

```bash
"$POWER_CLI" index /absolute/path/to/destination --strict
"$POWER_CLI" lint /absolute/path/to/destination
"$POWER_CLI" markdown-check /absolute/path/to/destination
"$POWER_CLI" status /absolute/path/to/destination
```

Required result:

- every command exits `0`;
- strict indexing skips zero invalid notes;
- broken internal links are zero;
- any orphan/stale warnings are individually explained, not hidden;
- the status counts agree with the manifest's verified Markdown rows.

### 5.2 Search gates

First prove FTS without model downloads:

```bash
"$POWER_CLI" sync /absolute/path/to/destination --fts-only
"$POWER_CLI" search /absolute/path/to/destination "known phrase" --mode fts
```

Use several known phrases from different source categories and record expected
target paths. Then, only when resources permit, prove dense search:

```bash
"$POWER_CLI" sync /absolute/path/to/destination
"$POWER_CLI" search /absolute/path/to/destination "known concept" --mode semantic
"$POWER_CLI" search /absolute/path/to/destination "known concept" --mode reranked
```

Semantic/reranked readiness remains pending if model download, validation, or
search fails. An FTS pass does not prove dense quality.

### 5.3 Final losslessness reconciliation

The migration is not complete until all are true:

- authorized source Markdown count = verified destination note count;
- every source note has one manifest target or an explicitly approved exclusion;
- normalized source/destination body hashes match for every migrated note;
- source/destination attachment hashes match;
- no unexpected destination file exists;
- blocked and ambiguous items count is zero, or the user explicitly accepts a
  documented exception;
- the source tree still matches its Phase 1 inventory.

Spot checks are useful but never replace full manifest reconciliation.

**Phase 5 receipt:** command outputs/exit codes, lint issue counts, index counts,
search cases, manifest totals, and hash reconciliation.

---

## Phase 6: Cutover, rollback record, and maintenance

### 6.1 Cutover

Point applications and MCP clients to the destination only after Phase 5
passes. Configure the canonical variable:

```text
POWER_VAULT_DIR=/absolute/path/to/destination
```

Restart long-lived MCP clients and run their preflight with the exact configured
Python. Keep the source and verified backup read-only during the observation
period.

### 6.2 Git is optional and separately authorized

A local vault does not require a remote repository. If Git publication is
authorized:

- exclude `.env`, credentials, private keys, model/search databases, backups,
  and raw private evaluation data;
- inspect `git diff --cached` before committing;
- work on a feature branch and use the repository's review/signing policy;
- never import a private signing key or push merely because migration passed.

Private-vault synchronization is not public publication.

### 6.3 Rollback record

Record:

- source, backup, destination, and manifest paths;
- source and destination Git state if applicable;
- exact last passing gate and timestamps;
- how to repoint clients to the unchanged source;
- unresolved exceptions and their owners.

Do not delete the source or backup as part of this protocol. Retention and
destruction require a separate explicit decision.

### 6.4 Ongoing maintenance

After structural changes:

```bash
"$POWER_CLI" index /absolute/path/to/destination --strict
"$POWER_CLI" lint /absolute/path/to/destination
"$POWER_CLI" markdown-check /absolute/path/to/destination
```

Run `power sync` when retrieval indexes need refreshing. Read `index.md`, then
the relevant canonical `_index.md`, then specific notes. Preserve a dated change
record in the vault according to its local operating rules.

## Final acceptance checklist

- Verified backup exists outside source and destination.
- Manifest accounts for every authorized source file with zero unexplained rows.
- Source remains unchanged and can be restored/read.
- Destination notes use canonical folders and valid OKF metadata.
- Body and attachment hash reconciliation passes.
- Link ambiguity is zero or explicitly accepted; broken links are zero.
- `index --strict`, `lint`, and `markdown-check` exit `0`.
- FTS sync/search pass with recorded known-result cases.
- Dense/reranked status is stated as verified or pending based on target-host
  evidence, never inferred from FTS.
- MCP uses the exact installed interpreter and `POWER_VAULT_DIR`.
- Cutover and Git/publication were performed only with explicit authorization.
- Rollback instructions and retained backup paths are recorded.

## Troubleshooting

| Problem | Correct response |
| --- | --- |
| `power init` rejects the source | Expected: it is non-empty. Create a separate destination. |
| `ingest_note` rejects a custom folder | MCP writes are restricted to approved P.A.R.A. folders. Map the note to a canonical target. |
| `read_sub_index` rejects a source category | It accepts canonical P.A.R.A. categories. Use the destination mapping and generated canonical index. |
| `power heal` leaves notes invalid | Custom folders may not provide a type hint. Add approved `type`, `title`, `description`, and `timestamp` from the manifest, then validate again. |
| Links break after moving notes | Apply the source→target mapping separately to wikilinks, Markdown links, embeds, and `related`; do not assume `power rename` rewrites all forms. |
| `index --strict` fails | Inspect every skipped path; do not continue to cutover with a partial catalog. |
| Dense sync fails | Record semantic/reranked as pending and keep FTS operational; do not downgrade the evidence claim silently. |
| Counts match but hashes do not | Migration is not lossless. Restore/retransform the mismatched rows before cutover. |
