# POWER 3.7.1 release boundary — NO-GO

This document records the evidence boundary for the 3.6.7 -> 3.7.1
stabilization line. The immutable public `v3.7.1` component release exists, but
the requested POWER Suite 3.7.1 Stable claim is **NO-GO**.

The public consumer gate reproduced a mandatory native-install failure on
Python 3.14 with a HOME path containing spaces and Unicode: installation
reported `applied`, while the moved `power`, `power-mcp`, and `power-gui`
console shims still referenced the removed `.venv.staging-*` environment. The
content-free reproduction is recorded in
`release/evidence/public-native-failure-3.7.1.json`.

This immutable result cannot be repaired by moving or rewriting `v3.7.1`.
Later patch lines are separate historical corrections and do not promote this
3.7.1 suite to Stable.

## Publication gate

The following are the required stable gates; the native gate failed, so the
stable claim is not permitted:

- the signed `v3.7.1` tag and matching source revision;
- the exact wheel, source archive, suite manifest, receipt, SPDX SBOM, and
  hashes recorded by the release workflow;
- the independent GUI release and its exact compatible POWER pair;
- the immutable container digest, SBOM, and attestation;
- the final clean-tag validation report, including native, MCP, GUI, lifecycle,
  concurrency, recovery, and upgrade evidence.

Component artifact publication/readback is not sufficient to close the suite
gate. The exact public component identities remain recorded for audit and are
not presented as a Stable Suite claim.

Local synthetic tests or a disposable vault do not constitute a
real-vault quality or human-quality claim. Human-quality evidence remains
sealed and is
not inferred from technical test counts.

## Support boundary

The 3.7.1 release boundary is Linux with the repository-declared supported
Python versions. macOS and Windows remain outside the supported release boundary.
The Windows guide is retained as an informational rollback and migration
reference only.

Downstream documentation must use candidate/NO-GO wording and must not
describe the POWER `v3.7.1` Suite as Stable or available.
