# POWER 3.8 — Execution Roadmap

> This roadmap is published as **PRE-MERGE BLOCKED-STATE EVIDENCE** on the
> documentation branch. It is not a release authorization and does not replace
> live GitHub state, exact Git objects, or protected merge policy.

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
        ├── Python admission — DONE
        ├── WEB-01 / WEB-05 — DONE
        ├── HF admission PR #406 — BLOCKED / NOT MERGED
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
| HF refresh | BLOCKED | PR #406 is open; exact head is not merged |
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
3. **HF admission — current blocked gate.** PR #406 must retain its exact
   authorized base, head, tree, and parent until a fresh guard passes.
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
mergeable=true; mergeable_state=unstable

ADMISSION:
BLOCKED
```

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

## Roadmap stop conditions

Stop immediately when any of the following occurs:

- HF base, head, tree, parent, diff, or PR state changes after authorization.
- `mergeable_state` is not a normal protected-merge admission state.
- Required policy, reviews, checks, or branch protection are not fully
  observable.
- A source, dependency, workflow, version, or release file appears in a docs
  publication change.
- A later agent attempts Actions #396 or Phase 5 before the HF gate is closed.

## Cross-links

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Development protocol](POWER_3.8_DEVELOPMENT_PROTOCOL.md)
- [Planning index](README.md)
- [Handoff protocol](../../artifacts/project-state/handoffs/README.md)
- [Latest blocked-state handoff](../../artifacts/project-state/handoffs/2026-09-07T234711Z_hf-406_pre-merge-blocked.md)
