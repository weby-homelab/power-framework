# POWER 3.7.12 patch release

POWER 3.7.12 is the maintenance patch release following the immutable `v3.7.11` boundary.
The release is valid only when its signed tag, public assets, attestations, and
clean-install evidence all bind to the same protected maintenance commit.

## Changes in 3.7.12

- Added typed fail-closed task journal integrity validation (`TaskJournalIntegrityError`)
  covering sequence gaps, malformed JSON, schema-invalid events, wrong task ID,
  broken event chains, payload digest mismatches, and missing or empty journals for existing tasks.
- Enforced zero mutation across task state, snapshot, and event journal when journal
  integrity cannot be verified.
- Added degraded read-only Web UI detail view (HTTP 200) displaying the task snapshot,
  an explicit integrity banner, unavailable event history, and suppression of mutation controls.
- Implemented stable public error code `task_journal_integrity` returning HTTP 409 Conflict
  on attempted direct mutations against corrupted task journals.
- Synchronized package, Web, Skill, onboarding, migration, support, and release
  metadata to `3.7.12`.

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
