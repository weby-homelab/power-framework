# POWER 3.7.10 closure blocker log

Only material unexpected conditions are recorded here. The log contains public
identifiers and sanitized symptoms; it contains no credentials, private vault
content, or raw authorization material.

| ID | Phase | Severity | Class | Status | Owner |
| --- | --- | --- | --- | --- | --- |
| `BLK-0001` | 11 | P2 | WORKFLOW / RELEASE_EVIDENCE | RESOLVED_BY_PUBLIC_READBACK | closure branch |
| `BLK-0002` | 10 | P1 | PRXMX / AUTHORIZATION | RESOLVED_WITH_BOUNDED_TRANSPORT | closure branch |
| `BLK-0003` | 6 | P2 | ENVIRONMENT | RESOLVED_WITH_OCI_API | closure branch |
| `BLK-0004` | 27 | P2 | ENVIRONMENT | RESOLVED_WITH_UV_ENVIRONMENT | closure branch |
| `BLK-0005` | 29-32 | P1 | AUTHORIZATION | BLOCKED_AUTHORIZATION | owner action |
| `BLK-0006` | 10 | P1 | PRXMX / RUNTIME_DRIFT | OPEN_DRIFT | owner action |

## BLK-0001

- Symptom: publication run `33391322565` created Release `379738795`, then
  failed at the post-publication OCI binding step; the Web attestation step was
  consequently skipped.
- Root cause: the release workflow revision used an authenticated GHCR readback
  after the temporary Docker session boundary, while the registry was private
  at that time.
- Fix: the public release was not rewritten; PR #380 added authenticated public
  readback controls for future workflow executions.
- Verification: fresh public asset binding, exact OCI digest readback, and
  independent wheel/sdist/OCI `gh attestation verify` all passed.

## BLK-0002

- Symptom: the required PRXMX remote read-only audit initially had no approved
  transport from WS.
- Root cause: the global OpenCode policy denied remote shell access until the
  owner explicitly authorized this bounded read-only Phase 10 scope.
- Fix: a temporary host-specific, batch-only transport rule was enabled for the
  audit and removed immediately afterward; forwarding, TTY, apply, record, and
  mutation commands were not invoked.
- Verification: `phase-10-prxmx-readonly-audit.json` records
  `mutation_performed=false`, `remote_access_attempted=true`, strict transport
  controls, and identical before/after metadata hashes.

## BLK-0006

- Symptom: the authorized read-only audit resolved and verified `v3.7.10`; all
  six discovered POWER runtimes and all four MCP references resolve to
  `3.7.10`, but one managed Skill target requires topology review.
- Root cause: one managed OpenCode Skill target is a symlink, which the runtime
  audit intentionally classifies as `manual_review`; additionally, the checkout
  copy of the audit script was already dirty and was not executed.
- Fix: none claimed because this phase was explicitly read-only. The audit ran
  only the public-verified tracked `HEAD` blob and made no remote mutation.
- Verification: public manifest and wheel digests passed, runtime drift is
  false, MCP drift is false, Skill drift is true, and every before/after
  bounded metadata comparison passed. No universal transient-write absence
  claim is made from metadata equality alone.

## BLK-0003

- Symptom: the WS Docker installation has no `buildx` subcommand, so the usual
  `docker buildx imagetools inspect` readback was unavailable.
- Root cause: local tooling capability, not a registry or release mismatch.
- Fix: used the authenticated OCI Distribution API with an isolated temporary
  config and read the `Docker-Content-Digest` response header.
- Verification: HTTP 200 and digest equality with the manifest and Profile B.

## BLK-0004

- Symptom: direct host `mypy` lacked optional project dependencies.
- Root cause: the command bypassed the locked project environment.
- Fix: reran the same gate through `uv run` without changing source or system
  Python.
- Verification: `uv run mypy src/power_framework/` passed.

## BLK-0005

- Symptom: PR #381 has all required exact-head checks passing, but protected
  `main` still requires one approving review and the only recorded review is
  `COMMENTED`.
- Root cause: the current actor cannot approve its own pull request; an admin
  merge bypass would weaken the required-review policy and is forbidden for
  this closure.
- Fix: none claimed; no bypass, protection edit, or fabricated approval was
  used.
- Verification: GitHub reports `reviewDecision=REVIEW_REQUIRED`,
  `mergeStateStatus=BLOCKED`, and branch protection requires one approval.

## OWNER-ACTION-002

- AREA: protected merge of the closure PR.
- REQUIRED ACTION: an independent authorized maintainer must review and approve
  PR #381, then allow the normal protected merge flow.
- WHY AGENT CANNOT COMPLETE: GitHub rejects self-approval, and bypassing the
  required review would violate the repository closure policy.
- EXACT EVIDENCE: PR `https://github.com/weby-homelab/power-framework/pull/381`,
  head `8ab5314613f104c4aea8aa578bc602ae274ac910` at the latest verified public
  readback, all required checks passed,
  `reviewDecision=REVIEW_REQUIRED`.
- HEAD SNAPSHOT NOTE: this identifier is a point-in-time public PR readback
  immediately before this evidence-refresh commit; after any later branch
  commit, the PR head and required checks must be read back again before
  treating this evidence as current.
- RISK IF DEFERRED: closure changes remain only on the dedicated branch; public
  `main` has no durable post-release evidence or final merge readback.
- RESUME PHASE: Phase 31 merge gate, then Phase 32 post-merge verification and
  Phase 33 independent clean-room audit.

## OWNER-ACTION-001

- AREA: PRXMX read-only runtime audit.
- REQUIRED ACTION: review the Skill symlink topology and dirty checkout copy of
  the audit script; explicitly authorize any repair, then rerun the same bounded
  read-only audit until managed Skill drift is false.
- WHY AGENT CANNOT COMPLETE: the granted scope was read-only and did not permit
  changing a Skill target, checkout, MCP configuration, runtime, or system
  Python.
- EXACT EVIDENCE: `phase-10-prxmx-readonly-audit.json` with
  `status=DRIFT`, `mutation_performed=false`, six runtimes at `3.7.10`, MCP
  drift false, Skill drift true, and immutable before/after readback.
- RISK IF DEFERRED: the runtime itself is current, but managed Skill topology
  remains outside a full PASS claim.
- RESUME PHASE: Phase 10 and then final independent audit; all other phases are
  independent and continue without this action.
