# POWER Suite Architecture v1

Status: architecture freeze for the 3.6.7 RC and 3.7.0 release work
Date: 2026-08-21

## Authority and boundaries

The suite has one canonical state model:

```text
Markdown/Git = authoritative knowledge source
ApplicationService = business boundary
TaskService = task truth
DecisionService = decision truth
Proposal/apply = canonical mutation path
Receipts = core evidence
GUI/MCP/CLI/Skills = adapters and consumers
```

Adapters may validate input, enforce their transport contract, and format a
bounded response. They must not persist a second canonical state, call a
lower-level canonical mutator directly, or treat retrieved note text as an
executable instruction.

## Canonical Linux workstation profile

The managed native profile is one exact virtual environment with these stable
launchers:

```text
~/.local/share/power/venv
~/.local/bin/power
~/.local/bin/power-mcp
~/.local/bin/power-gui
```

The install and update harnesses operate only on the managed suite directory.
They never mutate system Python, an arbitrary project virtualenv, or a hidden
checkout. Every launcher resolves into the same managed environment and the
same exact core/GUI candidate pair.

The GUI launcher is available for the native workstation profile. A CLI/MCP
only profile may omit it without changing the core or Skill contract.

## Canonical local transport

`power-mcp` is the public local entry point and defaults to MCP stdio. It
requires one explicit, existing `POWER_VAULT_DIR` root and fails closed when
the root is absent, invalid, or outside the configured boundary. Protocol
frames are written to stdout; logs and diagnostics are written to stderr.

The adapter owns no business state. MCP tool mutations route through
`ApplicationService` and return the same content-free receipts and revisions
as CLI and GUI calls. A client configuration contains an absolute launcher and
the vault environment only; no vendor-specific business logic is required.

## Portable Skill profile

`skills/power/` is the single source tree and is shipped as release package
data. It contains `SKILL.md`, `references/`, and bounded `scripts/`. The
installed Skill is immutable with respect to the release candidate: its tree
hash and compatible core version are recorded in the suite manifest. Generic
installation is explicit, dry-run first, path-confined, atomic, idempotent,
and does not overwrite unrelated agent files.

## GUI profiles

The native `systemd --user` unit is the canonical workstation service. It is
opt-in, binds to loopback by default, uses a user-owned managed environment,
reads mode-600 configuration when configuration is required, and has a bounded
restart policy. Installation never enables it silently.

The container GUI is a supported homelab/server profile, not the product
foundation. It uses the exact GUI/core pair named by the suite manifest, runs
non-root with a constrained capability set, keeps rebuildable cache state
separate from native processes, and may share the canonical vault only through
the documented mount. Host-native CLI/MCP and the container GUI must be able
to operate on one disposable vault without turning cache or GUI state into
authority.

## Explicitly non-canonical

The following are not release requirements and must not become hidden
dependencies:

```text
Docker-only all-in-one
mandatory POWER daemon
remote unauthenticated MCP
public MCP, Federation, A2A, or distributed multi-writer state
```

The existing maintainer fleet updater is operational infrastructure and stays
separate from the product updater. The product updater consumes a complete,
hash-bound suite manifest and uses stage/verify/activate/readback/rollback
semantics. If that updater is not proven safe, automatic updates remain
disabled and the documented exact-version manual path is used.

## Evidence policy

The release gates must use exact source and artifact identities. A passing
unit test is not evidence for a clean install, a real subprocess protocol
client, a container image, or a published artifact unless that gate actually
runs the corresponding surface.

`M2_HUMAN` remains `EXCLUDED_BY_POLICY`; sealed human evaluation remains
`DO_NOT_OPEN`; no human retrieval-quality claim is emitted. Retrieval is not
retuned as part of suite unification unless a direct code/config change
invalidates the existing machine-only evidence.

## Freeze inputs

The clean worktrees for this implementation are based on the fetched public
heads:

| Component | Version/tag | Source SHA |
| --- | --- | --- |
| POWER core | 3.6.6 / `v3.6.6` | candidate base `origin/main` `527cc8a77187e9fa6d724b604d1a6634545da575`; tag commit `6c6b6ae52f4b29382f0d2ec82fbb4e75ba1f471a` |
| POWER-GUI | 0.7.4 / `v0.7.4` | candidate base `origin/main` `068b4d32d5d55170de52c81a897526e3d640078a`; tag commit `f1c918c7a8c6de011ff0553f08d00675ad296f59` |

The pre-existing dirty worktrees under `projects/P.O.W.E.R` and
`projects/ai-second-brain-gui` are intentionally excluded from this freeze;
they remain untouched and are not silently folded into the candidate.

## Blocker ledger at freeze

The following gates are open and must be closed or explicitly reported as
NO-GO before a stable release claim:

| ID | Area | Required evidence |
| --- | --- | --- |
| B0 | exact version pair | source/tag/version readback and compatibility manifest |
| B1 | public MCP entry | `power-mcp` console script and clean stdio smoke |
| B2 | MCP SDK | supported adapter inventory and dual-era subprocess gate |
| B3 | business boundary | automated transport-boundary test with zero bypasses |
| B4 | Skill packaging | wheel extraction, tree hash, generic install/check |
| B5 | native suite | disposable HOME installer and content-free receipt |
| B6 | manifest | candidate and final suite manifests with exact hashes |
| B7 | native GUI | opt-in `systemd --user` lifecycle and native E2E |
| B8 | container profile | pinned pair, non-root/health/cache evidence |
| B9 | cross-runtime safety | host CLI/MCP plus container GUI concurrency/recovery |

No feature ring is added to close these blockers. A blocker that cannot be
fixed within the existing architecture produces a documented NO-GO rather than
an unbounded redesign.
