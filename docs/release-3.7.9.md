# POWER 3.7.9 corrective release

POWER 3.7.9 is the corrective release candidate for the post-3.7.8 release
integrity findings. The historical `v3.7.8` tag and all of its public assets
remain immutable; this release does not replace, move, or reinterpret them.

## Why this release supersedes 3.7.8

The public v3.7.8 wheel, sdist, checksums, published manifest, SBOMs, Profile
A/B evidence, receipt, attestations, and Web image were internally consistent.
The checked-in source manifest was a stale pre-publication object, however, and
the host runtime audit read that raw source file instead of the authoritative
published manifest asset. POWER 3.7.9 separates those roles and fails closed on
any binding mismatch.

## Runtime contract

- Supported release boundary: Linux with Python `>=3.13,<3.15`.
- Profile A is one native `power-framework[mcp]` installation with `power`,
  `power-mcp` over local stdio, one host-side Skill tree, and one canonical
  vault. Docker and Web are not required.
- Profile B starts with Profile A and adds exactly one matching Web-only image
  from `ghcr.io/weby-homelab/power-framework-web`. It uses the same
  `ApplicationService`, mounts the canonical vault for governed operations, and
  exposes host loopback port `8080`; it launches no MCP service.
- macOS and Windows are excluded from this release's certification, upgrade
  matrix, performance, GPU, retrieval-quality, and compatibility claims.

## Release-integrity contract

The release workflow builds the wheel and normalized sdist twice from the exact
tag source, requires byte identity, freezes those bytes, and generates the final
manifest from them. It then binds SBOMs, Profile A/B evidence, attestation
subjects, the OCI digest, baseline, checksums, and receipt before publication.
No package rebuild is allowed after a digest is recorded.

`release/power-release-manifest.json` in the source tree is a candidate-only
template. It is not final release evidence. The final
`power-release-manifest.json` is the GitHub Release asset generated from the
frozen candidate bytes.

The public readback must download the exact asset set into a fresh directory and
run `scripts/verify_public_release_bindings.py`. For every hash-bound file it
requires:

```text
downloaded bytes SHA-256 == SHA256SUMS == published manifest SHA-256
```

It also checks the signed tag target, receipt commit and manifest digest, Profile
B image digest, exact package/Web attestation roles and subjects, and the live
GHCR digest. A missing or contradictory identity is a public-release NO-GO.

## Recovery policy

Manual `workflow_dispatch` is a narrowly scoped immutable recovery path for an
existing signed annotated tag. It may complete publication only for the exact
requested tag after signed-tag admission and authenticated API checks prove that
no GitHub Release exists for that tag.

Recovery never creates, moves, force-updates, or deletes a Git tag, and never
edits or replaces an existing GitHub Release. If a Release exists—or any
identity check is inconclusive—the workflow fails closed. The checkout, package,
Web image, SBOMs, attestations, manifest, receipt, and readback remain bound to
the admitted annotated tag object and peeled commit. A failed publication must
preserve its evidence; a later corrective release uses a new patch tag, while
the historical `v3.7.8` tag and release remain untouched.

## Status boundary

This document is candidate release truth until the public tag, GitHub Release,
GHCR image, attestations, and clean-room readback exist. Do not call POWER 3.7.9
Stable, or declare POWER 3.7.x closed, from local tests or a green CI indicator
alone. The final forensic closure report records the exact identities and every
remaining unsupported claim.
