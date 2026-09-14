# Implementation Plan: POWER 3.8 INFRA-1

## Overview

Add a Linux-first, opt-in constrained infrastructure execution broker. The
agent-facing boundary accepts only typed operation/target/profile identifiers;
the broker resolves operator-owned policy and credentials, derives the caller
principal from Unix peer credentials, executes only fixed rsync-over-SSH
templates, and emits bounded secret-free receipts. No dependency refresh,
version bump, release, or Phase 5C retrieval implementation is included.

## State and capability map

- `PowerTask` already has `input-required`, `auth-required`, `blocked`, and
  `waiting-network`; preserve these values and reuse `required_input`,
  `open_gates`, `error_ref`, and `receipt_ids`.
- `ApplicationService` is the common CLI/MCP boundary; `Principal` is issued by
  trusted transport factories and actor attribution is not identity proof.
- `capabilities.manifest()` is static, read-only, and must not load models or
  access the network. Dynamic broker discovery belongs to `power infra status`.
- `handoff_work` and `power handoff` persist data only; they must never execute
  `next_action` or infer an infra action from retrieved text.
- Existing Phase 5B routing remains untouched; Phase 5C remains unstarted.

## Architecture decisions

1. Use a filesystem Unix-domain socket with newline-delimited bounded JSON and
   optional systemd socket activation. No TCP or HTTP broker listener.
2. Keep broker policy, known-hosts, approval records, and credential references
   outside the vault and request payload. Use strict Pydantic models and fixed
   subprocess argv; never use `shell=True` or a remote command channel.
3. Use fixed local source roots and immutable manifest-derived run IDs. The
   receiver reference profile is a non-root account with forced `rrsync`,
   `restrict`, and no deletion; provisioning is documentation-only.
4. Return typed block/authorization results rather than converting missing
   capability into `input-required`. Explicit approval is a server-side,
   exact binding, not a generic boolean.

## Ordered slices

### Slice 1 — Contract and policy foundation

- Add strict operation/request/result/receipt models, reason taxonomy, policy
  loader, approval binding, peer-principal extraction, and bounded framing.
- Add unit tests for unknown fields, forbidden request fields, policy ownership/
  symlink/schema checks, receipt redaction, and principal attribution.

### Slice 2 — Broker execution boundary

- Add Unix-socket client/server, local status discovery, bounded concurrency,
  manifest/run-id generation, host-key and credential preflight, and fixed
  rsync/SSH argv execution with failure categorization.
- Add fixture-backed tests for missing broker/profile/credential/host key,
  changed host key, network/timeout categories, path containment, fixed SSH
  options, no shell, output bounds, and idempotent replay/conflict.

### Slice 3 — Application, CLI, and MCP adapters

- Add `ApplicationService.infra_action()` with backward-compatible task-state
  projection, `power infra` client commands, and one typed `infra_action` MCP
  tool marked externally effectful.
- Add adapter contract tests and ensure handoff text cannot invoke the broker.

### Slice 4 — Packaging, receiver guidance, and governance projection

- Add opt-in systemd service/socket assets, policy/receiver examples, security
  and threat-model updates, and an INFRA-1 closure handoff with the Phase 5B
  parent erratum and candidate epoch placeholders resolved at admission.
- Add package-smoke coverage for the client entry point and verify no dependency
  or public-version files changed.

## Validation gates

- Focused broker, task semantics, capability, CLI, MCP, principal, handoff, and
  security tests pass without skipped new assertions.
- Locked sync, pip check, Ruff, format, MyPy, doc drift, strict MkDocs,
  pip-audit, package smoke, benchmark integrity, upgrade matrix, and full
  hermetic suite pass on the exact candidate.
- Independent architecture/security reviewers inspect the exact diff; every
  material head change starts a new candidate epoch.
- GitHub protected checks, GPG verification, one normal merge, and post-merge
  readback are required before declaring INFRA-1 closed.

## Explicit non-goals

No arbitrary SSH or shell, password fallback, agent-visible private key,
remote destructive operation, restore/prune/delete, infrastructure
orchestration, Phase 5C SearchScope pushdown, dependency changes, tag, release,
or public `3.8.0` publication.
