# POWER 3.7.11 change reconciliation

Baseline: `origin/main` / local `HEAD` `1a9879ee2353d63d979da5f68e79a6065122343b`

PR #381 head: `7930e22f5fe548ab7a38e204ca9c5b207fadb552`
Local branch: `fix/power-3.7.11-critical-stabilization` (dirty, not published)

| Path or feature | `main` state | PR #381 state | Local WS state | Final 3.7.11 action |
|---|---|---|---|---|
| `.github/workflows/release.yml` | 3.7.10 release workflow | tag/release-control and attestation hardening, plus historical closure flow | native lock asset, tag-bound control checkout and readback changes | manually merge only current tag/provenance, lock and public-readback requirements |
| `scripts/generate_release_receipt.py` | 3.7.10 receipt contract | release-control and attestation provenance fields | native dependency-lock subject binding | combine immutable tag/workflow provenance with lock subject binding |
| `scripts/verify_public_release_bindings.py` | public asset/hash verifier | exact release provenance verifier additions | exact artifact set, wheel/Skill/MCP and dependency-lock checks | retain both; reject mixed provenance and obsolete asset sets |
| `scripts/verify_attestation_provenance.py` | absent | exact subject/predicate/signer/source/ref/event/run policy | absent | port PR implementation, then extend tests for native lock and final workflow contract |
| `src/power_framework/web/auth/csrf.py` | existing implementation | fail-closed settings validation | unchanged | port only the validated CSRF fix and its tests |
| `src/power_framework/core/source_service.py` | source scan implementation | small source/task logging change | symlink-safe vault scan | manually combine behavior; keep vault boundary as canonical |
| `src/power_framework/core/task_service.py` | task migration implementation | small task-state adjustment | `.power` control-state boundary hardening | manually reconcile without importing historical behavior |
| `src/power_framework/core/task_store.py` | task persistence | small task-state adjustment | safe control directory and symlink checks | manually reconcile and test fresh/upgrade/rollback paths |
| `scripts/prxmx_power_runtime_audit.py` | current public audit | 3.7.10 closure/readback behavior | unchanged | do not import historical closure bulk; use only independently required current verifier logic |
| `release/evidence/3.7.10-postrelease/` | absent | historical 3.7.10 evidence bulk | absent | exclude from 3.7.11 candidate |
| `skills/power/` and `.agents/skills/power/` | 3.7.10 prose | no current release Skill rewrite | unchanged so far | synchronize to 3.7.11 and runtime-schema truth |

## Ownership decisions

1. The dirty WS worktree owns the 3.7.11 native installer, MCP contract, vault
   boundary, dependency-lock and release-asset changes.
2. PR #381 is a source of reusable provenance and CSRF hardening only; it is
   not merged wholesale and its 3.7.10 closure evidence is excluded.
3. Every overlapping release file gets one combined implementation. No
   cherry-pick is performed while the worktree is dirty.
4. Historical evidence remains immutable and is not used as 3.7.11 proof.
