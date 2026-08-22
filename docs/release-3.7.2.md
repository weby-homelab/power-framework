# POWER 3.7.2 release boundary

This document records the corrective 3.6.7 -> 3.7.2 stabilization line. The
patch release follows a public NO-GO finding in immutable POWER `v3.7.1`: the
native installer left Python 3.14 shell shims pointing at a removed staging
environment when the home path contained spaces or Unicode characters.

The fix rewrites both ordinary shebangs and staging-root references in moved
console scripts. The corrected suite target is POWER `3.7.2` with the
compatible GUI patch release `0.7.8`.

## Publication gate

The release is not published by this document. A stable claim requires all of
the following to be read back from the public release after the corresponding
workflow succeeds:

- the signed `v3.7.2` tag and matching source revision;
- the exact wheel, source archive, suite manifest, receipt, SPDX SBOM, and
  hashes recorded by the release workflow;
- the independent GUI `v0.7.8` release and its exact compatible POWER pair;
- the immutable container digest, SBOM, and attestation;
- the final clean-tag validation report, including native, MCP, GUI, lifecycle,
  concurrency, recovery, and upgrade evidence.

Local synthetic tests or a disposable vault do not constitute a real-vault quality or human-quality claim.
Human-quality evidence remains sealed and is not inferred from technical test counts.

## Support boundary

The 3.7.2 release boundary is Linux with the repository-declared supported
Python versions. macOS and Windows remain outside the supported release boundary
and are not release platforms. The Windows guide is retained as an informational
rollback and migration reference only.

Until the public readback gate is complete, downstream documentation must use
candidate wording and must not describe `v3.7.2` as available.
