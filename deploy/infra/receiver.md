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
- forced command with write-only, no-delete semantics;
- no root login, forwarding, agent forwarding, X11 forwarding, PTY, or
  general-purpose interactive access;
- `from=` source restriction where POWER has a stable management address;
- protected `authorized_keys` and a shell configuration proven compatible with
  forced `rrsync` (a simple shell such as `dash` is preferred over assuming
  `nologin` works).

## Authorized-key shape

Use an operator-approved key and replace the placeholders. Never paste a real
key into this repository:

```text
from="<STABLE_POWER_SOURCE_IP_OR_CIDR>",restrict,command="/usr/local/bin/rrsync -wo -no-del /srv/power-vault/staging" ssh-ed25519 <OPERATOR_APPROVED_PUBLIC_KEY> power-infra
```

`-wo` makes the receiver write-only and `-no-del` prevents remote deletion.
For a profile whose semantics are immutable snapshots, the operator may add
`-no-overwrite`; do not add it to a profile that must update an existing file.
The destination and forced-command path must match the profile's operator
policy; neither can be selected by an agent.

## Receiver audit

Before admitting a profile, the operator should prove with a disposable source
and a disposable run that:

1. the key cannot open an interactive shell or allocate a PTY;
2. forwarding and agent identities are unavailable;
3. a command-like payload cannot bypass the forced `rrsync` command;
4. `--delete`, `--remove-source-files`, `--rsync-path`, symlinks, hardlinks,
   device files, and paths outside the staging root are rejected;
5. an existing snapshot is immutable when `-no-overwrite` is part of the
   profile; and
6. receiver logs contain no private key, password, or full source file data.

Do not use `ssh-keyscan` output as trust. A host key is pinned only after an
independent operator verification and an exact fingerprint is installed in the
POWER broker profile.
