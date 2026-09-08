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
        ├── Pre-HF governance snapshot — IN PROGRESS / protected review
        ├── Python admission — DONE
        ├── WEB-01 / WEB-05 — DONE
        ├── HF admission PR #406 — BLOCKED / DIAGNOSIS IN PROGRESS
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
| Pre-HF governance snapshot | IN PROGRESS | Fresh signed branch from live `main`; may merge before HF |
| HF refresh | BLOCKED / DIAGNOSE | PR #406 is open; exact head is not merged; current state is not terminal |
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
3. **HF admission — current blocked gate.** PR #406 starts with an exact
   authorized base, head, tree, and parent. A repair, compatibility fix, lock
   regeneration, or merge of current `main` may create a new candidate epoch;
   old evidence then becomes stale and must be recomputed, not treated as a
   reason to terminate the gate.
4. **Actions admission — next gate only after HF.** PR #396 remains on hold;
   no Actions dependency or workflow changes are authorized here.
5. **Final integration admission — later gate.** It requires independent exact
   evidence for every dependency surface and normal protected merges.

The controlled refresh does not authorize a public version bump, tag, release,
Phase 5, or any later phase.

## HF #406 admission anchor

```text
BASE_SHA:
119d5c39aa2c22734ca72c351f8a70790371678f

HEAD_SHA:
201da2e0e78d1bbf860c98dc653008c0fb4984cd

HEAD_TREE:
c8d66c9bf65c54b09bb9990380313737af63c932

TARGET:
huggingface-hub 1.30.0

SPECIFIER:
>=1.30.0,<1.31.0

LIVE_PR_STATE:
OPEN / NOT MERGED

LIVE_MERGEABILITY:
mergeable=true; mergeable_state=blocked (diagnostic observation)

ADMISSION:
PENDING REQUIRED-POLICY DIAGNOSIS / NORMAL-MERGE TEST
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
- `mergeable_state=unstable` or `blocked`; diagnose the concrete required
  check/policy cause and retry admission only after remediation.
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
- [Latest governance handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T084501Z_governance-bootstrap_epoch-3.md)
