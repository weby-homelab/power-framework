# POWER 3.8 Stale Dependabot PR Cleanup & Dependency Refresh Ledger

Baseline Main Commit: `d14a851e459eb5166d25df5764c3304bcd8c30e2`
Recorded: 2026-09-04T23:22:00+03:00

| PR | Package | Version | Classification | Merge Base | Disposition |
|:---|:---|:---|:---|:---|:---|
| #389 | `filelock` | 3.32.5 | Ordinary Maintenance | `af2e302` | Close stale PR; re-evaluate in controlled dependency refresh on current main. |
| #390 | `pygments` | 2.21.0 | Ordinary Maintenance | `af2e302` | Close stale PR; re-evaluate in controlled dependency refresh on current main. |
| #391 | `mcp` | 2.1.1 | Compatibility Relevant | `af2e302` | Re-evaluate against the final Phase-5 Context/MCP implementation. Must pass full stdio/client compatibility suite. |
| #392 | `numpy` | 2.5.2 | Compatibility Relevant | `af2e302` | Do not automatically widen upper boundary. Requires semantic, rerank, ONNX runtime, Profile B, lock reproducibility, and performance tests. |
| #393 | `huggingface-hub` | 1.29.0 | **SECURITY RELEVANT** | `af2e302` | **MANDATORY SECURITY RE-EVALUATION BEFORE v3.8.0**. Contains security-relevant upstream fixes. |

## Controlled refresh run — 2026-09-06

This run starts from the authoritative Phase-4 merge baseline
`01059114a29af2fd0f1faafa6c8190fadcca1c86`. Phase-4 source files and package
version `3.7.11` remain unchanged.

- PR #399 (`4a2c16892492c384e8932871357e71acbaf3bda6`) remains open and is not
  mergeable evidence: the `pip` Dependabot ecosystem updates `pyproject.toml`
  and exports but cannot update the authoritative `uv.lock`. Its CI fails in
  locked-install steps before substantive assertions; CodeQL passes.
- Maintainer replacement branch: `chore/power-3.8-python-dependency-refresh-controlled`.
  The branch changes the Dependabot ecosystem to `uv`, refreshes the lock with
  `uv==0.11.33`, and regenerates the current Web export. Historical
  `power-suite-3.7.1-gui-0.7.7.constraints.txt` is byte-identical and was not
  regenerated.
- Current derived artifact SHA-256: `uv.lock`
  `6be64b778beb877f8ef9cfc9c962dfe82ee7d8c659d40ad7f13f3230a1c90f9a`;
  `release/web-runtime.requirements.txt`
  `2d77741f2b30fce8bf5bdfff13f028b7c1279e21d852f8e6b7f85b41eebf4a9a`.
- Resolved maintenance graph includes `mcp==2.1.1`, `mcp-types==2.1.1`,
  `onnxruntime==1.29.0`, `anyio==4.15.1`, `numpy==2.4.6`,
  `pydantic-core==2.46.5`, and `huggingface-hub==1.25.1`. NumPy 2.5.2 and
  `pydantic-core==2.48.0` are explicitly split out: optional
  `qwen3-embed==1.12.0` requires NumPy `<2.5`, while `pydantic==2.13.5`
  requires `pydantic-core==2.46.5`. Bringing either bot target into this
  graph would not produce a self-consistent lock.
- Verified local gates: `uv lock --check`, frozen install/pip check, MCP 58
  tests, neural contract 5 tests, embeddings/reranker 59 tests, PSE/Task/
  Decision/crash regression 354 tests, full CI suite 1713 passed with 82.50%
  coverage, Ruff, format, mypy, doc-drift, MkDocs strict, benchmark integrity
  114 tests, package smoke, Web hash install, and `pip-audit`.
- Docker Profile B is not executed on PRXMX-01 because the Docker CLI/daemon is
  unavailable. Real-vault neural benchmark cases remain local-vault blocked;
  no online model-download PASS is claimed.
- HF security refresh and Actions PR #396 remain pending by design. No merge,
  tag, release, version bump, or Phase-5 work is authorized by this record.

## Python replacement remote closure — 2026-09-06

- Replacement PR #400 was opened against
  `01059114a29af2fd0f1faafa6c8190fadcca1c86` and advanced through signed commits
  `e2dbc867e85001b6f9926840e77d76115ffbf788`,
  `60e04ea7daac9890066d75331d970f2652314683`,
  `67197de24852e9ddcb75708ad5d8c4cfb6673377`,
  `2b90301ed7d9c46fcc51828c511e846ed993312d`, and
  `7a694a373d2431c6103deb636796e9e92d93198b`.
- #399 was closed as superseded and not merged. Its final replacement comment
  is retained on the PR.
- Final exact-head remote evidence for #400: CI run `34035570545`, CodeQL run
  `34035570543`, and Docs run `34035570546`; all required contexts passed.
  The CodeRabbit review thread is resolved and outdated with no remaining
  actionable review comment.
- Final local evidence: Python 3.13.5 and 3.14.6 locked environments passed
  import/version and pip checks; MCP 58 tests; neural contract 5 tests; PSE/
  Task/Decision/crash 359 tests; full suite 1713 passed, 4 skipped, 17
  deselected; coverage 82.51%; benchmark integrity 114 passed, 1 skipped;
  Ruff, format, MyPy, docs, package smoke, upgrade matrix, and full-maintained-
  profile pip-audit passed.
- The Web export is now raw canonical `uv export` output. Both CI and release
  workflows enforce a blocking byte-for-byte comparison against `uv.lock`.
- PR #400 was manually squash-merged as `1fc285ac134445841f1954648db94de4564ab6ac`.
  Because squash merge does not retain the PR head as an ancestor, this ledger
  update is intentionally based on signed PR head
  `7a694a373d2431c6103deb636796e9e92d93198b` and must be
  normal-merged before the lineage invariant is considered closed.
- The lineage branch must include current main before merge; squash is
  prohibited for this closure because it would discard the signed refresh head.
