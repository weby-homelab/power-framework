# P.O.W.E.R. 3.7.1 Stable Release Report

Date: 2026-08-22 (Europe/Kyiv)

## Final decision

**NO-GO — POWER 3.7.1 Stable was not achieved.**

The immutable public POWER `v3.7.1` component and compatible GUI `v0.7.7`
artifacts are available and their component publication readback succeeded.
The Suite is not Stable because the mandatory public native clean-install gate
fails. Rewriting the immutable tag or silently replacing its artifacts is
prohibited.

## Source identities

| Component | Tag | Commit | Version |
| --- | --- | --- | --- |
| POWER | `v3.7.1` | `8e172b82b98c8980a83e433744ea2ed6cdedce82` | `3.7.1` |
| GUI | `v0.7.7` | `339388ee4f77401a033ed50d4cac25ad3b82fefd` | `0.7.7` |

No immutable tag was rewritten. Later `3.7.2`/`3.7.3` corrective lines are
separate historical releases and are not used to certify this target.

## Exact public artifacts

- POWER wheel: `power_framework-3.7.1-py3-none-any.whl`, SHA-256
  `486a41b070a00dc519e7ec23adccac89a07a3842e47745734a3ee495ae5ad481`.
- POWER sdist: SHA-256
  `1cfb507f298611b2ddc1800ae202fab3610f9aa5580b5a1a6e0722f6490b19bb`.
- GUI wheel: `power_gui-0.7.7-py3-none-any.whl`, SHA-256
  `8e7904a12abf30e4e458125c36d621ae383caff764a46471223b919dc7591853`.
- GUI sdist: SHA-256
  `be61e84747c82caced4949deb1ef606fb284805867ffb9fb29bbab0995a261de`.
- Constraints: `power-suite-3.7.1-gui-0.7.7.constraints.txt`, SHA-256
  `e0ded6bc17bbbfc38a0834dcd32fad50e2fc3a2d23b03145deca76920e948898`.
- Core/GUI SBOM, release receipts, provenance, and container readback are
  recorded in `release/evidence/public-readback-3.7.1.json`.

## Mandatory gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact pair and public artifact readback | PASS (component scope) | `release/evidence/public-readback-3.7.1.json` |
| Native clean install from public wheels | **FAIL** | `release/evidence/public-native-failure-3.7.1.json` |
| `power-mcp` / MCP contract | PASS for tested component surface; not sufficient to promote Suite | prior release evidence and component receipts |
| Packaged Skill | PASS for the tested 3.7.1 component | component evidence; no human-quality claim |
| Native GUI lifecycle | NOT RUN after the blocking native failure | mandatory gate remains open |
| Cross-runtime concurrency/recovery | NOT RUN as final public Stable proof | mandatory gate remains open |
| Upgrade and rollback | NOT RUN as final public Stable proof | mandatory gate remains open |
| GUI security/accessibility final public flow | NOT RUN as final public Stable proof | mandatory gate remains open |

The reproduced failure is deterministic: on Python 3.14.4, the installer
returns `applied`, but the moved `power`, `power-mcp`, and `power-gui` shims
retain a generated `.venv.staging-*` interpreter path. That staging path no
longer exists, so the public launcher exits `127`.

## Boundaries and policy

- Supported evidence boundary: Linux x86_64, Python 3.14.4 for the reproduced
  failure; no universal Linux claim is made.
- Managed native target remains `~/.local/share/power/venv` with launchers under
  `~/.local/bin`; the public 3.7.1 clean-install gate does not satisfy it.
- Automatic product updates: disabled; no safe suite-aware updater was proven.
- A2A, Federation, MCP Apps, Windows, and macOS: no Stable claims.
- Human retrieval quality: none claimed.
- `M2_HUMAN` opened: **NO**; sealed material remains excluded by policy.
- New material product features: **0**.

## Stale-claim correction

The repository suite manifest is explicitly marked `candidate` with
`release_decision: NO-GO` and `stable_readback: false`. The suite receipt records
the component identities but marks the release `NO-GO`; neither artifact claims
that POWER 3.7.1 Stable exists.

## Open blockers

1. The immutable public 3.7.1 native installer fails on a supported path shape.
2. Because the P0 native gate failed, final Stable lifecycle, cross-runtime,
   upgrade, rollback, and post-publication proof cannot be promoted for this
   target.

## Final decision

**NO-GO. POWER 3.7.1 is not Stable.**
