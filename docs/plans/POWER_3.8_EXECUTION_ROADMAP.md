# POWER 3.8 — Execution Roadmap

> This roadmap is a repository-visible governance projection. Before a
> protected merge it is provisional; after a protected merge its paths are
> canonical for that snapshot. It is not a release authorization and does not
> replace live GitHub state, exact Git objects, or protected merge policy.

## Canonical execution sequence

```text
POWER 3.7.11
DONE / PUBLIC / FROZEN
        ↓
Phase 0
CLOSED / FROZEN
        ↓
Phase 1
CLOSED / FROZEN
        ↓
Phase 2
CLOSED / FROZEN
        ↓
Phase 3
CLOSED / FROZEN
        ↓
Phase 4
CLOSED / FROZEN
        ↓
Controlled Dependency Refresh
        ├── Pre-HF governance snapshot — CLOSED / PR #408 MERGED
        ├── Python admission — DONE
        ├── WEB-01 / WEB-05 — DONE
        ├── CI admission repair PR #410 — CLOSED / MERGED
        ├── HF admission PR #406 — CLOSED / MERGED
        ├── Actions admission PR #396 — NEXT AFTER HF / HOLD / NOT STARTED
        └── Final integration admission — BLOCKED
        ↓
Phase 5 — Context Compiler & MCP
BLOCKED / NOT STARTED
        ↓
Phase 6 — Agent Capture & Integrations
NOT STARTED
        ↓
Phase 7 — Materialized Views & Web
NOT STARTED
        ↓
Phase 8 — Security / Reliability / Performance
NOT STARTED
        ↓
Phase 9 — Migration / Benchmark / Release
NOT STARTED
        ↓
POWER 3.8.0
NO-GO
```

## Current status markers

| Work item | Status | Meaning |
|---|---|---|
| Public `3.7.11` | DONE / PUBLIC | Stable public baseline; no version bump |
| Phases 0–4 | DONE / FROZEN | No reopening in this gate |
| Python refresh | DONE | Prior controlled admission |
| WEB-01 / WEB-05 | DONE | Closed through security PR #405 |
| Pre-HF governance snapshot | CLOSED | PR #408 protected merge is on `main` |
| CI admission repair | CLOSED | PR #410 protected merge is on `main` |
| HF refresh | CLOSED | PR #406 protected merge and post-merge checks are on `main` |
| Actions #396 | NEXT AFTER HF / HOLD | Do not inspect or modify in this gate |
| Final integration | BLOCKED BY HF | Requires separate admissions |
| Phase 5 | BLOCKED / NOT STARTED | No implementation authorized |
| Phases 6–9 | NOT STARTED | No work authorized |
| POWER 3.8.0 | NO-GO | No tag, release, or public version change |

## Controlled Dependency Refresh

The refresh is a sequence of independent gates, not one undifferentiated
dependency update:

1. **Python admission — complete.** Preserve its merged evidence.
2. **WEB-01 / WEB-05 — complete.** Security boundaries are closed through PR
   #405 and must not be reopened as part of HF work.
3. **CI admission repair — complete.** PR #410 fixed the missing PR-associated
   Docs `build` context for dependency-only changes and was normally merged.
4. **HF admission — complete.** PR #406 was refreshed through three candidate
   epochs, passed exact dependency/security/CI admission, and was normally
   merged. Its final merge is recorded below.
5. **Actions admission — next gate only after HF.** PR #396 remains on hold;
   no Actions dependency or workflow changes are authorized here.
6. **Final integration admission — later gate.** It requires independent exact
   evidence for every dependency surface and normal protected merges.

The controlled refresh does not authorize a public version bump, tag, release,
Phase 5, or any later phase.

## HF #406 admission anchor

```text
BASE_SHA:
7ed70766904e394d9717fe3fb7e18ed079e1887b

HEAD_SHA:
c385073583dc00dc7752169eb36f66ecdd7f4361

HEAD_TREE:
a5f63eb671d3d57dd304d497cef4c03c52ed340b

HEAD_PARENTS:
75f3d7dad242566887fe77b5c64cd5b64aaa0576, 7ed70766904e394d9717fe3fb7e18ed079e1887b

MERGE_SHA:
2d8058854ffbfae8526095af9809ab2c6f9c04f6

TARGET:
huggingface-hub 1.30.0

SPECIFIER:
>=1.30.0,<1.31.0

LIVE_PR_STATE:
MERGED / CLOSED

LIVE_MERGEABILITY:
N/A after merge; pre-merge exact state was mergeable=true / mergeable_state=clean

ADMISSION:
CLOSED / POST-MERGE VERIFIED
```

`mergeable_state` alone is neither merge authorization nor an automatic stop.
For each candidate, record the required and optional check-runs, pending or
failed checks, required reviews and requests, unresolved conversations, branch
freshness, rulesets, merge queue, deployment requirements, and the result of
the protected normal-merge admission test. Only GitHub policy acceptance for
the exact current head can close the gate.

## Candidate epoch rule

The candidate tuple is:

```text
PR number + base SHA + head SHA + head tree SHA + parent(s)
```

If any tuple member, relevant diff, lock/export hash, or policy state changes:

1. record the new head/tree/parent/base and the reason;
2. recompute the diff and all hashes;
3. rerun targeted local tests, security checks, and the required remote CI;
4. re-check the live merge policy; and
5. publish a new handoff/state pointer.

This is a new candidate audit epoch, not a workflow stop condition.

## Phase 5–9 boundaries

Phase 5 may eventually cover the Context Compiler, ContextPacks, governed
context assembly, and MCP project-state tools. It begins only after the full
controlled dependency refresh is admitted and separately authorized.

Phases 6–9 remain future work. Internal planning may retain these labels:

```text
3.7.12 forensic architecture
3.7.13 contracts/schema/tests
3.7.14 capture runtime
3.7.15 Codex adapter
3.7.16 multi-agent adapters
3.7.17 working memory/curation
3.7.18 durable temporal memory/living models
3.7.19 context broker
3.7.20 canonical POWER integration
3.7.21 security/privacy/forgetting
3.7.22 full validation/RC
```

These are **INTERNAL WORK-PACKAGE LABELS — NOT PUBLIC RELEASES**. They do not
authorize tags, GitHub releases, version bumps, or release artifacts.

## Roadmap remediation conditions

Treat the following as remediation inputs rather than automatic stops:

- HF base, head, tree, parent, diff, or PR state changes after authorization;
  start a new candidate epoch and recompute evidence.
- `mergeable_state=unstable`, `blocked`, or `unknown`; diagnose the concrete
  required check/policy cause and retry admission only after remediation.
- A required check fails; inspect its logs, apply a minimal related fix, and
  rerun the bounded gate.
- Required policy is not observable through one interface; use the approved
  authenticated fallback channels without exposing credentials.
- A source, dependency, workflow, version, or release file appears in a docs
  publication change; remove the unrelated scope before publication.

Stop only when a human-only approval/permission is objectively required after
the reviewer/request path is exhausted, a secret is lawfully unavailable, a
security remediation remains impossible after three meaningful cycles, or a
history/data-loss risk is demonstrated. Do not use admin bypass, protection
disablement, fake approval, or force merge. A later agent must not start
Actions #396 or Phase 5 before the HF gate is closed.

## Cross-links

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Latest HF post-merge handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T095310Z_hf-406_post-merge.md)
