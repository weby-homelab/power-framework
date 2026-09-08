# POWER 3.8 — Development Protocol

> This protocol is a repository-facing operating contract. Before a protected
> merge it is provisional; after a protected merge its paths are canonical for
> that snapshot. It never replaces live GitHub facts, exact Git objects, branch
> protection, or an independent gate authorization.

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

## Non-negotiable execution rules

```text
GitHub > chat history
exact SHA > narrative
candidate SHA may change during remediation
candidate SHA change invalidates old evidence, but does NOT terminate the work;
it starts a new candidate audit epoch
mergeable_state alone is not merge authorization and is not an automatic blocker;
actual required policy state must be diagnosed
one gate = one bounded work package
no admin bypass
normal merge preferred
```

These rules apply to both provisional and canonical repository memory. A
candidate or governance branch may advance only through a newly recorded epoch,
fresh validation, and the ordinary protected GitHub policy path.

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
invalidates the evidence for that candidate epoch. A repair, compatibility
change, lock/export regeneration, merge of current `main`, or conflict
resolution may update the candidate; record the new tuple and start a new audit
epoch instead of silently reusing old evidence. Do not merge a different
object under the old approval.

The candidate epoch record must include the new base, head, tree, parent(s),
diff, dependency/export hashes, test and security results, remote checks, and
merge-policy observation. A changed SHA is stale evidence, not a terminal
workflow condition.

## One chat = one gate

One bounded chat handles one major gate. Do not automatically chain:

```text
HF → Actions #396 → Final Integration → Phase 5
```

The current gate is HF #406 admission. Actions #396 and Phase 5 must remain
untouched until a later independent session starts from fresh repository state.

## GitHub publication policy

Use local Git plus the configured GPG key as the canonical path for signed
repository commits and branch publication:

- create the commit locally with `git commit -S`;
- verify it locally with `git verify-commit HEAD`;
- publish through an authenticated HTTPS or SSH Git channel without placing a
  token in a remote URL, command argument, prompt, log, or repository file;
- use authenticated GitHub REST for live state reads, PR/comments, state
  pointers, and the protected normal merge endpoint when authorized.

Do not use admin bypass, protection changes, fake signatures, browser-only
merges, GraphQL bypasses, or ad-hoc remote URL credentials. If the preferred
publication channel fails, try at most one other legitimate authenticated
channel; keep the branch and provisional evidence available if canonical
signing/publication remains blocked.

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
- `mergeable_state` is diagnostic only. `unstable` or `blocked` requires a
  table of required/optional checks, pending/failing checks, reviews and
  requests, conversations, branch freshness, rulesets, queue, deployments, and
  the exact protected merge response; it is not by itself authorization or a
  terminal blocker.
- When the concrete GitHub policy state accepts a normal protected merge, make
  at most one normal `merge_method=merge` attempt for the exact current head
  with an exact-head guard. If GitHub rejects it, record the exact reason and
  remediate rather than blindly retrying.

## Governance publication boundary

The governance publication has two bounded stages:

1. A pre-HF governance snapshot may be created from live `main`, reviewed, and
   normally merged before HF. It records HF as open/blocked and does not start
   Actions #396 or Phase 5.
2. After HF is normally merged, prove the HF head is an ancestor of `main`, run
   post-HF regression/dependency/CI/docs/CodeQL/security gates, and publish a
   new governance update. Only the protected merge makes the snapshot
   canonical; a PR or unsigned REST Contents commit remains provisional.

The retained `docs/power-3.8-premerge-state-publication` PR is historical
provisional evidence/source material. A fresh signed governance branch is the
current publication candidate; its exact branch/PR/head must be verified live.

## GPG and commit integrity

Authoritative implementation and governance commits must be GPG-signed and
verified by GitHub. A local signature alone is insufficient for a canonical
claim. Record signature status and exact object identity in the handoff. The
local gate is:

```bash
git config user.name
git config user.email
git config user.signingkey
gpg --list-secret-keys
git commit -S
git verify-commit HEAD
```

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

For candidate changes, validation must also recompute the candidate epoch when
the head, base, tree, parent, diff, or policy state changes. The old evidence
is retained as historical input and never silently promoted.

Maximum retry discipline:

- one merge attempt per exact gate unless GitHub explicitly reports transient
  failure;
- one fresh state investigation after a merge/policy failure;
- one CI rerun for a proven external infrastructure failure;
- no repeated commands that add no evidence.

## Current stop condition

Current operational state until a fresh guard closes the HF gate:

```text
HF ADMISSION: BLOCKED / NOT MERGED
CANONICAL GOVERNANCE: NOT STARTED
ACTIONS #396: HOLD / NOT STARTED
PHASE 5: BLOCKED / NOT STARTED
PUBLIC VERSION: 3.7.11
POWER 3.8.0: NO-GO
```

The governance line changes to `PRE-HF CANDIDATE / IN PROGRESS` while its
protected PR is under review, and to `CANONICAL` only after merge. Do not start
Actions #396, Phase 5–9, version bumps, tags, releases, release images, or
final release notes.

## Cross-links

- [Current state](POWER_3.8_CURRENT_STATE.md)
- [Execution roadmap](POWER_3.8_EXECUTION_ROADMAP.md)
- [Planning index](README.md)
- [Handoff protocol](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/README.md)
- [Latest governance handoff](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-09-08T084501Z_governance-bootstrap_epoch-3.md)
