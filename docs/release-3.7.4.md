# POWER 3.7.4 release boundary

This document records the corrective 3.6.7 -> 3.7.4 stabilization line. The
public POWER `v3.7.3` component remains immutable, but it cannot certify a
Stable Suite: its native installer populates a temporary venv, moves it, and
repairs generated launchers afterward. Its tag-bound Suite manifest also does
not bind the published POWER 3.7.3 and GUI 0.7.9 pair.

POWER 3.7.4 replaces that installer architecture with final-location release
slots. Each venv is created and populated at its permanent physical path,
slot-local launchers are executed, a `current` symlink is switched atomically,
and user-facing launchers are executed before an `applied` receipt is written.
The previous verified slot and any legacy managed venv are preserved for the
documented rollback boundary.

The Suite manifest v2 contract additionally binds the exact GUI POWER
requirement, Application schema, dependency constraints, and the Skill tree
embedded in the POWER wheel. A reusable native-candidate harness emits the
machine-readable `power.native-candidate-validation.v1` receipt for the same
artifact inputs used on the WS, CI, and public readback paths.

The corrective Suite target is POWER `3.7.4` with compatible GUI patch
`0.7.10`. These are candidate identities until every mandatory prepublication
and public consumer gate passes.

## Publication gate

This document does not publish a release. A Stable claim requires all of the
following to be read back after the corresponding signed-tag workflows finish:

- the signed `v3.7.4` tag and exact wheel/source identities;
- the Suite v2 manifest, constraints, validation receipt, SPDX SBOM, and
  provenance;
- the independent GUI `v0.7.10` artifact and exact pair identity;
- Python 3.13 and 3.14 native matrices, including normal, spaces, Unicode, and
  spaces-plus-Unicode HOME paths;
- non-root native, Skill, MCP, native GUI, upgrade, rollback, container, and
  cross-runtime gates inside the declared Linux support boundary.

Local synthetic tests or a disposable vault do not constitute a
real-vault quality or human-quality claim. M2_HUMAN remains sealed.
macOS and Windows remain outside the supported release boundary.
