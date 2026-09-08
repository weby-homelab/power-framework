# Project-State Handoffs

Handoffs are concise, timestamped, append-only evidence packets for one POWER
3.8 gate. They allow a new agent to resume from repository-visible evidence
without relying on an old chat transcript.

## Publication status

The repository may publish a **pre-HF governance snapshot** before HF #406 is
merged. Until its protected PR merges, that branch/PR is provisional; after the
protected merge, the same paths are canonical for that snapshot. A later
post-HF update is still required and must not rewrite this packet.

## Naming

Use the execution timestamp and a stable gate/status slug:

```text
YYYY-MM-DDTHHMMSSZ_<gate>_<status>.md
```

Examples:

```text
2026-09-07T234142Z_hf-406_pre-merge-blocked.md
2026-09-08T081335Z_governance-bootstrap_pre-hf.md
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
OBSERVED_AT_UTC
CANDIDATE_EPOCH
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

`CANDIDATE_EPOCH` identifies the exact tuple and reason for any rebuild:

```text
PR + BASE_SHA + HEAD_SHA + HEAD_TREE + HEAD_PARENT(s) + relevant policy snapshot
```

If a candidate SHA, base, tree, parent, diff, lock/export hash, or policy state
changes, retain the old evidence, record a new epoch, recompute the required
tests/security/checks, and publish a new handoff. A changed candidate is not a
reason to stop by itself.

## Recovery order

1. Read the current state, roadmap, and development protocol from the
   repository [planning index](https://github.com/weby-homelab/power-framework/blob/main/docs/plans/README.md).
2. Read the latest handoff by timestamp and classify older packets as
   historical evidence.
3. Fetch live GitHub state through authenticated REST and independently verify
   the documented SHA anchors, checks, reviews, conversations, branch policy,
   queue, and deployments before any action.
4. If a state pointer exists on the active PR, update that pointer rather than
   creating an unbounded series of duplicate comments.

Repository memory is a recovery aid. Mutable GitHub facts always require live
verification. `mergeable_state=unstable` or `blocked` requires diagnosis and
remediation; neither value alone authorizes a merge or terminates the work.
