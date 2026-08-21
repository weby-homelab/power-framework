# POWER Suite updater policy

The 3.6.7/3.7.0 suite candidate does not enable an automatic product updater.
The existing fleet updater remains maintainer infrastructure and is not a
product dependency.

Until a suite-aware updater proves stage, verify, activate, readback, rollback,
and downgrade behavior for the exact core/GUI/Skill/container pair, updates
are manual and hash-bound:

1. Build or obtain the exact POWER and POWER-GUI wheels.
2. Run `power integrations install` without `--apply` and inspect the artifact
   digests, target managed venv, and launcher set.
3. Apply only with `--apply --approved` after reviewing the plan.
4. Verify the launcher versions, `power-mcp preflight`, GUI health, and the
   `suite-install.json` receipt before enabling `systemd --user`.

Automatic activation remains disabled when any artifact, container digest,
rollback proof, or publication readback is missing.
