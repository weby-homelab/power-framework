# POWER 3.3.1 technical release notes

POWER 3.3.1 is a machine-only technical release. It packages the fail-closed
M2–M5 technical gate and the Python 3.13 file-backed mutation bridge fix while
preserving the evidence boundary: no new human judgments, design-partner
sessions, or sealed-holdout access are part of this release.

## Machine-only M2–M5 gate

- M2-AUTO synthetic retrieval gate: **PASS**, `31.695s/45s`, verifier errors `[]`.
- M3 synthetic performance gate: **PASS**, max query p95 `151.139 ms`, runtime
  `38.9s`, peak RSS `42.1 MB`, index `405504 B`.
- M4 transactional memory gate: **PASS** — approval boundary, stale proposal
  rejection, state validation, and two history entries.
- M5 release gate: **PASS** — clean tree, `git diff --check`, signed tag and
  release contract.

## Validation

- Framework suite: `707 passed`, `10 skipped`, coverage `79.54%`.
- Focused mutation/MCP regression suite: `34 passed`.
- Ruff, MyPy, changed-file formatting, and root workspace verification: PASS.

## Explicit limitations

This is a technical release, not human-quality certification, product-adoption
evidence, or a production performance claim. The release contract keeps
`human_quality_certification=false`, `production_quality_claim=false`, and
`sealed_holdout=do_not_open`.
