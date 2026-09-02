# POWER 3.7.11 patch release

POWER 3.7.11 is the patch release after the immutable `v3.7.10` boundary.
The release is valid only when its signed tag, public assets, attestations, and
clean-install evidence all bind to the same protected-main commit.

## Changes in 3.7.11

- Hardened the native installer with a hash-pinned `power-native-requirements.txt`
  contract, deterministic release slots, atomic activation, rollback checks, and
  managed `power` / `power-mcp` launchers.
- Made MCP stdio discovery and legacy compatibility explicit while requiring
  `POWER_VAULT_DIR` and preserving a 20-tool governed contract.
- Added fail-closed vault, SQLite-index, control-state, and Skill boundaries for
  traversal and symlink escape attempts.
- Hardened external ROT/LLM endpoint handling with explicit egress approval,
  public-address resolution, redirect validation, and credential-origin policy.
- Synchronized package, Web, Skill, onboarding, migration, support, and release
  metadata to `3.7.11`.

## Supported release boundary

- Linux with Python `>=3.13,<3.15` is the supported release platform.
- Profile A uses the native `power-framework[mcp]` runtime and local stdio MCP.
- Profile B adds one matching non-root Web container on port `8080`; it does not
  expose MCP over HTTP, SSE, or TCP.
- Semantic and reranked paths remain explicit optional profiles and must report
  their actual provider/fallback state. The base FTS install does not require
  ONNX or a GPU.
- Ollama integration is local loopback-only; remote Ollama hosts are rejected
  because the client cannot provide the required resolved-address pinning.
- Windows and macOS remain outside the certified release boundary.

## Installation and verification

Use only the immutable public wheel/sdist and the accompanying
`power-native-requirements.txt` after publication. Install dependencies with
`pip --require-hashes`, then install the framework artifact with `--no-deps`.
Run `power --version`, `power doctor`, `power-mcp --version`, MCP modern and
legacy handshake checks, and the Skill/package checks from the clean-install
guide.

Release correctness is established by the public manifest, `SHA256SUMS`, release
receipt, SBOMs, attestation policy results, GHCR digest, and independent clean
readback—not by a local checkout alone.
