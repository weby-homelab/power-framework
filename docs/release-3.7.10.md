# POWER 3.7.10 patch release

POWER 3.7.10 is the patch release after the existing `v3.7.9` release boundary.
It carries release-integrity hardening from the current branch and does not
rewrite the historical `v3.7.9` or `v3.7.8` records,
artifacts, or evidence.

## Changes in 3.7.10

- Manual release recovery is constrained to an existing signed annotated tag.
  It must prove that no GitHub Release exists for that tag and cannot create,
  move, force-update, replace, or delete a tag or release.
- Web-image promotion preserves the exact source image digest and uses an
  explicit single-platform promotion mode before the registry digest is read
  back.
- Public release verification now fails closed unless the published manifest,
  checksums, receipt, Profile A/B evidence, tag target, and attestation subjects
  bind to the same public asset directory and release identity.
- Profile evidence is checked for its schema, harness revision, native and Web
  capability flags, non-root container identity, dropped capabilities,
  read-only root filesystem, and absence of Web MCP services or application
  boundary bypasses.
- Release validation distinguishes a successful prepublication check with
  pending publication gates from a completed release, while still rejecting
  failing checks.
- The adversarial release-integrity suite and CI policy checks cover the new
  immutable recovery, digest, profile, receipt, and public-readback boundaries.

## Runtime and support boundary

- The unified package remains `power-framework` with 26 CLI commands and 20
  MCP tools through the official MCP Python SDK v2.
- Profile A is the native Linux runtime with `power` and `power-mcp` over local
  stdio. Profile B adds exactly one Web-only `power-web` container through the
  same `ApplicationService` boundary.
- The supported release platform remains Linux with Python `>=3.13,<3.15`.
  macOS, Windows, GPU performance, host-independent latency, retrieval quality,
  and multi-tenant claims remain outside this release's certification.
- The content-free upgrade target is `3.7.9 -> 3.7.10`; deferred platforms are
  not represented as successful release evidence.

## Historical evidence boundary

The following material is historical and intentionally remains unchanged:

- `docs/release-3.7.9.md` and `docs/release-3.7.8.md`;
- `release/evidence/3.7.9/` and its prepublication forensic records;
- the existing `v3.7.9` and `v3.7.8` tag and artifact identities.

## Publication status

This document defines the release contract; local version-surface updates and
local tests do not prove publication. A stable 3.7.10 claim requires required CI
and CodeQL on the exact signed release-source commit, plus proof that the
release-source Git tree is identical to the tree merged into protected `main`.
The merge commit may therefore differ from the signed source commit without
weakening the identity claim. It also requires a clean signed `v3.7.10` tag,
reproducible wheel and source archive, SBOMs, Profile A/B acceptance, checksums,
manifest, receipt, attestations, GHCR digest, and fresh public readback.

The post-release public verification record is maintained at
[`release/evidence/3.7.10-postrelease/`](https://github.com/weby-homelab/power-framework/tree/main/release/evidence/3.7.10-postrelease).
It is evidence for the immutable release, not an addition to the `v3.7.10`
asset set and not a replacement for any published asset.
