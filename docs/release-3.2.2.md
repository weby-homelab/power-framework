# POWER 3.2.2 release notes

POWER 3.2.2 strengthens the local-first indexing contract without changing the
public command surface.

## Highlights

- Each vault receives a stable local identifier and an isolated SQLite search
  database. `POWER_SEARCH_DB` remains available as an explicit test override.
- `power sync` builds a staged generation, verifies source coverage and SQLite
  integrity, then atomically promotes it. A failed build leaves the previous
  active generation available.
- Background sync and graph extraction use the same vault-local database.
- Release evidence now has a machine-validatable manifest schema; documentation
  claims are checked for drift in CI.

## Validation

The release gate runs the hermetic Python suite with its 70% coverage floor,
Ruff, MyPy, the documentation-drift check, and a strict MkDocs build. No
production-quality or target-hardware RSS claim is introduced by this release.

## Upgrade

Existing vaults are migrated lazily: the next `power sync <vault>` creates the
vault metadata and a new isolated index. The old shared cache is not deleted
automatically, so rollback remains possible.
