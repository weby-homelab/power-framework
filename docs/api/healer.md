# Healer

Auto-heals missing or invalid OKF frontmatter fields.

| Function | Returns | Description |
|----------|---------|-------------|
| `heal_frontmatter(content, filepath, vault_dir=None)` | `tuple[str, list[str]]` | Heal a single note's frontmatter. Returns (healed_content, list_of_changes). Empty changes list if nothing to heal. |
| `heal_vault(vault_dir, dry_run=True)` | `str` | Scan vault and heal all notes with missing/invalid frontmatter. Returns formatted report. Creates timestamped backups before live edits. |
| `heal_vault_report(vault_dir, dry_run=True, limit=None)` | `HealReport` | Typed receipt with scanned/healed counts, staged per-note failures, formatted output, and `exit_code`. |

## Fields healed

| Field | Heal strategy |
|-------|---------------|
| `type` | Inferred from parent P.A.R.A. folder (`01_Projects` → `Project`, `06_Daily_Logs` → `Daily Log`, etc.) |
| `title` | Converted from filename (kebab/snake to Title Case, date prefixes stripped) |
| `description` | Extracted from first non-header paragraph (max 150 chars) |
| `timestamp` | Added with current UTC time if missing |
| Type casing | Fixed if present but not in correct case (e.g. `project` → `Project`) |

## `HealVault` report

The `heal_vault()` function returns a formatted report with:

```
=== Frontmatter Heal Report ===
Vault: /path/to/vault
Mode: DRY RUN / LIVE
Notes scanned: N
Notes healed: N
Notes failed: 0

Changes:
  01_Projects/my-note.md:
    - Added missing type: Project
    - Added missing title: 'My Note'
```

Failures are reported with the note path and stage (`read`, `validation`,
`transform`, `backup`, or `write`). A failed note is not counted as healed, and
a write failure leaves the original file in place because live edits use the
atomic-write path. Invalid foreign `status` and `related` values are quarantined
as `x-status` and `x-related` before title/description repair.
