# POWER 3.7.10 public repository closure report

## EXECUTIVE VERDICT

**NO-GO, blocked by PRXMX drift remediation and an external approval gate.**
The published `v3.7.10` release snapshot and all public release identities
passed independent checks. The closure branch is not merged because one
managed PRXMX Skill target still requires review and protected `main` requires
an independent approval that the current actor cannot provide.

## STARTING STATE

- Repository: `https://github.com/weby-homelab/power-framework`
- Starting public `main`: `1a9879ee2353d63d979da5f68e79a6065122343b`
- Closure branch snapshot before the final report: `cc6e5f19e98b6037f25953959b92b70176aaf802`
- Final report snapshot commit: `2c645598e8876c551e1f0cbd8c34a70764876dce`
- Subsequent inventory-timing clarification: `e0fc3f3a198373cedf2cbcbc3f1068ec5466b6bf`
- Closure PR: `https://github.com/weby-homelab/power-framework/pull/381`
- Latest public PR readback head in the closure evidence: `8ab5314613f104c4aea8aa578bc602ae274ac910`.
- The complete pre-existing untracked `v3.7.9` forensic inventory contains 17
  files, including ignored nested JSON/SBOM files. They are WS-local-only,
  preserved byte-for-byte, never staged, and never treated as public evidence;
  paths, sizes, hashes, and the inventory timestamp are recorded in
  `phase-00-baseline.json` and `phase-16-18-repository-hygiene.json`.

## V3.7.10 RELEASE

- Release: `https://github.com/weby-homelab/power-framework/releases/tag/v3.7.10`
- Tag object: `440a589572ba42867af92e6215a8ca4e1f8b3153`
- Signed release source: `f6cdaa35b552ed0a335051f2f268f57d52302161`
- Source tree: `0f6a5e399bd3a78792a6c5fab983a2136cb2b335`
- PR #377 merge tree: `0f6a5e399bd3a78792a6c5fab983a2136cb2b335`
- Tree equality: **PASS**
- Tag signature and release-source commit signature: **PASS**, verified against
  public fingerprint `7AF1EDA195FE29FF093FB1CA2D49E810C7F2527E` as recorded in
  `phase-01-history.json`.

## CI / CODEQL

CI run `33386643616` and CodeQL run `33386643565` both bind to the exact
release-source commit and concluded success. The historical publication run
`33391322565` created the Release but concluded failure at a later
post-publication OCI readback gate; that failure is disclosed, not converted
to a success claim.

## PUBLIC ASSET INVENTORY / SHA MATRIX

The public Release contains exactly 9 expected assets. Fresh downloads matched
the public `SHA256SUMS`, manifest, receipt, and GitHub asset API digests. The
complete machine-readable inventory is in `phase-03-public-assets.json` and
`phase-04-public-sha-matrix.json`.

Wheel SHA-256:
`f06592d63a7b1176890d5d69f9f9031955f1b78dd020994c3f43e239c54bdda2`

Sdist SHA-256:
`4b828a7cb99fcaa704675cce5d94b20462205b46d9dadb0d628002c5770d1bae`

Manifest SHA-256:
`1aac24ee51e6f1f36a313bbca932fd8fe77abbbdc7b0835174df05bfdc4527f4`

Receipt SHA-256:
`7faec4376fcaaf70a075c00b84e146d22820cfb6dfb2f08183bb62d278163abe`

Package SBOM SHA-256:
`c2c86216d62676da88e6178794309cd8cc9daffc3d2267973700ece04523df3e`

Web SBOM SHA-256:
`0bab3337f62a0a46741f9b85cd2c8119e43be9f641cc89101abc0dd6c04fdefb`

Profile SHA-256:
`83af86ed2a3db0e6b836ca8efded9638ad1a1e22ed964f0d9662fd0c78d9bbf7`

## MANIFEST / RECEIPT / SBOMS / PROFILE A/B

`phase-05-public-bindings.json` records schema, version, source commit/tree,
manifest SHA, receipt SHA, wheel/sdist/SBOM/Profile hashes, published
manifest/receipt attestation IDs, Profile A/B status, and all required equality
checks. Result: **PASS**.
The already-published receipt has no control-plane provenance block; the
future strict generator/verifier contract does not rewrite it.

## ATTESTATIONS / GHCR

Wheel, sdist, and Web OCI attestations were independently verified with
`gh attestation verify`. Subjects match the exact package and image digests.
The public verification JSON exposed subjects, predicate, signer, and run
identity, but did not expose a stable attestation ID for each observed bundle.
Observed entries therefore carry `attestation_id=null` and an explicit
`AMBIGUOUS_NOT_EXPOSED_BY_GH_ATTESTATION_VERIFY_OUTPUT` status. The separate
published manifest/receipt IDs and package/Web roles remain exact.
The wheel and sdist verification output hash is explicitly a combined package
attestation result hash; it is not either artifact digest. Future release runs
now pass explicit `--repo`, repository-qualified `--signer-workflow`, and
`--predicate-type` controls, then apply the repository policy verifier to exact
subject, predicate, signer, source revision, event, ref, and run ID. Raw
verification JSON remains runner-temp-only; only sanitized policy summaries are
eligible for the final evidence artifact.
The authenticated OCI Distribution API returned HTTP 200 and the full digest:

`sha256:923a3efb17ae944bf8eca7df4e46c7e287a1e9c10cd4bbedcebf2f7ee77cadf1`

This equals the manifest, Profile B, and Web attestation subject.

## PUBLIC INSTALL PYTHON 3.13 / 3.14

Public wheel and sdist installations passed independently on Python 3.13.14
and 3.14.6. Each clean environment passed distribution/CLI version checks,
MCP preflight, official MCP stdio initialize/list-tools handshake with 20
tools, and a synthetic init/ingest/index/lint/FTS sync/search lifecycle.
`power doctor` correctly reported the base install as degraded because no
optional embedding provider was requested. No real vault was touched.

## PRXMX READ-ONLY AUDIT

**DRIFT.** After explicit owner authorization, a bounded batch-only read audit
ran over the existing key-based PRXMX transport. It verified the public
`v3.7.10` manifest and wheel digests in memory, found six POWER runtimes at
`3.7.10`, and confirmed four MCP references resolve to `3.7.10`; comments in
the canonical OpenCode JSONC were preserved and are not runtime drift. One
managed OpenCode Skill target is a symlink and therefore remains
`manual_review`. The checkout copy of the audit script was also already dirty,
so it was not executed; the audit used the public-verified tracked `HEAD` blob
instead. All before/after script, index, MCP, and Skill metadata comparisons
were identical, and no mutation command was invoked. This bounded equality is
not represented as proof about all possible transient writes outside the
audited targets. See `phase-10-prxmx-readonly-audit.json` and
`OWNER-ACTION-001`.

## RELEASE CONTROL PROVENANCE

The public receipt was produced by workflow run `33391322565`, attempt 1,
`workflow_dispatch`, using control/workflow revision
`6cab9f63e4a926996fa141d245a9863a5073ca32`. The release source remained the
signed tag target `f6cdaa35b552ed0a335051f2f268f57d52302161`; these identities
are intentionally separate. Future receipt generation now persists both.

## DOCUMENTATION / CHANGELOG

`docs/release-3.7.10.md` now states the exact signed-source CI/CodeQL plus
merged-tree property. `[Unreleased]` truthfully records post-release workflow,
evidence, governance, security, and validation hardening. Active documentation
remains bounded to `3.7.10`, Linux, and Python `>=3.13,<3.15`.

## BRANCH PROTECTION / TAG GOVERNANCE / ACTIONS SECURITY

- `main` protection: **PASS**; one required review, strict required checks,
  force-push and deletion blocked.
- Required contexts: `test (3.13)`, `test (3.14)`, `security`, `package-smoke`,
  `upgrade-matrix (ubuntu-latest)`, `upgrade-matrix-aggregate`,
  `base-runtime-smoke`, `benchmark-integrity`, `analyze (python)`, `CodeQL`,
  and `build`; PR #381 exact-head checks passed.
- Tag ruleset `21939922`: active `update`/`deletion` protection for
  `refs/tags/v*.*.*`, with no `creation` rule; `v3.7.10` was not changed.
- Privileged `workflow_dispatch` release control requires the canonical
  `weby-homelab/power-framework` protected `refs/heads/main`; tag-push release
  behavior remains enabled.
- Actions SHA-pinning enforcement and Dependabot security updates: enabled.
- Release write permissions are job-scoped to the dedicated release job; no
  unsupported step-level permission scope is claimed.
- All repository workflow action references are immutable commit SHAs and
  release credentials are isolated and logged out.

## REPOSITORY SECURITY / HYGIENE / PUBLIC METADATA

The repository has CodeQL, secret scanning, push protection, `SECURITY.md`,
public metadata, and no open issues or PRs other than this closure PR. The
authenticated default-branch readback currently shows 9 open CodeQL alerts with
null severity; their severity is therefore unknown/unclassified, and no P0/P1
absence claim is made. Clear findings were fixed on the closure branch with
focused tests; a default-branch rescan remains pending until merge. Historical
evidence was retained; no temporary artifact was deleted.

## BLOCKERS

- Resolved: historical post-publication OCI readback failure was independently
  reverified and future workflow authentication was hardened.
- Resolved: missing local Docker buildx was replaced by authenticated OCI API
  readback.
- Resolved: pre-commit mypy dependency isolation was aligned with the locked
  project environment.
- Resolved `BLK-0002`: a temporary bounded PRXMX read-only transport was
  authorized, used, and removed without remote mutation.
- Remaining `BLK-0006`: PRXMX Skill/check-out drift requires an explicitly
  authorized remediation and clean audit rerun; `OWNER-ACTION-001`.
- Remaining `BLK-0005`: protected PR approval boundary; `OWNER-ACTION-002`.
  The latest public readback recorded PR #381 head `8ab5314613f104c4aea8aa578bc602ae274ac910`
  with all required checks passed and `reviewDecision=REVIEW_REQUIRED`.

## TESTS / HASHES / DIGESTS

Local and exact-head validation results are recorded in the phase evidence
files. `actionlint` was unavailable in WS, so Actions security is qualified as
`PASS_WITH_ACTIONLINT_UNAVAILABLE`; YAML parsing and workflow pinning policy
checks passed. No credential, private vault content, internal host address,
absolute PRXMX path inventory, or raw attestation signature was persisted.

## FINAL GO / NO-GO

Final public main SHA currently verified: `1a9879ee2353d63d979da5f68e79a6065122343b`.
This is not a closure merge SHA because PR #381 is open and blocked. **NO-GO**
until `OWNER-ACTION-001` (authorized PRXMX Skill/check-out drift remediation
and clean read-only rerun) and
`OWNER-ACTION-002` (independent maintainer approval and normal protected merge
of PR #381) are both completed, followed by Phase 32 post-merge verification
and Phase 33 independent clean-room audit. No `v3.7.11` was created and no
POWER 3.8 work was started.
