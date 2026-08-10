# POWER 3.4.5 release notes

POWER 3.4.5 consolidates the cross-platform supported release baseline across Linux, Windows 11 25H2, and macOS. It incorporates the canonical synthetic quality oracle harness (`benchmarks/power31`), validated CUDA execution on ONNX Runtime GPU, verified BGE-M3 1024d semantic search default, and complete platform matrix coverage.

## What changed

- **Cross-Platform Support Matrix**: Documented and verified platform boundaries for Linux, macOS (`macos-latest` Python 3.13 CI smoke), hosted Windows Server, and physical Windows 11 25H2 GPU environments (`docs/support-matrix.md`).
- **Synthetic Quality Oracle Harness**: Added `benchmarks/power31/scripts/evaluation/run_quality_comparison.py` evaluating `semantic` vs `reranked` retrieval on dataset v1 (228 queries, 100 corpus docs, 416 qrels) with paired statistics (MRR@10, NDCG@10, Recall@10, per-stratum UA↔EN breakdown, and warm latency).
- **Verified Retrieval Default**: Confirmed Semantic Search (BGE-M3 1024d) as the canonical, fast, high-precision default retrieval engine. Reranker is rejected as default due to statistically significant degradation on English notes and latency/VRAM overhead.
- **Truthful MCP Discovery & Server Info**: `get_server_info` tool exposes FastMCP package version, configured vault path, coverage stats, and explicit provider binding state without side effects or model preloading.
- **Windows Runtime Safety**: `power rename` uses `os.replace()` for atomic physical moves. Windows runtime smoke enforces strict index coverage policy (`power sync --fts-only --strict`).
- **Clean Governance**: Zero open repository issues; all field report defects and measurements validated by regression suites.

## Validation and evidence boundary

The release workflow runs the full test matrix (Python 3.11–3.14 on Linux, macOS, and Windows), Ruff, MyPy, CodeQL SAST, package smoke, security scan, and tag-bound release contract checks. The release baseline (`release/evidence/baselines/v3.4.5.json`) records the exact source commit, tree, model lock hash, and dataset hashes.

## Upgrade

Install the immutable release wheel:

```bash
python -m pip install \
  https://github.com/weby-homelab/power-framework/releases/download/v3.4.5/power_framework-3.4.5-py3-none-any.whl
power --version
```
