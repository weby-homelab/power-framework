# Changelog

## 3.2.2

- Isolated search databases by stable vault identity, so independent vaults do
  not overwrite one another's FTS, vector, or graph data.
- Staged, validated index generations now publish atomically and retain the
  previous active database if a sync fails.
- Added an evidence manifest schema and documentation-drift checks for release
  claims. See the [3.2.2 release notes](release-3.2.2.md).

## 3.2.1

The release remains a beta evidence record. See
[P.O.W.E.R. 3.2.1 test evidence](tests/P.O.W.E.R.3.2.1-TEST.md) and the
[POWER 3.2 release evidence](release-3.2.md) for scoped results and open gates.

## 3.1.0

See the [POWER 3.1 release evidence](release-3.1.md) and its
[trust-release baseline](adr/0001-power-3.1-trust-release-baseline.md).

## Evidence policy

Claims are classified and validated under
[ADR 0002](adr/0002-memory-os-principles.md). Historical measurements are not
release guarantees without a matching benchmark manifest and raw artifacts.
