# POWER 3.7.1 release boundary

This document records the evidence boundary for the 3.6.7 -> 3.7.1
stabilization line. It is deliberately written as a candidate-release note:
the source tree may be validated locally before the signed tag, immutable
artifacts, and public readback exist.

## Publication gate

The release is not published by this document. A stable claim requires all of
the following to be read back from the public release after the corresponding
workflow succeeds:

- the signed `v3.7.1` tag and matching source revision;
- the exact wheel, source archive, suite manifest, receipt, SPDX SBOM, and
  hashes recorded by the release workflow;
- the independent GUI release and its exact compatible POWER pair;
- the immutable container digest, SBOM, and attestation;
- the final clean-tag validation report, including native, MCP, GUI, lifecycle,
  concurrency, recovery, and upgrade evidence.

Local synthetic tests or a disposable vault do not constitute a
real-vault quality or human-quality claim. Human-quality evidence remains
sealed and is
not inferred from technical test counts.

## Support boundary

The 3.7.1 release boundary is Linux with the repository-declared supported
Python versions. macOS and Windows remain outside the supported release boundary.
The Windows guide is retained as an informational rollback and migration
reference only.

Until the public readback gate is complete, downstream documentation must use
the candidate wording and must not describe `v3.7.1` as available.
