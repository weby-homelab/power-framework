# Restricted rsync receiver reference

This document is a provisioning reference, not an automated provisioning
script. The receiver must be created and reviewed by an operator on the target
host.

## Required properties

- dedicated non-root account such as `power-receiver`;
- dedicated destination such as `/srv/power-vault/staging` that is not the
  account's writable home;
- current distribution `rrsync`, not a home-grown `SSH_ORIGINAL_COMMAND`
  parser;
- forced command with write-only, no-delete, no-overwrite semantics;
- no root login, forwarding, agent forwarding, X11 forwarding, PTY, or
  general-purpose interactive access;
- `from=` source restriction where POWER has a stable management address;
- protected `authorized_keys` and a shell configuration proven compatible with
  forced `rrsync` (a simple shell such as `dash` is preferred over assuming
  `nologin` works). Disable user startup files and keep the receiver home
  outside the writable destination.

## Authorized-key shape

Use an operator-approved key and replace the placeholders. Never paste a real
key into this repository:

```text
from="<STABLE_POWER_SOURCE_IP_OR_CIDR>",restrict,command="/usr/local/bin/rrsync -wo -no-del -no-overwrite /srv/power-vault/staging" ssh-ed25519 <OPERATOR_APPROVED_PUBLIC_KEY> power-infra
```

`-wo` makes the receiver write-only, `-no-del` prevents remote deletion, and
`-no-overwrite` is mandatory for the INFRA-1 immutable snapshot profile. The
destination and forced-command path must match the profile's operator policy;
neither can be selected by an agent. If a future profile needs mutable files,
it is a separate capability and cannot reuse this immutable receiver claim.

Verification uses a separately authorized public key whose only forced command
is the read-only form below. It is required when the profile admits `verify`;
the client first uses `--list-only --dry-run` and then pulls only the
enumerated files into a private ephemeral directory for local size/digest
comparison; it never invokes a remote shell or a file-read command:

```text
from="<STABLE_POWER_SOURCE_IP_OR_CIDR>",restrict,command="/usr/local/bin/rrsync -ro /srv/power-vault/staging" ssh-ed25519 <OPERATOR_APPROVED_VERIFY_PUBLIC_KEY> power-infra-verify
```

## Receiver audit

Before admitting a profile, the operator should prove with a disposable source
and a disposable run that:

1. the key cannot open an interactive shell or allocate a PTY;
2. forwarding and agent identities are unavailable;
3. a command-like payload cannot bypass the forced `rrsync` command; the
   receiver's simple shell and startup-file behavior are tested explicitly;
4. `--delete`, `--remove-source-files`, `--rsync-path`, symlinks, hardlinks,
   device files, and paths outside the staging root are rejected;
5. an existing snapshot is immutable when `-no-overwrite` is part of the
   profile; and
6. receiver logs contain no private key, password, or full source file data.

Do not use `ssh-keyscan` output as trust. A host key is pinned only after an
independent operator verification and an exact fingerprint is installed in the
POWER broker profile.
