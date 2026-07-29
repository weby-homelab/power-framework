# POWER 3.2.7 release notes

POWER 3.2.7 completes the M1 memory-governance foundation. It preserves the
local-first model while making relation authority, temporal retrieval, remote
egress, and memory changes explicit and testable.

## Highlights

- Typed relations preserve relation semantics instead of reducing them to paths.
- Heuristic graph output remains a candidate until an explicit decision accepts
  or rejects it.
- Temporal validity and supersession states participate in retrieval.
- `POWER_EGRESS_POLICY` denies remote embeddings, query expansion, and ROT
  calls by default; internal or sensitive content needs an explicit policy.
- `power memory` and five MCP memory tools use content-addressed proposals,
  explicit approval, stale-write rejection, a shared mutation boundary, and
  content-free append-only receipts.
- The repository now includes a versioned security threat model for its vault,
  MCP, mutation, and egress trust boundaries.

## Validation boundary

GitHub CI runs the supported Python matrix, lint, formatting, type checks,
coverage, dependency audit, package smoke tests, strict documentation build,
and CodeQL. The generated GitHub release contains the wheel, source
distribution, SPDX SBOM, provenance attestation, and release receipt.

The release does not claim production retrieval quality, target-host latency,
or memory consumption without separate versioned human or hardware evidence.

## Upgrade

```bash
pip install --upgrade power-framework==3.2.7
```

Existing vault data requires no migration. Remote integrations that process
non-public notes now require an explicit `POWER_EGRESS_POLICY` setting.
