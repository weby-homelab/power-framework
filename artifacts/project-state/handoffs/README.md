# Project-State Handoffs

Handoffs are concise, timestamped, append-only evidence packets for one POWER
3.8 gate. They allow a new agent to resume from repository-visible evidence
without relying on an old chat transcript.

## Publication status

This branch publishes a **pre-merge blocked-state handoff**. It is not the
canonical post-HF governance branch. The canonical governance bootstrap remains
not started until HF #406 is normally merged and its post-merge gate passes.

## Naming

Use the execution timestamp and a stable gate/status slug:

```text
YYYY-MM-DDTHHMMSSZ_<gate>_<status>.md
```

Examples:

```text
2026-09-07T234142Z_hf-406_pre-merge-blocked.md
2026-09-08TxxxxxxZ_hf-406_post-merge.md
```

The filename records when the gate was executed, not when a later reader opens
or summarizes it.

## Append-only rules

- Historical handoffs are immutable evidence after publication.
- Do not edit an old handoff merely because the project advanced.
- Add a new handoff for each new gate or factual state transition.
- If an unavoidable correction is needed, retain the original text, mark the
  correction with its date and reason, and link the proving evidence.
- A handoff must never rewrite Git history or turn local evidence into merged-main
  evidence.
- Do not include passwords, tokens, private keys, cookies, or unbounded logs.

## Standard schema

Use only fields relevant to the gate, with these names where applicable:

```text
STAGE
PUBLIC_VERSION
STARTING_MAIN
ENDING_MAIN
STATE_BASE_SHA
PR
BASE_SHA
HEAD_SHA
HEAD_TREE
HEAD_PARENT
GPG
MERGE_STATUS
MERGE_SHA
MERGE_PARENTS
TESTS
SKIPPED
DESELECTED
COVERAGE
SECURITY
CI
CODEQL
DOCS
REVIEW_THREADS
WORKTREE
COMPLETED
OPEN_BLOCKERS
NEXT_GATE
AUTHORIZED
NOT_AUTHORIZED
PUBLICATION
```

## Recovery order

1. Read `docs/plans/POWER_3.8_CURRENT_STATE.md`.
2. Read `docs/plans/POWER_3.8_EXECUTION_ROADMAP.md`.
3. Read `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`.
4. Read the latest handoff by timestamp.
5. Fetch live GitHub state through REST API.
6. Verify the documented SHA anchors before any action.

Repository memory is a recovery aid. Mutable GitHub facts always require live
verification.
