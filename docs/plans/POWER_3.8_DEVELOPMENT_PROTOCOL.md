# POWER 3.8 — Development Protocol

> This protocol is published as **PRE-MERGE BLOCKED-STATE EVIDENCE**. It is a
> repository-facing operating contract and does not replace live GitHub facts,
> exact Git objects, branch protection, or an independent gate authorization.

## Source of truth

```text
GitHub live state > chat history
exact Git objects > narrative
remote CI/checks > local claims
repository-native memory > agent memory
evidence > assertion
```

Repository documents are a recovery aid, not a mutable-fact oracle. Every new
agent must read the current documents and then independently verify their SHA
anchors against GitHub REST before acting.

## Evidence hierarchy

Use this order when sources disagree:

1. Git object and GitHub REST object state.
2. GitHub PR, branch-protection, ruleset, review, and check state.
3. Remote CI artifacts attached to the exact SHA.
4. Merged repository evidence and authoritative phase reports.
5. Local reproduction and local worktree evidence.
6. Handoff and other narrative reports.
7. Chat history.

Labels must be precise:

- **LOCAL CANDIDATE** — local worktree or branch only.
- **REMOTE EXACT-HEAD** — evidence attached to the exact PR head.
- **MERGED MAIN** — evidence attached to an exact protected merge on `main`.
- **FINAL INTEGRATION** — evidence after all declared gates are admitted.

Candidate evidence must never be called `MERGED MAIN` or `FINAL INTEGRATION`.

## Exact-head principle

An authorization is valid only for the exact tuple:

```text
PR number
base SHA
head SHA
head tree SHA
head parent(s)
```

For HF #406 the inspected tuple is:

```text
PR: 406
BASE: 119d5c39aa2c22734ca72c351f8a70790371678f
HEAD: 201da2e0e78d1bbf860c98dc653008c0fb4984cd
TREE: c8d66c9bf65c54b09bb9990380313737af63c932
PARENT: 119d5c39aa2c22734ca72c351f8a70790371678f
```

Any change to the PR, base, head, tree, parent, diff, or relevant policy
invalidates the authorization. Do not rebase, update the branch, or merge a
different object under the old approval.

## One chat = one gate

One bounded chat handles one major gate. Do not automatically chain:

```text
HF → Actions #396 → Final Integration → Phase 5
```

The current gate is HF #406 admission. Actions #396 and Phase 5 must remain
untouched until a later independent session starts from fresh repository state.

## GitHub publication policy

All GitHub state-changing and publication operations use **GitHub REST API only**:

- create/update refs, Git objects, commits, files, comments, and pull requests;
- merge pull requests only through the REST merge endpoint;
- use `merge_method=merge` for an authorized normal merge commit.

Do not publish through `gh`, GraphQL, browser UI, direct `git push`, or ad-hoc
remote URL credentials. Read-only local Git commands may inspect objects and
signatures, but they do not publish repository state.

The GitHub credential is host-local and must be injected only in memory. Never
print, paste, commit, log, URL-encode, or place it in command arguments, remote
URLs, prompts, handoffs, or repository files. If authenticated REST state is
not observable, stop; do not ask an agent to guess or bypass the missing policy.

## Merge policy

The required merge method is a **normal merge commit** when a gate is admitted.

- Revalidate PR, base, head, tree, checks, reviews, policy, and mergeability
  immediately before one merge attempt.
- No administrator bypass.
- No protection bypass.
- No force push.
- No auto-merge.
- No merge queue override.
- No temporary protection or ruleset modification.
- If `mergeable_state` is not a normal admission state, stop.

The current `mergeable_state=unstable` is a blocker, not an invitation to retry
or bypass.

## Governance publication boundary

The post-HF canonical governance bootstrap begins only after:

1. HF #406 is normally merged under the exact authorization.
2. The authorized HF head is proven an ancestor of `main`.
3. Post-HF regression, dependency, CI, docs, CodeQL, and security gates pass.

This branch is an explicitly named **blocked-state evidence publication**. It is
not the canonical post-HF governance branch, and its files must not be treated
as proof that HF or governance has merged.

## GPG and commit integrity

Authoritative implementation and governance commits must be GPG-signed and
verified by GitHub. A local signature alone is insufficient for an authoritative
claim. Record signature status and exact object identity in the handoff.

## Evidence commits

Do not create a trailing evidence commit solely to replace a previously unknown
final SHA. The commit being evaluated must contain the intended content, and
the final merge SHA must be resolved from live GitHub state after the merge.

## Handoff discipline

Every gate produces one timestamped, append-only handoff. A handoff must contain
exact SHAs, state labels, evidence links, blockers, and the next authorized gate;
it must not paste secrets or unbounded logs. Historical handoffs are retained as
historical snapshots and are never silently rewritten as current state.

## Plan → Act → Validate

Each bounded action follows PAV:

1. **Plan:** state scope, exact objects, authority, and stop conditions.
2. **Act:** make one isolated change only in the authorized paths.
3. **Validate:** inspect added and removed content, run the applicable checks,
   verify signatures and live REST state, and mark unknowns `UNVERIFIED`.

Maximum retry discipline:

- one merge attempt per exact gate unless GitHub explicitly reports transient
  failure;
- one fresh state investigation after a merge/policy failure;
- one CI rerun for a proven external infrastructure failure;
- no repeated commands that add no evidence.

## Current stop condition

Until a fresh independent guard proves normal merge admission for exact PR #406:

```text
HF ADMISSION: BLOCKED / NOT MERGED
CANONICAL GOVERNANCE: NOT STARTED
ACTIONS #396: HOLD / NOT STARTED
PHASE 5: BLOCKED / NOT STARTED
PUBLIC VERSION: 3.7.11
POWER 3.8.0: NO-GO
```

Do not start Actions #396, Phase 5–9, version bumps, tags, releases, release
images, or final release notes.

## Cross-links

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Planning index](README.md)
- [Handoff protocol](../../artifacts/project-state/handoffs/README.md)
- [Latest blocked-state handoff](../../artifacts/project-state/handoffs/2026-09-07T234711Z_hf-406_pre-merge-blocked.md)
