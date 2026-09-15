# INFRA-1 Broker API

> **Status:** CLOSED / MERGED / VERIFIED (PR #419). Local capability and
> framework contracts are merged on `main`. Real receiver deployment is an
> operator follow-up.

INFRA-1 is an opt-in Linux capability boundary. The POWER client and MCP
adapter send only identifiers over a local filesystem Unix socket. The broker
is the only component that can resolve an operator profile, read an isolated
credential, or start the fixed rsync-over-SSH transport.

## Request contract

The request operation is exactly one of:

```text
status | probe | rsync-dry-run | replicate | verify
```

The other request fields are `target`, `profile`, `dry_run`, an optional
`idempotency_key`, an optional `run_id` for `verify`, and an optional opaque
`approval_ref` for `replicate`. Task correlation fields are accepted only with
an exact `expected_revision`; they never grant authority. Unknown fields are
rejected. Hostnames, usernames, ports, source/destination paths, SSH options,
rsync options, passwords, and private keys are not request fields.

`replicate` always requires an idempotency key. A profile with
`dry_run_policy=required` must have a successful `rsync-dry-run` for the same
content-addressed snapshot before a write. The broker derives
`run_<manifest-sha256>` and does not accept a caller-supplied run ID for a
write.

## Response and receipts

Responses are closed, bounded `power.infra-response.v1` objects. They include a
request digest and a per-connection nonce binding. The receipt is either:

- `power.infra-receipt.v1` for a successful or failed fixed operation; or
- `power.infra-block.v1` for a capability, policy, identity, approval, or
  environment block.

No response contains raw stdout/stderr, command lines, environment variables,
source path lists, file contents, passwords, or private-key material. The
receipt carries counts, digests, safe identifiers, duration, exit category,
host-key fingerprint, credential ID, and the bounded remediation code.

## Principal and approval

The server derives `uid:<id>` from `SO_PEERCRED` (or the platform peer-credential
equivalent) and checks the explicit broker UID/GID allowlist before policy
execution. A request `actor` is not accepted and cannot impersonate a peer.
The client checks the broker UID before accepting a response.

`approval_policy=standing` is an operator-installed exact profile/principal
rule. `approval_policy=explicit` reloads the root/operator-owned approvals file
for every replicate and matches operation, target, profile, complete profile
digest, policy revision, principal, and expiry. One-time approvals are claimed
atomically. The agent cannot create or revoke either policy or approval.

## Transport boundary

The broker uses fixed absolute `/usr/bin/rsync` and `/usr/bin/ssh` paths with a
minimal environment and a new process group. SSH is forced to use
`BatchMode=yes`, public-key-only authentication, `IdentitiesOnly=yes`,
`IdentityAgent=none`, `StrictHostKeyChecking=yes`, one exact dedicated
known-host entry, no global/user configuration, no proxy/forwarding/local or
remote command, and a bounded timeout. Rsync receives no caller-controlled
options and never receives a delete or remote-command option.

`probe` and dry-run use a fixed rsync dry-run handshake; probe is not a bare SSH
session and therefore remains compatible with a forced `rrsync` receiver.
Verify uses the separate read-only credential: it enumerates each remote root,
pulls only the expected files one at a time with a per-file size ceiling, and
checks exact names/types/sizes/digests locally. It never writes to the remote
receiver; unknown, extra, missing, or truncated outcomes fail closed.

## Task semantics

The application projection preserves existing Task v2 states:

| Condition | Projection |
|---|---|
| actual missing target/profile datum | `input-required`, with bounded `required_input` |
| missing exact approval | `auth-required`, no password/key request |
| broker/profile/credential/host-key/network capability unavailable | `blocked` |
| external write outcome unknown or in flight | preserve current state, use `execution_state=leased` |
| network retry scheduling | existing `execution_state=waiting-network` only where the current contract permits it |

An infra receipt is not a Task completion receipt. The existing TaskService
must separately verify the postcondition and issue its canonical
`tcr_<sha256>` receipt before a task can become `completed`.

## Operator assets

Profiles that admit `verify` also require a separate operator-provisioned
read-only `rrsync -ro` credential; without it the broker blocks verification
rather than claiming a partial comparison is complete.

The service and socket units are in `deploy/systemd/`; they are never enabled
by package installation. Profile, approval, credential, known-host, source
ACL, and receiver provisioning are operator activities described in
`deploy/infra/README.md` and `deploy/infra/receiver.md`. The receiver is a
dedicated non-root account with forced current `rrsync -wo -no-del
-no-overwrite`, `restrict`, no forwarding/PTY, and a restricted destination.
