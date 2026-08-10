# P.O.W.E.R. platform support matrix

This matrix is the operational boundary for the current `v3.4.5` contract. It
separates automated lifecycle coverage from model-backed, physical-host, GPU,
and retrieval-quality evidence. A green CI job does not certify a different
host, provider, corpus, or performance envelope.

## Current support boundary

| Platform / environment | Tested now | Conditional | Not certified by this matrix |
| --- | --- | --- | --- |
| Linux, Python 3.11–3.14 | Ubuntu CI runs the full test suite, Ruff, MyPy, documentation and release-contract gates; package smoke runs wheel/sdist outside the checkout. | Dense, reranked, and provider-backed workflows require a local model cache and an actually bound provider. | Real-vault dense latency, GPU benefit, ANN recall, and reranker quality. |
| macOS, Python 3.13 | `macos-latest` smoke covers import, init, ingest, strict index, lint, markdown-check, strict FTS sync, and FTS search with offline model settings. | Model-backed dense search requires a locally available model and a verified runtime provider. | Physical Mac hardware performance, GPU acceleration, dense real-vault evidence, and reranker quality. |
| Hosted Windows CI, Python 3.13 | `windows-latest` smoke covers import, init, ingest, strict index, lint, markdown-check, strict FTS sync, FTS search, and CPU provider selection. | The Windows 11 guide must be followed for a physical installation; provider choice is accepted only after session readback. | Physical Windows 11 25H2 GPU performance, CUDA DLL availability on a user's machine, dense real-vault evidence, and quality claims. |
| Physical Windows 11 25H2 | The dedicated [Windows installation guide](windows-11-installation.md) and its validation receipts define the supported installation procedure and host-specific checks. | Exact Python, release artifact, OS build, model cache, ONNX provider, and hardware must be recorded in the receipt. | Hosted CI is not a physical Windows 11 certification; no GPU or latency claim is inferred without a fresh host receipt. |

## Evidence rules for agents

- Treat `tested` as lifecycle coverage only. It proves the named command path on
  the named runner and Python version.
- Treat `conditional` as a precondition, not as a successful runtime claim.
  Check `power doctor --json` and require active provider readback before dense
  work.
- Treat `unsupported` or missing evidence as a stop condition. Do not silently
  fall back from an explicitly requested GPU provider to CPU.
- For a real vault, require an immutable generation, complete coverage, a
  content-free retrieval receipt, cold/warm/process/MCP controls, and resource
  attribution before making latency or ranking claims.

## Source of truth

The executable checks live in [CI](../.github/workflows/ci.yml), the release
workflow is [release.yml](../.github/workflows/release.yml), and the physical
Windows procedure is [windows-11-installation.md](windows-11-installation.md).
The roadmap records evidence boundaries and pending gates in
[`ROADMAP_POWER.md`](https://github.com/weby-homelab/knowledge-base/blob/main/01_Projects/ROADMAP_POWER.md).
