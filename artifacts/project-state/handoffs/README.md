# Project-State Handoffs

Handoffs are concise, timestamped, append-only evidence packets for one POWER
3.8 gate. They allow a new agent to resume from repository-visible evidence
without relying on an old chat transcript.

## Publication model

A handoff may describe a governance gate, an architecture-planning gate, an
implementation gate, or a validation/release gate. Until its protected PR
merges, the packet and its branch are provisional. After the protected merge,
the packet is canonical evidence for the exact snapshot it names; mutable
GitHub facts still require fresh live verification.

Architecture handoffs use the explicit labels `APPROVED PLANNING DIRECTION`,
`CANONICAL PLANNING`, and `NOT IMPLEMENTED`. A canonical planning handoff is
not phase evidence, runtime completion, or authorization to start the next
implementation gate.

## Naming

Use the execution timestamp and a stable gate/status slug:

```text
YYYY-MM-DDTHHMMSSZ_<gate>_<status>.md
```

Examples:

```text
2026-09-07T234142Z_hf-406_pre-merge-blocked.md
2026-09-08T081335Z_governance-bootstrap_pre-hf.md
2026-09-08T140647Z_context-memory-architecture_planned.md
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
ARCHITECTURE_PLAN
PLANNING_CONTRACTS
PLANNING_STATUS
IMPLEMENTATION_STATUS
PHASE_STATUS
PUBLICATION_STATUS
INDEX_POLICY
LATEST_ARCHITECTURE_HANDOFF
ARCHITECTURE_STATUS
PHASE_5
CURRENT_STATE
ROADMAP
DEVELOPMENT_PROTOCOL
DOMAIN_POLICY
ACCEPTANCE_GATES
PLANNING_STATUS_POINTER
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

1. Read the current state, roadmap, development protocol, architecture plan,
   and planning artifacts from the repository [planning index](https://github.com/weby-homelab/power-framework/blob/main/docs/plans/README.md).
2. Read the latest handoff by timestamp and classify older packets as
   historical evidence. Do not treat a planning packet as implementation or
   phase evidence.
3. Fetch live GitHub state through authenticated REST and independently verify
   the documented SHA anchors, checks, reviews, conversations, branch policy,
   queue, and deployments before any action.
4. If a state pointer exists on the active PR, update that pointer rather than
   creating an unbounded series of duplicate comments.

Repository memory is a recovery aid. Mutable GitHub facts always require live
verification. `mergeable_state=unstable` or `blocked` requires diagnosis and
remediation; neither value alone authorizes a merge or terminates the work.
