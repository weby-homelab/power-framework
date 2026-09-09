# POWER 3.8 Controlled Dependency Refresh — Final Integration Handoff

> Append-only governance handoff. This packet is a planning candidate until
> the consolidated governance PR is protected-merged. It does not start
> Foundation Hardening or Phase 5.

## STAGE

Controlled Dependency Refresh — Final Integration and Course-Correction Governance

## PUBLIC_VERSION

`3.7.11`

## STARTING_MAIN

`a386858a45489eb5db213d42ffe773db9134ff88`

## STARTING_MAIN_TREE

`664f34995961a2990dee00ecde0ebe7c8ed0f5d8`

## OBSERVED_AT_UTC

`2026-09-09T06:59:50Z`

## GOVERNANCE_BRANCH

`docs/power-3.8-final-integration-course-correction`

## GOVERNANCE_BASE

`a386858a45489eb5db213d42ffe773db9134ff88`

## GOVERNANCE_PR

`#413`

## CANDIDATE_EPOCH_AT_HANDOFF_CREATION

```text
PR: #413
BASE_SHA: a386858a45489eb5db213d42ffe773db9134ff88
HEAD_SHA: d0728d28898fd590b9aaa9d9b82289ebfa553b66
HEAD_TREE: 3d54b3d605ea102c945ffc76c6cb83b9770a3775
HEAD_PARENT: a386858a45489eb5db213d42ffe773db9134ff88
GPG: verified=true / reason=valid
```

The handoff is part of the candidate tree, so a later correction creates a new
candidate epoch. `GOVERNANCE_HEAD` below intentionally resolves from the live
PR rather than fabricating the self-referential future commit SHA.

## CANDIDATE_EPOCH_REPAIR

```text
PREVIOUS_HEAD: d0728d28898fd590b9aaa9d9b82289ebfa553b66
PREVIOUS_TREE: 3d54b3d605ea102c945ffc76c6cb83b9770a3775
REASON: independent governance/security review tightened planning-only schema invariants and stale-state labels
NEW_HEAD: RESOLVE_FROM_GITHUB
```

The repair does not change source/runtime/dependency/workflow scope. It creates
a fresh exact-head evidence epoch; all prior checks remain historical evidence
until the new head receives its own checks.

## GOVERNANCE_HEAD

`RESOLVE_FROM_GITHUB`

## GOVERNANCE_MERGE_SHA

`RESOLVE_FROM_GITHUB`

## GOVERNANCE_MERGE_TREE

`RESOLVE_FROM_GITHUB`

## GOVERNANCE_MERGE_PARENTS

`RESOLVE_FROM_GITHUB`

## ACTIONS_396

`CLOSED / MERGED`

Candidate head:
`147afac8f4b43a967207309d69ccad78c6d16739`

Candidate tree:
`664f34995961a2990dee00ecde0ebe7c8ed0f5d8`

Candidate parents:
`a715df08b34a0c561e487199ff56a2853279d951`
and
`64178e9d2791fc8a291ac647374efc566f201f0e`

Protected merge:
`a386858a45489eb5db213d42ffe773db9134ff88`

Merge parents:
`64178e9d2791fc8a291ac647374efc566f201f0e`
and
`147afac8f4b43a967207309d69ccad78c6d16739`

Merge tree equals the candidate tree. The Actions diff contains exactly the
four intended workflow files. GitHub verification for candidate and protected
merge was `verified=true`, `reason=valid`.

## FINAL_INTEGRATION

`CLOSED / FINAL INTEGRATION VERIFIED`

Required protected contexts freshly enumerated through REST:

```text
test (3.13)
test (3.14)
security
package-smoke
upgrade-matrix (ubuntu-latest)
upgrade-matrix-aggregate
base-runtime-smoke
benchmark-integrity
analyze (python)
CodeQL
build
```

Current-main CI, Docs, and CodeQL workflow runs were successful. Branch
protection was read through REST: main is protected, strict required checks are
enabled, signed commits are required, force pushes/deletions are disabled, and
no approval count is required by the current projection.

## LOCAL_VALIDATION

- `uv lock --check`: PASS.
- `uv sync --locked`: PASS.
- Locked environment `pip check`: PASS.
- Ruff check: PASS.
- Ruff format check: PASS.
- MyPy: PASS, 115 source files.
- `mkdocs build --strict`: PASS; only non-fatal upstream/deprecation and
  un-navigated-page warnings were emitted.
- `pip-audit --skip-editable`: PASS, no known vulnerabilities.
- Root `verify.sh`: PASS.
- Frozen PSE/Task/Decision/crash subset: `346 passed`.
- Full hermetic suite: `1775 passed, 4 skipped, 17 deselected`, coverage
  `83.06%`.
- Security/model/Web subset: `147 passed`.
- Neural hermetic contract: `5 passed` and verifier PASS.
- Package smoke: PASS, version `3.7.11`, `16` queries.
- Base runtime smoke: PASS on Python `3.14.6`; FTS init/ingest/sync/search and
  pip check passed.
- Upgrade matrix `3.7.10 → 3.7.11` and supported-platform aggregate: PASS.
- Benchmark integrity: `114 passed, 1 skipped`; outcome and continuity gates:
  PASS.
- No model was downloaded and no release/tag/image was published.

## DEPENDENCY_CONSISTENCY

Current main retains the separately admitted HF boundary:

```text
huggingface-hub >=1.30.0,<1.31.0
numpy <2.5
```

`pyproject.toml`, `uv.lock`, and `release/web-runtime.requirements.txt` are
internally consistent. The broad #402 NumPy/MCP/Pydantic/maintenance bundle was
not required for final integration and was not refreshed onto main.

## PR_402

```text
HEAD: 555748e07f4ef2d61dc08dc0b3cb4c8d92b913d0
BASE: 2d8058854ffbfae8526095af9809ab2c6f9c04f6
TREE: 323b45bf2c00a6a06e30dae997583f7b7829748d
PARENT: 2d8058854ffbfae8526095af9809ab2c6f9c04f6
STATE: CLOSED WITHOUT MERGE / DEFERRED
```

The candidate was a broad maintenance bundle, behind current main, and its
required `package-smoke` failed at the lock-bound Web export check. It combined
independently governed NumPy, MCP/mcp-types, Pydantic/pydantic-core, ONNX/GPU,
tooling, Web export, and a historical release constraints artifact. A fresh
disposition comment was published before REST closure. Future useful updates
must be split by compatibility/security surface.

## PR_407

```text
HEAD: a3f8cb5f0cfd7e5b37ea316146a4e761a99a46e2
BASE: 119d5c39aa2c22734ca72c351f8a70790371678f
TREE: ad884ff0d42e1daba6d9489004ce98d169d5eb02
PARENT: a01d92e37ec5536f75d3e8cd3461112c114e9199
STATE: CLOSED WITHOUT MERGE / SUPERSEDED HISTORICAL EVIDENCE
GPG: unsigned candidate; retained for auditability
```

The pre-HF blocked-state evidence was superseded by later protected governance,
HF, architecture, and Actions merges. Its historical evidence was not deleted
or rewritten. A final supersession comment was published before REST closure.

## GOVERNANCE_SCOPE

The governance candidate changes only planning/governance paths:

```text
docs/plans/**
artifacts/project-state/planning/**
artifacts/project-state/handoffs/2026-09-09T065950Z_controlled-dependency-refresh_final-integration.md
```

It contains:

```text
no source code
no dependency changes
no workflow changes
no Phase 5 runtime
no Foundation Hardening runtime
no version bump
no tag
no release
no OCI publication
```

## PLANNING_V2

```text
CONTEXT_CONTRACT_V2:
artifacts/project-state/planning/context-retrieval-contracts-v2.schema.json

RETRIEVAL_EVAL_CONTRACT:
artifacts/project-state/planning/retrieval-eval-v1.schema.json

FOUNDATION_GATE:
artifacts/project-state/planning/pre-phase5-foundation-hardening-gate.md

RETAINED_V1:
artifacts/project-state/planning/context-retrieval-contracts-v1.schema.json
artifacts/project-state/planning/index-cost-policy-v1.json
```

The v2 contracts remain planning-only and are not consumed by the current
runtime. v1 artifacts remain retained evidence and their meanings are not
silently rewritten.

## NEXT_GATE

`Pre-Phase-5 Foundation Hardening Admission`

## FOUNDATION_HARDENING

`NEXT GATE / PLANNED / NOT STARTED`

## PHASE_5

`BLOCKED / NOT STARTED`

## PHASES_0_4

`CLOSED / FROZEN`

## PHASES_6_9

`NOT STARTED`

## POWER_3_8_0

`NO-GO`

## GPG

Governance commit must be created with the configured `2D49E810C7F2527E` key,
verified locally with `git verify-commit`, and verified by GitHub after
publication. Final governance object fields are `RESOLVE_FROM_GITHUB` until the
protected merge exists; no trailing SHA commit is permitted.

## NOT_AUTHORIZED

- Do not start Foundation Hardening implementation from this handoff.
- Do not start Phase 5.
- Do not reopen or mutate closed Actions #396.
- Do not implement ContextPack runtime, persistent IndexWorkQueue, capture
  adapters, optional Context Broker, or vector database.
- Do not ingest conversation corpora or download models for this governance
  gate.
- Do not bump version, create tag/release, publish OCI artifacts, or bypass
  protection.

## RECOVERY_ORDER

```text
read CURRENT_STATE
read ROADMAP
read DEVELOPMENT_PROTOCOL
read active v2 planning contracts and Foundation gate
read this latest handoff
fetch live main through authenticated REST
verify snapshot ancestry and policy
independently audit only Foundation Hardening
```
