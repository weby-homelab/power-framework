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

1. Create a dedicated `power-infra` service account and a caller group. Add
   only the intended local POWER caller to that group.
2. Copy the example profile to the operator-owned
   `/etc/power/infra/profiles.d/` directory. Replace every placeholder with
   operator-approved values; keep the directory and JSON regular, non-symlink,
   and not group/world writable.
3. Install the current distribution `rrsync` wrapper on the receiver and
   provision the restricted non-root account according to
   [`receiver.md`](receiver.md). Receiver provisioning is never performed by
   generic CI or by the POWER agent.
4. Put the already-approved receiver host key in
   `/etc/power/infra/known_hosts` and set its exact `SHA256:` fingerprint in
   the profile. Missing or changed pins block; there is no TOFU or automatic
   `ssh-keyscan` trust.
5. Place the private key in the operator credential store with mode `0600` and
   use the unit's `LoadCredential=` mapping. The broker resolves only the
   server-side `credential_id`; it never accepts key bytes or a key path from
   MCP/CLI.
6. For `approval_policy=explicit`, install a strict operator-owned
   `/etc/power/infra/approvals.json` containing exact operation, target,
   profile, policy revision, server-derived `uid:<id>` principal, and an
   expiry. The broker rejects missing, mismatched, or expired records.
7. Review `power-infra-broker.service`, run `systemd-analyze verify` as an
   operator, and enable/start it only after the receiver, profile, key pin, and
   source ACLs have been independently verified. The unit is deliberately not
   enabled by package installation.

## Readiness checks

```text
power infra status
power infra probe prxmx01 --profile power-vault
power infra dry-run prxmx01 --profile power-vault
```

The first write requires the profile's dry-run policy and an exact standing or
explicit approval. Use `power infra replicate ... --idempotency-key ...` only
after the dry-run result is reviewed. A missing service returns
`MISSING_EXECUTION_CAPABILITY`; it is not a request for an SSH password.

## Source staging

`source_roots` are operator policy, not request data. The service must have
read-only ACL access to the staged source tree. Keep source data outside the
credential directory, reject symlinks/hardlinks/special files, and do not grant
the daemon unrestricted root filesystem access to solve a read-permission issue.

## Rollback

Disable the unit through normal systemd operator procedure and remove or revoke
the receiver key through the operator's credential/receiver process. Do not
delete evidence or silently rewrite policy. Key rotation is an operator action:
install the new pinned host key and credential, run status/probe/dry-run, then
retire the old pin only after independent verification.
