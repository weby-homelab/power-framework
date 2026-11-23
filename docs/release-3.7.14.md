# POWER 3.7.14 patch release

POWER 3.7.14 is a maintenance patch for the 3.7 release line. Its
signed tag, public assets, attestations, and clean-install evidence must bind
to the same protected maintenance commit before publication can be verified.

## Changes in 3.7.14

- Doctor can report a legacy FTS-only index when its dense chunk table is
  absent, instead of marking that index unreadable solely for that reason.
  A missing or ordinary `fts_notes` table is rejected in this case; an empty
  FTS index is not itself an error.
- Doctor correctly opens relative SQLite database filenames containing spaces
  or URI-special characters such as `?`, `#`, and `%`.
- The doctor report remains schema version 1. When the dense chunk table is
  absent, `vault.indexed_chunks` is `null`; existing warnings and exit-code
  behavior remain in effect.

## Diagnose a legacy FTS-only index

For a controlled local developer workflow with an existing legacy database and
no active generation, run the following from the directory containing `indexes`
and `vault`. The quoted database filename is relative to the current working
directory:

```bash
POWER_SEARCH_DB='./indexes/relative ?# %.db' power doctor './vault' --json
```

`POWER_SEARCH_DB` is a developer/test override; normally, omit it and let
doctor resolve the vault's index. Inspect `vault.index_state`,
`vault.indexed_notes`, `vault.indexed_chunks`, and `issues`. Doctor does not
probe the embedding provider by default, so the existing
`embedding_binding_not_requested` warning can make the report `degraded` and
the command exit with status 1 even when the FTS index is readable. Other
warnings or errors may also affect the result; do not interpret exit 1 alone as
an unreadable index.

## Supported release boundary

- The supported release profile is Linux with Python `>=3.13,<3.15`; see the
  [support matrix](support-matrix.md) for the current boundary.
- This patch does not promise SQLite WAL or hot-journal integrity under
  concurrent changes, and does not include the broader 3.8 capabilities.

## Installation and verification

Use the immutable public wheel or source distribution and the accompanying
hash-pinned `power-native-requirements.txt` only when the signed tag and expected
assets are visible and verified on the [v3.7.14 release page](https://github.com/weby-homelab/power-framework/releases/tag/v3.7.14).
Otherwise, use the [latest published release](https://github.com/weby-homelab/power-framework/releases/latest)
and its matching instructions. For 3.7.14, follow
[Getting Started](getting-started.md) and the [CLI reference](cli.md).
Verify the signed tag, public manifest, checksums, release receipt,
attestations, and clean-install readback before relying on the release. A local
candidate or these notes alone are not evidence of publication.
