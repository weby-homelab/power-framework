# POWER 3.4.5 release notes

POWER 3.4.5 records the prior cross-platform technical baseline across Linux,
Windows 11 25H2, and macOS. Its historical retrieval contract was semantic;
the development line now targets the FTS-first `auto` profile for 3.5.0.

## What changed

- **Cross-Platform Support Matrix**: Documented and verified platform boundaries for Linux, macOS (`macos-latest` Python 3.13 CI smoke), hosted Windows Server, and physical Windows 11 25H2 GPU environments (`docs/support-matrix.md`).
- **Synthetic Quality Oracle Harness**: Added `benchmarks/power31/scripts/evaluation/run_quality_comparison.py` evaluating `semantic` vs `reranked` retrieval on dataset v1 (228 queries, 100 corpus docs, 416 qrels) with paired statistics (MRR@10, NDCG@10, Recall@10, per-stratum UA↔EN breakdown, and warm latency).
- **Historical Retrieval Evidence**: The 3.4.5 semantic measurements remain
  version-stamped historical evidence; they do not define the 3.5.0 default.
  The 3.5.0 `auto` profile exposes actual mode and fallback reason.
- **Truthful MCP Discovery & Server Info**: `get_server_info` tool exposes FastMCP package version, configured vault path, coverage stats, and explicit provider binding state without side effects or model preloading.
- **Windows Runtime Safety**: `power rename` uses `os.replace()` for atomic physical moves. Windows runtime smoke enforces strict index coverage policy (`power sync --fts-only --strict`).
- **Governance boundary**: This is a technical release baseline. Issue status,
  human-quality certification, and production claims require separately retained
  tracker/readback evidence and are not inferred from the regression suite.

## Validation and evidence boundary

The release workflow runs the full test matrix (Python 3.11–3.14 on Linux, macOS, and Windows), Ruff, MyPy, CodeQL SAST, package smoke, security scan, and tag-bound release contract checks. The release baseline (`release/evidence/baselines/v3.4.5.json`) records the exact source commit, tree, model lock hash, and dataset hashes.

## Upgrade

Install the immutable release wheel:

```bash
python -m pip install \
  https://github.com/weby-homelab/power-framework/releases/download/v3.4.5/power_framework-3.4.5-py3-none-any.whl
power --version
```
