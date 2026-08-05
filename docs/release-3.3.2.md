# POWER 3.3.2 release notes

POWER 3.3.2 is a maintenance patch release. It fixes the only confirmed
Windows-specific blocker identified by the 3.3.1 Windows 11 25H2 compatibility
analysis: the physical file move in `power rename`.

## Windows-safe rename overwrite

- `power rename` used `os.rename(old_file, new_file)` for the physical file
  move. On Windows, `os.rename()` raises `FileExistsError` when the destination
  already exists; on POSIX it silently replaces the destination.
- The move now uses `os.replace(old_file, new_file)`, which provides the
  required cross-platform destination-overwrite semantics.
- Regression coverage in `tests/test_rename.py`:
    - the live CLI rename overwrites an existing destination with the source
      content and removes the source;
    - a mock contract asserts the physical operation calls `os.replace` directly,
      so a regression back to `os.rename()` fails even on POSIX CI.

## Validation

- `pytest tests/test_rename.py -v --no-cov` — 3 passed, 1 warning.
- `pytest tests/test_mutation.py -v --no-cov` — 4 passed, 1 skipped, 3 warnings.
- Full framework suite — 683 passed, 35 skipped, 31 warnings, 77.43% coverage.
- `ruff check src tests scripts` — PASS.
- Release contract, documentation-drift, and workspace verification: PASS.

## Explicit limitations

Direct Windows 11 25H2 runtime validation was not executed in this release
environment; the repository CI currently runs on `ubuntu-latest` only. The
cross-platform overwrite contract is covered by the automated regression.
