# POWER 3.2.4 release notes

POWER 3.2.4 is a corrective maintenance release focused on knowledge-base
integrity, deterministic link resolution, and complete local catalog coverage.

## Highlights

- `related` frontmatter accepts typed YAML mappings such as `path`, `relation`,
  and `confidence`, while plain string relations remain supported.
- GFM links resolve relative to the source note. Wiki links that match multiple
  notes are reported as ambiguous instead of being silently attributed to an
  arbitrary basename.
- Links shown as examples in inline code or fenced code blocks no longer create
  false graph edges or false broken-link reports.
- The hierarchical index includes `PROTOCOLS/` and valid root-level daily logs.

## Validation

- Full project suite: 573 passed, 17 optional tests skipped.
- Coverage: 74.94%, above the 70% release gate.
- Vault health lint: zero broken, ambiguous, orphan, or stale-note errors.
- Markdown quality check: zero reported issues.

The machine-readable release baseline in
`release/evidence/baselines/v3.2.4.json` binds this release to its source tree,
model-lock checksum, frozen synthetic benchmark hashes, warning count, and
explicitly skipped optional gates. It is source evidence, not a production
latency or quality claim.

## Upgrade

```bash
pip install --upgrade power-framework==3.2.4
```

No vault migration is required. Existing notes and plain-string `related`
metadata remain backward compatible.
