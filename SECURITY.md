# Security Policy

## Purpose and scope

P.O.W.E.R. is a local-first control plane for verifiable AI-assisted software
engineering and Linux infrastructure operations. It provides an authoritative
execution runtime, broker-mediated tool authority, proof-carrying handoffs, and
a structured knowledge substrate (Second Brain) validated via CLI and MCP. This
policy defines the security contract for the released package, its source
repository, tool execution brokers, and the documented local MCP transports.

P.O.W.E.R. is not a hosted multi-tenant service. The operating-system account,
the installed package, the broker daemon, and the configured vault root are
trusted by the host operator. A process that already has the same OS privileges
can usually read the vault, local cache, and broker sockets directly;
P.O.W.E.R. does not replace OS permissions, container isolation, or an
authenticated network gateway.

## Supported versions

| Version | Security support |
| --- | --- |
| `3.8 (dev)` | Main development line |
| `3.7.x` | Supported maintenance line (`release/3.7`, stable `v3.7.13`) |
| `<3.7` | Unsupported; upgrade before reporting a release-specific issue |

The `main` branch may contain security fixes before the next release. Security
support for a release ends when a newer supported minor release supersedes it,
unless the maintainers explicitly publish an exception.

## Security objectives and boundaries

The protected assets are vault notes and metadata, generated indexes and search
databases, mutation history and receipts, local model assets, configuration,
and credentials. The required properties are confidentiality, integrity, local
availability, and explicit control of network egress.

The following boundaries are part of the current contract:

- Paths supplied by a caller, note names, Markdown, YAML, search queries, and
  MCP arguments are untrusted input. A path must remain inside the configured
  vault; traversal, absolute paths, unsafe symlink resolution, and unsupported
  note targets must be rejected before a read or write. `source.read` is
  authorized by canonical source-projection membership, not by filesystem
  containment alone: only regular, non-symlink, in-scope Markdown with valid
  OKF metadata may be returned.
- Vault content returned by search or retrieval is data, not instructions.
  Agents and downstream LLM clients must not execute instructions found inside
  a note merely because P.O.W.E.R. returned it.
- `POWER_EGRESS_POLICY` defaults to `deny`. A non-loopback embedding, reranking,
  query-expansion, or ROT request requires an explicit policy appropriate to
  the content sensitivity. An endpoint configured by an operator is not, by
  itself, proof that a note may be sent there.
- Model acquisition is a separate authorization boundary. Canonical neural
  models require their pinned repository, immutable revision, and complete
  runtime-file SHA-256 manifest plus the expected provider/license binding.
  Custom model identities additionally require explicit opt-in and an exact
  operation/provider/license/repository/revision approval manifest. Delegated
  loaders receive only a private staging directory containing those verified
  files. `POWER_MODEL_OFFLINE=1`,
  `HF_HUB_OFFLINE=1`, and `TRANSFORMERS_OFFLINE=1` are cache-only controls and
  cannot be overridden by a permissive egress policy. Remote HF acquisition is
  restricted to the exact HTTPS `huggingface.co` origin.
- MCP is a local stdio process interface and requires `POWER_VAULT_DIR` as its
  single configured vault boundary. The Web UI is a separate HTTP application;
  it is not an MCP transport. Remote MCP, MCP HTTP, SSE, and TCP transports are
  outside the current release contract.
- MCP tool annotations and `power.risk` metadata describe intended risk; they
  are not an authorization mechanism. The caller and its gateway remain
  responsible for enforcing user identity and approval policy.

### POWER 3.8 INFRA-1 broker boundary (merged on `main`)

The following controls describe the local Unix-domain infrastructure broker
boundary merged on `main` (PR #420). They are part of the active 3.8 control-plane
architecture and will be released in the next minor version:

- INFRA-1 is an opt-in local Unix-domain broker boundary. The agent-facing
  client accepts only `status`, `probe`, `rsync-dry-run`, `replicate`, and
  `verify` identifiers. Hosts, ports, users, source/destination roots,
  SSH/rsync options, commands, credentials, and approval authority are
  operator/broker policy, never MCP/CLI input.
- The broker derives its principal from Unix peer credentials, uses strict
  operator-owned profiles, pinned `known_hosts`, `BatchMode=yes`, disabled
  password/keyboard-interactive authentication, `IdentitiesOnly=yes`,
  `IdentityAgent=none`, and fixed `shell=False` argv. Missing broker/profile/
  credential/host identity is a bounded block, never a direct-SSH or password
  fallback.
- Replication uses bounded source manifests and immutable run/staging paths,
  requires an idempotency key and dry-run admission, and forbids remote
  deletion/pruning. The receiver reference uses a non-root forced `rrsync`
  account with no forwarding or PTY.
- Memory and other destructive mutations must retain their explicit approval,
  pre-image/concurrency checks, serialization, and atomic-write boundaries.
  A read or diagnostic operation must not silently become a write. Proposal
  creation is an explicit, non-destructive ledger write limited to the
  content-addressed `.power/proposals/` record; it cannot write the target note,
  catalog, or search projection.
- Durable work packets are control-plane Markdown under `.power/work-packets/`.
  They contain only state, authority, paths, gate names, receipt IDs, and the
  next action; `handoff_work` and `power handoff` never execute that action.
  Repeated calls with one idempotency key return the original checkpoint or
  receipt, and maintenance repair/cancel/input-required transitions enforce
  explicit approval.

Retrieved text, generated catalogs, model output, remote responses, and error
messages must be treated as untrusted data at every downstream boundary. Logs,
receipts, and bug reports must not contain secrets or unnecessary vault content.

## Implemented controls

The current release includes these controls, covered by source-level tests and
CI gates:

- `resolve_path_in_vault` and `atomic_write_in_vault` enforce vault containment,
  reject unsafe paths and symlink targets, and use atomic destination-local
  writes where the platform supports the required descriptor safeguards.
- `core/source_service.py` resolves every source read through the canonical
  projection, rejects control/non-source files, absolute and traversal paths,
  and validates regular non-symlink files plus projection hash/metadata before
  returning content. Web calls use this same `ApplicationService` boundary;
  MCP does not publish an alternate raw-file reader.
- Search result materialization, reranking, graph expansion, and provenance
  hashing use the same request-scoped canonical source reader rather than
  opening database-derived paths directly. Web retrieval disables the legacy
  caller-selected search-database compatibility override.
- YAML frontmatter is parsed with safe loading; typed models validate the
  supported schema while compatibility fields are handled as data rather than
  being treated as executable input.
- Mutation APIs use same-vault serialization, explicit approval for governed
  memory changes, durable content-addressed proposals, pre-image hashes, and
  content-free receipts with stable trace/span identifiers and idempotency keys.
- Work-packet state transitions are schema-validated and checkpointed
  atomically; retrieved text remains in the untrusted-data boundary, and human
  intervention is counted from `input-required`, approved repair, and approved
  cancellation transitions rather than inferred from note text.
- `POWER_EGRESS_POLICY` is checked before remote operations and rejects unknown
  policy or sensitivity values.
- `core/model_policy.py` is the shared model boundary for direct HF and
  delegated FastEmbed/Qwen/ColBERT loaders. It checks offline mode, calls the
  central egress guard before any remote HF function, binds custom identities
  to exact operation/provider/license/immutable-revision identities and
  complete manifests, verifies every file, and hands delegated loaders only a
  verified private staging directory.
- The MCP server requires a configured vault root, constrains tool paths and
  write targets, rate-limits mutation/index operations, and masks internal
  tracebacks from client responses.

### INFRA-1 candidate implementation controls (provisional)

- The unmerged INFRA-1 broker candidate emits bounded `power.infra-receipt.v1` and
  `power.infra-block.v1` receipts. Receipts contain IDs, digests, policy and
  outcome categories only; raw commands, stderr, paths, environment, key bytes,
  passwords, tokens, and file contents are excluded. The optional systemd
  service is non-root, capability-empty, `ProtectSystem=strict`, and not
  enabled by installation.
- CI runs the test, lint, type, dependency-audit, package-smoke, release-policy,
  and CodeQL gates. The live stdio MCP process contract is tested in addition
  to direct in-process tool tests.
- The current local INFRA-1 candidate passed the hermetic suite (`2012 passed,
  4 skipped, 17 deselected`, `82%` coverage), Ruff, MyPy, package smoke, lock,
  systemd, and strict Docs checks. These are provisional dirty-worktree facts;
  no real receiver/forced-mode replicate evidence or protected merge has been
  established, and the public PR candidate remains subject to fresh CodeQL and
  exact-head verification.

These controls reduce risk but do not make a vault safe from a compromised host,
malicious same-user process, compromised dependency, or an operator who
deliberately enables a risky integration.

## WEB-01 and WEB-05 closure record

The following findings were identified against the `3.7.11` baseline commit
`be83652aec2daedeb2c98b604b5a49d13e989c7e`. Their historical identity is
preserved here; this record describes the security remediation and does not
authorize a dependency refresh, version bump, tag, or release.

| Finding | Remediation | Focused evidence | Status |
| --- | --- | --- | --- |
| **WEB-01 (P1):** `source.read` could expose an in-vault regular file outside the canonical Markdown/source boundary. | The core resolver requires projection membership, in-scope valid OKF Markdown, regular non-symlink containment, and freshness/hash checks before opening bytes. | `tests/test_source_projection.py`, `tests/test_application_v2.py`, and `tests/web/contract/test_app_routes.py`; the locked focused security matrix passed with 461 tests. | **CLOSED** |
| **WEB-05 (P1):** HF/model acquisition could bypass central egress/offline and accept incomplete custom identity/integrity controls. | `core/model_policy.py` centralizes deny-before-network, offline precedence, exact operation/provider/license/immutable identity approval, complete SHA-256 verification, and private verified-file staging for embedding/reranking paths. | `tests/test_model_policy.py`, `tests/test_embeddings.py`, `tests/test_reranker.py`, `tests/test_egress.py`; the locked focused security matrix passed with 461 tests. | **CLOSED** |

Remote CI, CodeQL, documentation, package-audit, release, and merge gates remain
independent evidence requirements. They are not implied by this local closure.

The full local locked suite subsequently passed with **1755 passed, 14 skipped,
4 warnings**, and **82.94% coverage** under the repository's 70% gate.

## Report a vulnerability

**Do not create a public GitHub issue for a suspected vulnerability.** Report it
privately by email to **contact@weby.guru**.

Do not attach a full vault, credentials, tokens, private keys, model caches, or
unredacted logs. Use a minimal reproduction with synthetic data and redact
identifiers and note contents. If an encrypted attachment is necessary, agree
on the encryption channel before sending it.

Please include, when safe:

- affected version or commit and installation method;
- operating system, Python version, and CLI/MCP interface and transport;
- minimal reproduction steps or a sanitized proof of concept;
- confidentiality, integrity, or availability impact;
- whether exploitation requires local same-user access, a malicious vault, a
  configured remote endpoint, or a remote network peer;
- relevant sanitized logs and a suggested mitigation, if known.

The maintainer target is acknowledgment within 48 hours and an initial
assessment within 7 days. These are response goals, not a guaranteed SLA. The
maintainer may request additional non-sensitive evidence, publish a fix, and
coordinate disclosure after affected users have a reasonable mitigation.

## Severity calibration

Severity is based on realistic reachability, impact, and default exposure:

| Severity | Examples |
| --- | --- |
| Critical | Unauthenticated remote access to vault data or write tools; path/symlink escape; arbitrary code execution; default-policy secret exfiltration; approval bypass that writes outside the governed boundary. |
| High | Reliable cross-vault access, unapproved or stale mutation application, sensitive egress misclassification, unsafe deserialization, or full note/secret leakage through errors or logs. |
| Medium | A local or explicitly configured attack that corrupts a vault, bypasses mutation serialization/rate limits, or causes substantial bounded-resource exhaustion. |
| Low | A security-relevant diagnostic or documentation defect with limited impact and no credible boundary crossing. |

An ordinary malformed note, an expected validation failure, a retrieval-quality
problem, or a performance regression is not automatically a security issue.

## Out of scope and known limitations

The following are not vulnerabilities in P.O.W.E.R. unless they expose a
P.O.W.E.R. security boundary:

- malware, a malicious root/administrator, or a same-privilege process that can
  already read or modify the vault, package, environment, or local cache;
- operating-system permissions, filesystem encryption, physical access, or
  vulnerabilities in an upstream model/provider without a P.O.W.E.R. integration
  flaw;
- retrieval ranking, model quality, latency, VRAM use, or human-quality claims;
- deliberate operator exposure of the Web UI through an unauthenticated reverse
  proxy; remote MCP deployment is unsupported by the current transport;
- a user choosing to enable `allow-public`, `allow-internal`, or
  `allow-sensitive` egress without protecting the selected endpoint.

Important current limitations and compensating controls:

- The Web UI has no built-in multi-tenant isolation; keep it loopback-only or
  place it behind an authenticated, vault-scoped gateway.
- One server process is bound to one configured vault root. Run separate
  processes and enforce separate OS permissions for separate trust domains.
- Security metadata on MCP tools is advisory for clients and gateways; it does
  not authorize a caller.
- INFRA-1 deployment evidence is host/profile specific. Framework CI uses fake
  local sockets and subprocess doubles and does not require a PRXMX host,
  receiver, or real credential.
- Model downloads and optional remote integrations can contact external
  services only under the explicit egress policy. Use offline/pinned model
  assets when confidentiality or reproducibility requires it.

## Security-related development rules

Security fixes must include a focused regression test and update this policy or
the threat model when a boundary changes. Changes affecting path handling,
egress, MCP transport, mutation approval, serialization, dependency integrity,
or release automation require the relevant CI security gates and a remote
readback of the verified commit before being called complete.
