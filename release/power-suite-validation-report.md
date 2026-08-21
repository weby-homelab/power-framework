# POWER Suite validation report

Date: 2026-08-21

Status: candidate validation complete; stable publication is **NO-GO** until the
open release gates below are closed with external readback evidence.

## Scope and source identity

This report covers the requested 3.6.7 hardening, the blocker-only 3.6.8
review, and the 3.7.0 stable-suite gates. `M2_HUMAN` remains excluded and the
sealed human-evaluation material was not opened.

| Component | Candidate base | Tag readback | Implementation commit |
| --- | --- | --- | --- |
| POWER | `origin/main` `527cc8a77187e9fa6d724b604d1a6634545da575` | `v3.6.6` → `6c6b6ae52f4b29382f0d2ec82fbb4e75ba1f471a` | `08ca9326dc849921db0c61a852ecb83cd6dd96b0` |
| POWER-GUI | `origin/main` `068b4d32d5d55170de52c81a897526e3d640078a` | `v0.7.4` → `f1c918c7a8c6de011ff0553f08d00675ad296f59` | `b8001e1e5d3f57ed679b6941c6d0a12a752c931e` |

Both implementation commits are signed with GPG key `2D49E810C7F2527E` and
the required `weby-homelab <rekvizitor.ua@gmail.com>` identity.

The feature branches are clean and PR-ready:

- POWER: `feature/power-suite-3.7`, signed handoff evidence commit `815256aa8d9bbdd48a1f276729830c3999b914cb`;
- POWER-GUI: `feature/power-gui-suite-3.7`, local HEAD `b8001e1e5d3f57ed679b6941c6d0a12a752c931e`.

No remote feature branch or PR was created because the configured GitHub
credentials are invalid (`gh auth status` reports invalid `GITHUB_TOKEN` and
account token). No token was read from or written to a file, and no push, merge,
tag, or publication was attempted.

## 3.6.7 implementation gates

The following local gates passed:

- Official MCP Python SDK v2 is the runtime adapter. `power-mcp` is the public
  console entry point; `python -m power_framework.mcp` remains compatibility
  only. Real subprocess tests cover both legacy initialization and protocol
  version `2026-07-28`; stdout remains wire-clean.
- All 20 MCP tools expose output schemas, annotations, bounded risk metadata,
  and the deterministic tool-contract hash
  `bb4a0790eeb7c47138917508d8556a1f45c8a311995f552388499183b195755c`.
- Mutating MCP paths delegate through `ApplicationService`; the AST boundary
  test reports no low-level mutator bypass. Two independent source CLI
  processes also completed a same-vault mutation test with the lock and
  resulting notes intact.
- The packaged Skill tree contains five files and has SHA-256
  `c30126eafca2e3890a0441f9e6803cde88750c16ada975df6fde5a66e81df3d1`. The
  generic installer was planned and atomically applied to the three managed
  targets under `/root/.agents`, `/root/.opencode`, and
  `/root/.config/opencode`; all target trees match the source hash.
- The managed native installer was run in a disposable HOME with the exact
  wheel pair. It created only the managed venv and launchers, produced a
  `power.native-install.v1` receipt, reported POWER `3.6.6` and GUI `0.7.4`,
  passed `power-mcp preflight`, and did not mutate system Python.
- The canonical user unit is loopback-only, opt-in, uses a bounded restart
  policy, and has no system-level `User=`/`Group=` mutation. Its syntax passes
  `systemd-analyze verify`; live enable/start was intentionally not performed
  in the real HOME, so lifecycle evidence remains open.
- The GUI container candidate was built from the pinned Python base image
  `sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317`.
  Local image ID is
  `sha256:017970ee75b40c1ea16f39c8ecaaf5e33c4da7dbebfc8a5d182f09ebdc0d2b26`.
  A disposable run returned `/healthz` version `3.6.6`, returned HTTP 200 for
  `/login`, ran as UID/GID `10001`, used `cap_drop=ALL`,
  `no-new-privileges:true`, and kept `/data` as rebuildable cache state.

## Verification commands and results

| Surface | Command/result |
| --- | --- |
| POWER full suite | `POWER_EMBED_DEVICE=cpu POWER_RERANKER_DEVICE=cpu uv run --extra dev --extra rerank python -m pytest --no-cov -q` → **1150 passed, 11 skipped, 2 warnings** |
| GUI full suite | `uv run --extra dev python -m pytest -q` → **54 passed, 3 skipped, 1 warning** |
| MCP/integration focus | `uv run --extra dev --extra mcp python -m pytest --no-cov -q` over entrypoint, packaging, onboarding, boundary, server, integrations and cross-process tests → **69 passed** |
| POWER formatting/lint | Ruff format check and Ruff check → **pass** |
| GUI formatting/lint | Ruff format check and Ruff check → **pass** |
| POWER static types | `uv run mypy src/power_framework` → **Success: no issues found in 77 source files** |
| Public documentation drift | `uv run python scripts/check_doc_drift.py --check interfaces,onboarding,clients` → **pass** |
| Wheel packaging | POWER and GUI wheels built successfully; POWER wheel contains all five Skill files |

The first inherited automatic/CUDA test invocation was not used as a release
gate because this host has no CUDA execution provider. The explicit CPU gate
above is the canonical reproducible result and passed in full.

The Web Interface Guidelines review also passed as a static product gate after
the GUI accessibility hardening commit: form controls have associated labels,
the skip link and focus-visible ring remain present, `transition: all` and
focus-outline suppression were removed from the owned stylesheet, and a
`prefers-reduced-motion` fallback is present. The graph keeps its accessible
table fallback. This is static evidence; it does not replace the still-open
live native GUI lifecycle gate.

The required read-only startup health check
`uv run power doctor /root/geminicli/brain --json` returned an environment
error, not a candidate-code failure: five existing prompt/strategy notes are
excluded for invalid metadata and the current index has a coverage mismatch.
Those user-owned vault notes were not modified. The native integration doctor
also correctly reports the live `/root/.local` profile as incomplete because
the verified installer was run only in disposable HOME roots.

## Artifact and supply-chain evidence

| Artifact | SHA-256 or status |
| --- | --- |
| `power_framework-3.6.6-py3-none-any.whl` | `cf853aa73aca5847c43e8097be335c49196a17149eb88a931a000765f85fb512` |
| `power_gui-0.7.4-py3-none-any.whl` | `aef46cdde6baa3c88f407e8966ffe66acb16fdaf19198d0cf65edeb2b329bffc` |
| Local POWER CycloneDX 1.5 export | `233f99862dc68189deba59a5206cb95d0e0bfde67772048f23f47ca6966ad7a0` |
| Local GUI CycloneDX 1.5 export | `48a7357395e014442d4ec1913e73e6fa66676fa22cad3d89df5938ca944a20b2` |
| Published suite SBOM/digest | **not available** |
| Signed release attestation | **not available** |

The local CycloneDX hashes were calculated from `uv export` output and are
evidence of the checked lockfiles, not a substitute for a published SBOM or
attestation bound to a registry artifact. Automatic product updates remain
disabled under `release/power-suite-updater-policy.md`.

## 3.6.8 and 3.7.0 decisions

3.6.8 is **SKIP**: its blocker-only scope produced no additional code blocker
after the 3.6.7 gates passed.

3.7.0 is **NO-GO** for publication, even though the local implementation gates
are green. The remaining required evidence is:

- B6: final suite manifest publication and external artifact/readback identity;
- B7: an actual opt-in `systemd --user` install, start, restart, stop, and
  readback test in a disposable user profile;
- B8: published container digest plus release SBOM and signed attestation;
- B9: host CLI/MCP and container GUI concurrent mutation/recovery against one
  disposable vault, including a verified failure/recovery path.

The local host cross-process test, native installer, and container health/security
smoke do not claim those missing external gates. No product feature ring was
added to hide the blockers.

## Subagent advisory record

Antigravity-cli was invoked with Gemini 3.7 Flash high effort and OpenCode was
used for independent read-only audits. Their output was treated as advisory:
the useful OpenCode findings identified stale FastMCP/packaging/doc contracts,
which were corrected and then covered by the gates above. No subagent was
allowed to publish artifacts, open sealed M2 material, or override the
ApplicationService/source-of-truth boundary.
