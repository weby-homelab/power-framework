# POWER 3.2.6 release notes

POWER 3.2.6 is a maintenance release that makes vault mutations safe across
CLI, MCP, threads, and processes.

## Highlights

- All supported vault writers now use one shared mutation boundary.
- Reentrant per-vault locks serialize threads without coupling independent
  vaults.
- A lock file and OS-level advisory lock serialize writers across processes.
- The daemon index worker and process-global active-vault state are gone.
- Read-only coverage inspection does not retain worker or global-vault state.
- Regression tests cover concurrent writers, cancellation, lock ordering,
  failure cleanup, resource warnings, and multi-vault isolation.

## Validation boundary

The source-scoped baseline
`release/evidence/baselines/v3.2.6.json` records the exact release source,
model-lock checksum, frozen synthetic benchmark hashes, and the local
validation boundary. The release does not claim target-host latency, memory,
or real-vault neural-quality measurements.

## Upgrade

```bash
pip install --upgrade power-framework==3.2.6
```

Existing vault data and search generations require no migration.
