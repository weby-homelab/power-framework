# P.O.W.E.R. hourly updater

This deployment installs a systemd service and timer that check the stable
GitHub Release for `weby-homelab/power-framework` every hour. It verifies the
release tag, canonical wheel name, wheel metadata, and GitHub-published SHA-256
before changing an existing installation.

The updater uses an explicit `POWER_UPDATER_PYTHON_TARGETS` allowlist. It does
not recursively scan a home directory and does not install POWER into arbitrary
virtual environments. Every configured target must exist and already contain
`power-framework`; project-specific environments that are not part of the
active runtime remain untouched. It updates those targets with `--no-deps` and
never silently upgrades unrelated dependencies.

This distinction is intentional: the system Python and OpenCode/MCP Python are
canonical host runtimes, while active project venvs preserve dependency
isolation. Historical Codex worktrees and disposable test venvs are not update
targets.

On PRXMX-01 it additionally builds a local derived POWER-GUI image from the
official GUI base, installs the verified POWER wheel into that image, verifies
the package before deployment, changes the compose image atomically, and waits
for the GUI health endpoint to report the expected POWER version. Failed GUI
deployments restore the previous compose file and restart the previous image.

## Install

Run from this directory as root on each host:

```bash
./install.sh ws
./install.sh prxmx-host
./install.sh lxc200
```

The resulting timer is `power-updater.timer`. Logs are available with:

```bash
journalctl -u power-updater.service
systemctl list-timers power-updater.timer
```

Install `prxmx-host` on PRXMX-01 itself and `lxc200` inside LXC200. The host
profile updates system/OpenCode runtimes and active Skills; the LXC profile
updates the Docker GUI image and does not invent a Python installation where
none exists.

Use `power_auto_updater.py --dry-run --config /etc/power-updater/power-updater.env`
for a read-only release and target discovery check.
