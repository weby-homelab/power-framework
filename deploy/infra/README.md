# INFRA-1 operator deployment reference

INFRA-1 is an **opt-in** local execution boundary. Installing the POWER wheel
does not enable a daemon, create a credential, contact a target, or grant an
agent infrastructure authority.

## Boundary

```text
POWER CLI/MCP
    │ typed identifiers only
    ▼
AF_UNIX /run/power-infra/broker.sock
    │ SO_PEERCRED + group policy
    ▼
power-infra-broker.service (non-root)
    │ operator profile + LoadCredential
    ▼
fixed ssh/rsync argv → pinned host → forced rrsync receiver
```

There is no TCP/HTTP broker, direct-agent SSH fallback, arbitrary remote shell,
password authentication, `ssh-agent` use, caller-controlled host/path/command,
`--rsync-path`, delete/prune operation, or private key in MCP/Task/memory
context.

## Installation checklist

1. Create a dedicated `power-infra` service account and the separate
   `power-infra-callers` group. Add only the intended local POWER caller to that
   group, copy `callers.example.json` to the root-owned
   `/etc/power/infra/callers.json`, and configure that caller's exact UID/GID
   allowlist. The socket group alone is not the broker's identity proof.
2. Install the supported POWER package into the root-owned system Python
   environment used by `/usr/bin/python3`, which must be Python `>=3.13,<3.15`;
   the systemd unit refuses to start on an unsupported interpreter or package
   version.
3. Copy the example profile to the operator-owned
   `/etc/power/infra/profiles.d/` directory. Replace every placeholder with
   operator-approved values; keep the directory and JSON regular, non-symlink,
   and not group/world writable.
4. Install the current distribution `rrsync` wrapper on the receiver and
   provision the restricted non-root account according to
   [`receiver.md`](receiver.md). Receiver provisioning is never performed by
   generic CI or by the POWER agent.
5. Put the already-approved receiver host key in
   `/etc/power/infra/known_hosts` and set its exact `SHA256:` fingerprint in
   the profile. Missing or changed pins block; there is no TOFU or automatic
   `ssh-keyscan` trust.
6. Place separate write and read-only verification private keys in the operator
   credential store with mode `0600` and use the unit's two `LoadCredential=`
   mappings. The broker resolves only the server-side `credential_id` and
   `verify_credential_id`; it never accepts key bytes or a key path from
   MCP/CLI.
7. For `approval_policy=explicit`, install a strict operator-owned
    `/etc/power/infra/approvals.json` containing exact operation, target,
    profile, complete profile digest, server-derived `uid:<id>` principal, and
    an expiry. The broker reloads this file for every write and rejects
    missing, revoked/deleted, mismatched, or expired records.
8. Install the companion `power-infra-broker.tmpfiles` rule so the socket
   parent is traversable only by the caller group, review both systemd units,
   run `systemd-analyze verify` as an operator, and enable/start them only
   after the receiver, profile, key pin, and source ACLs have been independently
   verified. The units are deliberately not enabled by package installation.

## Readiness checks

```text
power infra status
power infra probe prxmx01 --profile power-vault
power infra dry-run prxmx01 --profile power-vault
```

The first write requires the profile's dry-run policy and an exact standing or
explicit approval. `probe` is a fixed rsync dry-run, not a bare SSH session.
Use `power infra replicate ... --idempotency-key ...` only after the dry-run
result is reviewed. A missing service returns
`MISSING_EXECUTION_CAPABILITY`; it is not a request for an SSH password.

## Source staging

`source_roots` are operator policy, not request data. The service must have
read-only ACL access to the staged source tree. Keep source data outside the
credential directory, reject symlinks/hardlinks/special files, and do not grant
the daemon unrestricted root filesystem access to solve a read-permission issue.
The private copied key/known-host material lives only in the service
`RuntimeDirectory`; persistent state contains no private key bytes.

## Rollback

Disable the unit through normal systemd operator procedure and remove or revoke
the receiver key through the operator's credential/receiver process. Do not
delete evidence or silently rewrite policy. Key rotation is an operator action:
install the new pinned host key and credential, run status/probe/dry-run, then
retire the old pin only after independent verification.
