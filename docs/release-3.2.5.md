# POWER 3.2.5 release notes

POWER 3.2.5 is a corrective release that makes SQLite search-index publication
crash-atomic and raises the supported Python runtime floor to Python 3.11.

## Highlights

- Search indexes are published as immutable, per-vault generations. A single
  state-DB transaction advances the active pointer only after the staged SQLite
  database has passed checksum, size, schema and integrity checks.
- Read paths resolve the active generation through the authoritative state
  pointer and open it read-only. The current and previous ready generations are
  retained, so a failed or interrupted build cannot replace a known-good index.
- Legacy fixed `search.db` files migrate only after checksum-verified readback.
  Source inventory records valid and excluded inputs explicitly, while chunk
  identifiers are content-addressed.
- The release fault matrix covers OOM, `ENOSPC`, SQLite lock, corrupt staging
  DB, source races and process kills at each publication checkpoint. It records
  14 versioned raw failure receipts in
  `benchmarks/power31/evidence/phase1-generation-fault-matrix-v1.json`.
- The package and CI contract support Python 3.11–3.14; Python 3.10 is no
  longer supported.

## Validation boundary

The source-scoped baseline
`release/evidence/baselines/v3.2.5.json` binds this release to the verified
generation-store source, model-lock checksum, frozen synthetic benchmark hashes
and recorded local validation. The evidence proves release-contract and
failure-invariant behavior; it does not claim target-host latency, memory, or
real-vault neural-quality measurements.

## Upgrade

```bash
pip install --upgrade power-framework==3.2.5
```

Existing vault notes need no migration. Existing fixed search indexes migrate
on the next sync with a verified readback; an interrupted migration leaves the
previous active search result available.
