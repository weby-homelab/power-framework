# POWER 3.3.0 technical release notes

POWER 3.3.0 is a technical release of the current framework tree. It includes
the independent architecture-test remediations, the Ukrainian M2 packet
contract, and a transparent threshold readback over the existing development
execution.

## M2 boundary

- The original M2-v2 receipt is immutable: `recall@10 = 0.75` against its
  original `0.80` threshold.
- The curator-authorized remediation profile uses `recall@10 = 0.75` and has
  zero gated failures in the readback receipt.
- The historical evaluator default remains `0.80`; `0.75` is accepted only by
  the explicit M2-v2.1 policy or the separate readback artifact.
- This is a readback, not a new retrieval execution. No human judgments were
  generated or changed.
- The sealed holdout remains `do_not_open`; this release makes no human-quality
  certification or production-quality claim.

## Verification

- Framework: `706 passed`, `10 skipped`, coverage `79.53%`.
- Ruff, format, MyPy and `git diff --check`: PASS.
- Release contract and package smoke must be run against the signed release tag.

## Corrected tag-bound baseline

The original tag contains a historical baseline snapshot from before the final
M2 profile-binding commit. The authoritative corrected artifact is the
`power-framework.release-baseline.json` release asset, generated from the
exact signed tag commit and verified with `--require-tag`. The release workflow
now generates and verifies this asset before building packages; the existing
`v3.3.0` tag and its package assets are not force-rewritten.
