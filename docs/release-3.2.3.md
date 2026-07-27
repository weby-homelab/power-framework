# POWER 3.2.3 release notes

POWER 3.2.3 advances the local-first indexing contract and introduces the
additive OKF Memory Contract v0.2. Existing OKF v0.1 notes remain valid and are
not rewritten by this release.

## Highlights

- `power sync` rechecks the BLAKE2 source snapshot immediately before atomic
  publication. If a source changes while staging is in progress, the build is
  rejected and the prior active database remains searchable.
- Optional `okf_version: "0.2"` and `memory` frontmatter support typed memory
  kind, confidence, validity dates, supersession references, provenance,
  write-policy, and sensitivity fields.
- Parser and healer retain unknown frontmatter extensions, including nested
  values, so adopting the contract does not silently discard forward-compatible
  fields.
- Notes generated through `power synthesize` and MCP `ingest_note` contain a
  provenance source, SHA-256 content evidence, and `agent-proposed` policy.

## Validation and limits

The release gate runs Ruff, MyPy, the documentation-drift check, strict MkDocs,
and the hermetic Python suite with its 70% coverage floor. It does not claim a
completed crash/OOM/disk-full fault-injection matrix, automatic filtering of
superseded memories, historical views, acceptance workflow, dry-run bulk
migration, or remote sensitivity enforcement; those remain planned follow-up
work for POWER 3.3.0.

## Upgrade

No migration is required. Existing notes keep their current frontmatter.
Applications can begin writing v0.2 `memory` metadata incrementally; unknown
extension fields are preserved during parsing and healing.
