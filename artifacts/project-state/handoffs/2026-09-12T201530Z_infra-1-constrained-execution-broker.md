# POWER 3.8 INFRA-1 — Constrained Local Infrastructure Execution Broker

> Append-only provisional handoff. This record becomes `MERGED MAIN` evidence
> only after the exact candidate passes protected admission, one normal merge,
> and independent post-merge readback.

## Recovery anchor

```text
PROJECT: POWER Framework 3.8
REPOSITORY: https://github.com/weby-homelab/power-framework
PUBLIC_VERSION: 3.7.11
BRANCH: feat/power-3.8-infra-execution-broker
ACTIVE_GATE: INFRA-1 — Constrained Local Infrastructure Execution Broker
NEXT_GATE: Phase 5C — SearchScope Pushdown
TRANSFER_PR: #419 / https://github.com/weby-homelab/power-framework/pull/419
```

```text
STARTING_MAIN: 6a315d5919eeef797bc506ecb216313c20419fc2
STARTING_TREE: a03b90648e1e57c5a579e5834988015192027cb0
STARTING_PARENTS:
  dde1e1369c2d79d8f01b9fce21ae1fb55834a814
  887f8319b70c4e7be98d503d53924a70ad211c38
STARTING_GPG: verified=true / reason=valid
STARTING_PROTECTION: strict=true; 11 required contexts; force/deletion disabled
```

## Phase 5B bounded erratum

Live GitHub confirms Phase 5B is closed by PR #418 and merge
`6a315d5919eeef797bc506ecb216313c20419fc2`. Candidate head
`887f8319b70c4e7be98d503d53924a70ad211c38` has actual parent
`12dda70c8badbbff723971d023206574b4130b64`. The protected merge parents are
the Phase 5A.1 main `dde1e1369c2d79d8f01b9fce21ae1fb55834a814` and that candidate
head. A different parent in the historical narrative is retained as a bounded
reporting typo; historical Phase 5B files are not rewritten.

## Dependency boundary

PR #417 is open maintenance work with a separate dependency graph and a failed
`package-smoke` check on its head `49d88950dfa266b0f6c53c167ddbbfcf3e956ce2`.
It is not merged, rebased, modified, or bundled into INFRA-1. No dependency
ranges, `uv.lock`, HF/model ranges, MCP dependency, NumPy/Pydantic pair, or
ONNX/GPU graph is changed by this gate.

## INFRA-1 scope

Implemented candidate boundary:

- strict `InfraRequest` with only `status`, `probe`, `rsync-dry-run`,
  `replicate`, and `verify`;
- bounded Unix socket framing and OS peer-principal derivation;
- operator profile schema with target/source/receiver/host-key/credential
  allowlists, resource bounds, dry-run policy, and approval policy;
- fixed noninteractive SSH options and fixed rsync argv; no shell, arbitrary
  host/path/command/options, password fallback, or inherited ssh-agent;
- source manifest containment with symlink/hardlink/special-file rejection;
- immutable run/staging semantics, idempotency replay/conflict handling,
  bounded secret-free receipts, and optional service receipt persistence;
- ApplicationService Task projection: capability absence → `blocked`, approval
  absence → `auth-required`, genuine missing request datum → `input-required`;
- static capability IDs plus separate dynamic `power infra status`;
- one typed MCP tool `infra_action` and operator CLI client;
- opt-in non-root systemd service, profile example, receiver/rrsync reference,
  ADR, threat-model and security-boundary documentation.

Not implemented or admitted: arbitrary shell/SSH, restore, delete/prune,
remote sudo/package/firewall/lifecycle, Ansible/Terraform, Phase 5C retrieval
scope pushdown, version/tag/release changes, or real-host provisioning.

## Security invariants

```text
DIRECT_ARBITRARY_SSH_FROM_AGENT: DENIED
ARBITRARY_REMOTE_SHELL: DENIED
PASSWORD_AUTH_FALLBACK: DENIED
PRIVATE_KEY_IN_LLM_CONTEXT: DENIED
BROKER_UNAVAILABLE: BLOCKED / MISSING_EXECUTION_CAPABILITY
```

Handoff text remains data and cannot execute an infra action. The receiver is a
dedicated non-root forced `rrsync` account with `restrict`, no forwarding/PTY,
no-delete, and optional stable-source `from=` defense in depth.

## Candidate epoch

```text
EPOCH_0_BASE: 6a315d5919eeef797bc506ecb216313c20419fc2
EPOCH_1_HEAD: dcf27b55e3e5bfeb285fc93ed73a485ce0f707fb
EPOCH_1_TREE: 85a84c6e9158dc98168dc9e7a1dff03259aba90b
EPOCH_1_PARENTS: 6a315d5919eeef797bc506ecb216313c20419fc2
EPOCH_1_WHY: INFRA-1 broker/client/task/MCP/CLI/security/docs implementation
EPOCH_1_GPG: verified=true / reason=valid / fingerprint=2D49E810C7F2527E
```

## Local evidence at handoff creation

```text
FOCUSED_INFRA_TESTS: PASS (18 hermetic broker tests plus application/CLI/MCP slices)
RUFF_TARGETED: PASS
MYPY_TARGETED: PASS
DOC_DRIFT: PASS with POWER_GLOBAL_SKILL_PATH pinned to repository skill;
  unmodified host-global copies are stale and are not repository evidence
REAL_HOST_CREDENTIAL: deployment evidence unavailable; not requested
REAL_REPLICATE: NOT RUN
```

## Next action

Complete the remaining local security/systemd/Task/MCP regression matrix, run
the full hermetic quality gate, inspect the complete dual-sided diff, create a
GPG-signed candidate commit, publish the PR, and admit only the exact head with
all required protected contexts. Do not start Phase 5C.
