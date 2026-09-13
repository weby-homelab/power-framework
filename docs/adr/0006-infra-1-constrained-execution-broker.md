# ADR-0006: INFRA-1 constrained local infrastructure execution broker

## Status

Accepted for the POWER 3.8 INFRA-1 gate. The broker is opt-in and does not
change the public version or authorize Phase 5C.

## Context

Direct SSH/SCP from an AI agent is denied by policy, but the absence of an
approved capability previously collapsed into a misleading `input-required`
request. POWER needs a safe, bounded path for a small class of local
infrastructure operations without turning the agent into a shell client.

## Decision

Provide a typed client and an opt-in non-root broker over one Unix-domain
socket. The client accepts only the closed operation set `status`, `probe`,
`rsync-dry-run`, `replicate`, and `verify`, plus target/profile identifiers and
bounded idempotency/approval references.

The broker derives the caller principal from Unix peer credentials. It resolves
host, port, user, source roots, remote root, pinned known-hosts file,
credential ID, resource limits, approval policy, and receiver mode from an
operator-owned strict profile. It builds fixed SSH/rsync arguments with
`BatchMode`, password and keyboard-interactive authentication disabled,
`IdentitiesOnly`, `IdentityAgent=none`, strict host-key checking, and no
caller-controlled remote command.

The private key is delivered only through systemd `LoadCredential=` into the
broker boundary. It never enters a request, Task, receipt, MCP response, CLI
output, prompt, or vault note. Replication is immutable-run/staging oriented,
requires an idempotency key, uses bounded manifests and output/time limits,
requires a dry-run unless standing profile policy says otherwise, and never
performs remote deletion/pruning.

## Task and handoff semantics

No new top-level Task state is introduced. Capability absence is `blocked` with
`MISSING_EXECUTION_CAPABILITY`; disabled profiles, missing pins, changed pins,
network failure, and unavailable credentials remain blocked. Missing approval is
`auth-required`; a genuinely missing target/profile input is `input-required`.
The broker block receipt is referenced through existing `receipt_ids`,
`error_ref`, and `open_gates`. Handoff packets remain declarative data and never
execute `next_action`.

## Alternatives rejected

- direct agent SSH/SCP: violates the security boundary and exposes arbitrary
  host/path/command selection;
- HTTP/TCP broker: expands the local trust boundary and is unnecessary;
- `sshpass`, environment/private-key arguments, or inherited `SSH_AUTH_SOCK`:
  leaks credentials or permits password/agent fallback;
- TOFU or automatic `ssh-keyscan` trust: permits host-key substitution;
- a homemade `SSH_ORIGINAL_COMMAND` parser: use current `rrsync` controls;
- privileged/root daemon: solve source ACLs with bounded staging and operator
  permissions instead of granting an agent-triggered root filesystem view.

## Consequences

The framework can report a truthful blocked capability instead of requesting a
password. A real profile and receiver remain explicit deployment evidence, not
framework CI prerequisites. General automation, restore, deletion, sudo,
package management, lifecycle, and firewall operations remain outside INFRA-1
and require separate gates.
