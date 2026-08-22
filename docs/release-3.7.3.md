# POWER 3.7.3 release boundary

This document records the corrective 3.6.7 -> 3.7.3 stabilization line. The
public POWER `v3.7.2` artifact remains immutable, but its deterministic Skill
tree gate exposed generated Python bytecode in installed resource trees. That
cache changed the observed Skill file set and hash after installation, so
`v3.7.2` is not a stable suite release.

The fix excludes `__pycache__` and `.pyc` files from source, wheel-resource,
and installed-target Skill tree walks, and adds a regression test. The
corrective suite target is POWER `3.7.3` with compatible GUI patch release
`0.7.9`.

## Publication gate

The release is not published by this document. A stable claim requires all of
the following to be read back from the public release after the corresponding
workflow succeeds:

- the signed `v3.7.3` tag and matching source revision;
- the exact wheel, source archive, suite manifest, receipt, SPDX SBOM, and
  hashes recorded by the release workflow;
- the independent GUI `v0.7.9` release and its exact compatible POWER pair;
- the immutable container digest, SBOM, and attestation;
- the final clean-tag validation report, including Skill hash equality, native,
  MCP, GUI, lifecycle, concurrency, recovery, and upgrade evidence.

Local synthetic tests or a disposable vault do not constitute a real-vault quality or human-quality claim. Human-quality evidence remains sealed and is not inferred from technical test counts.

## Support boundary

The 3.7.3 release boundary is Linux with the repository-declared supported
Python versions. macOS and Windows remain outside the supported release
boundary and are not release platforms. The Windows guide is retained as an
informational rollback and migration reference only.

Until the public readback gate is complete, downstream documentation must use
candidate wording and must not describe `v3.7.3` as available.
