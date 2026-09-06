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
