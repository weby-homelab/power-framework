# POWER 3.8 Pre-Phase-5 Foundation Hardening Handoff

> Append-only candidate handoff. The Foundation implementation is not
> `MERGED MAIN` until the exact candidate passes protected GitHub admission and
> is independently read back after one normal merge. It does not start Phase 5.

## PROJECT

```text
PROJECT: POWER Framework 3.8
REPOSITORY: https://github.com/weby-homelab/power-framework
PUBLIC_VERSION: 3.7.11
ACTIVE_NODE: WS
CHECKOUT: /root/gemma/projects/P.O.W.E.R
BRANCH: feat/power-3.8-foundation-hardening
```

## STARTING VERIFIED MAIN

```text
STARTING_MAIN: 95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a
STARTING_TREE: 28f99fc71d6e163a242d7782ae87040805e79faf
STARTING_PARENTS: a386858a45489eb5db213d42ffe773db9134ff88 bcd882815cbb7b2fe33d672b83421d98eefaaf48
STARTING_MAIN_GITHUB: verified=true / reason=valid
STARTING_BRANCH_PROTECTION: strict=true / enforce_admins=true / required_approvals=0 / signatures=true
```

Required contexts at the starting read were `test (3.13)`, `test (3.14)`,
`security`, `package-smoke`, `upgrade-matrix (ubuntu-latest)`,
`upgrade-matrix-aggregate`, `base-runtime-smoke`, `benchmark-integrity`,
`analyze (python)`, `CodeQL`, and `build`. No open PR existed at the starting
read; PR #413 was already protected-merged into this main.

## FOUNDATION RESULTS

### F1 — Explicit mutation authority

ApplicationService mutation entry points now fail closed on `context=None`,
read-only context, invalid/expired principal, or missing apply authority where
the operation writes canonical state. Web apply approval is required, parses
only the exact string `true`, and has no truthy default. PowerClient approval is
keyword-only and has no default. MCP write tools require explicit
`approved=True` where they perform a write; proposal intent remains separate.
CLI actor input remains attribution only.

### F2 — Principal/session binding

The core `Principal` contract distinguishes `WEB_SIGNED_SESSION`, `LOCAL_CLI`,
`LOCAL_MCP_STDIO`, and `SYSTEM_INTERNAL`. It carries an opaque reference,
binding type, validity, and optional expiry without storing credentials. Web
middleware preserves the verified signed-session subject only long enough to
issue a hashed reference with the token's actual expiry; auth-disabled Web is
trusted only on a loopback bind. MCP derives its principal from the local stdio
server, and CLI derives a local-process principal. `actor` remains a separate
attribution field. Web request IDs reach PowerClient/ApplicationService; MCP
call metadata carries its server-derived correlation ID.

### F3 — Retrieval boundary

ApplicationService default retrieval injects `allow_search_db_override=False`;
the legacy `POWER_SEARCH_DB` path remains an explicit lower-level
test/developer compatibility API. Web, MCP search, MCP diagnostics, and the
MCP synthesis graph projection use the configured vault/cache boundary.
Control-subdirectory symlinks are rejected, and CLI rename targets use the
existing vault containment helper. Existing source projection, safe relative
paths, non-symlink reads, and WEB-01/WEB-05 boundaries were retained.

### F4 — Bounded failure receipts

Configured ApplicationService audit hooks receive bounded failure receipts with
operation, outcome/status, request ID, idempotency key, empty-result digest,
principal reference/binding, error category, duration, and budget metadata.
Raw exception text, traceback, request body, note content, and credentials are
not copied. Successful `power.receipt.v1` serialization retains its historical
wire shape; principal metadata is present on the application envelope and on
failure receipts. Proposal, ingest/synthesis, task, and decision idempotency
replay paths reject conflicting reuse. MCP errors are bounded/redacted and MCP
call results include `power.request_id` metadata.

### F5 — Deadline/concurrency/result semantics

`RequestContext` supports a monotonic absolute deadline derived from a positive
budget, plus a caller-lower-only serialized result ceiling. Expired work is
rejected before the action starts. Synchronous reads that exceed a budget emit
failure evidence; synchronous mutations that finish late emit
`completed_after_deadline` rather than claiming cancellation. Web mutation
offload joins the worker before reporting late/canceled outcomes; read offload
may detach only because it has no mutation effect. MCP blocking work uses a
bounded process-wide worker pool and joined mutation cancellation. No automatic
mutation retries were added. Federation probes are capped by node count,
validated host/port shape, active probe slots, and an overall timeout.

## CANDIDATE EPOCH HISTORY

### EPOCH_1 — implementation candidate

```text
BASE: 95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a
HEAD: 77eb706a9794eb04b570c53520a5a891b96335c6
TREE: 6b100c73dcb6b250f3bf46ac7e00958a9a182972
PARENTS: 95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a
WHY_HEAD_CHANGED: first bounded F1-F5 implementation and regression-test slice
GPG: local git verify-commit GOOD / primary 2D49E810C7F2527E
TARGETED_TESTS_AT_EPOCH: 230 passed
FULL_TESTS_AT_EPOCH: 1817 passed, 14 skipped, 0 deselected; coverage 83.20%
```

The final documentation/handoff commit creates a new exact candidate epoch.
Its live `HEAD`, tree, and parent are intentionally resolved from GitHub after
publication rather than fabricated in this self-referential file.

### EPOCH_2 — documentation candidate

```text
BASE: 95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a
HEAD: 9b04bbea6d42d700ae9c28534ce87277afafe2da
TREE: 9a380020ad9b6356f69f6681d0b10aa921c832a0
PARENTS: 77eb706a9794eb04b570c53520a5a891b96335c6
WHY_HEAD_CHANGED: candidate state clarification and append-only handoff
GPG: local git verify-commit GOOD / primary 2D49E810C7F2527E
REMOTE_CI: all required contexts PASS
```

### EPOCH_3 — review remediation candidate

```text
BASE: 9b04bbea6d42d700ae9c28534ce87277afafe2da
HEAD: 5d81a2dfb04c12b4fc18e499f198fe06823a9c07
TREE: b911cddf3fdc9dfa92a1ca0b247305caff45e6c9
PARENTS: 9b04bbea6d42d700ae9c28534ce87277afafe2da
WHY_HEAD_CHANGED: bounded history replay, context propagation, truthful budget mapping, safe rename destination validation, and review regression tests
GPG: local git verify-commit GOOD / primary 2D49E810C7F2527E
TARGETED_TESTS_AT_EPOCH: 233 passed
REMOTE_CI: pending until this epoch is published
```

The final documentation update below creates another exact candidate epoch;
all remote approval evidence must attach to that later exact head.

## FILES CHANGED

```text
src/power_framework/core/** (authority, principal, receipts, retrieval, worker, CLI safety)
src/power_framework/mcp/power_server.py
src/power_framework/web/** (session, request binding, approval, offload, federation)
tests/test_foundation_hardening.py
tests/web/contract/test_foundation_hardening.py
tests/test_mcp_server.py
tests/test_rename.py
tests/web/unit/test_auth.py
docs/plans/POWER_3.8_CURRENT_STATE.md
docs/plans/POWER_3.8_EXECUTION_ROADMAP.md
docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md
docs/plans/POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md
docs/plans/README.md
artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md
```

No dependency, lockfile, workflow, public version, tag, release, OCI image,
model, Phase 5 router/planner/ContextPack, capture adapter, vector database,
or persistent IndexWorkQueue was added.

## SECURITY AND REVIEW

```text
SOURCE_REVIEW: two fresh single-model adversarial cycles completed; actionable findings repaired or classified
CROSS_MODEL_CODEX: explicitly attempted, HTTP 400 for unsupported Luna Max model, then skipped by user decision
REAL_NETWORK_REQUIRED: NO
SECRETS_IN_HANDOFF: NO
ADMIN_BYPASS: NO
PROTECTION_BYPASS: NO
FORCE: NO
AUTO_MERGE: NO
```

## CANDIDATE / MERGE POINTERS

```text
FOUNDATION_PR: #414
FINAL_CANDIDATE_HEAD: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_TREE: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_PARENTS: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_GPG: RESOLVE_FROM_GITHUB
MERGE_SHA: RESOLVE_FROM_GITHUB
MERGE_TREE: RESOLVE_FROM_GITHUB
MERGE_PARENTS: RESOLVE_FROM_GITHUB
MERGE_GPG: RESOLVE_FROM_GITHUB
```

## NEXT GATE

```text
FOUNDATION_HARDENING: IMPLEMENTED / VERIFIED LOCALLY / CLOSED ONLY WHEN THIS EXACT PR IS PROTECTED-MERGED
PHASES_0_4: CLOSED / FROZEN
CONTROLLED_DEPENDENCY_REFRESH: CLOSED
PHASE_5: READY FOR SEPARATE PHASE 5A ADMISSION / NOT STARTED
PHASES_6_9: NOT STARTED
POWER_3_8_0: NO-GO
NEXT_GATE: Phase 5A — Runtime Contracts v2 + Frozen Evaluation Corpus Admission
```

After protected merge, resolve the final PR/merge objects from live GitHub,
verify the Foundation paths on `main`, append the protected closure comment to
the Foundation PR, and stop. Do not start Phase 5A in this session.
