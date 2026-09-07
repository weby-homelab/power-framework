# P.O.W.E.R. Threat Model

## Overview

P.O.W.E.R. is a local-first Python framework that validates, indexes, searches,
and mutates Markdown knowledge vaults through a CLI and an MCP server. Its
primary security objective is to preserve vault confidentiality, integrity, and
availability while making automation explicit and reviewable. The framework is
a library and local agent tool, not a hosted multi-tenant service.

This model covers the repository's runtime surfaces at the version below. It
does not claim that every user vault, MCP client, model provider, or operator
environment is trustworthy.

## Threat Model, Trust Boundaries, and Assumptions

### Assets and security objectives

- **Vault content and metadata:** notes can contain private, internal, or
  sensitive data. Unapproved disclosure or modification is unacceptable.
- **Vault filesystem integrity:** writes must remain in the selected vault,
  preserve valid Markdown/OKF structure, and remain recoverable after normal
  process failures.
- **Governed memory history:** a proposal, explicit approval, stale-write
  check, and append-only receipt make memory mutations attributable.
- **Credentials and configuration:** environment variables, local model assets,
  and provider keys must never be emitted in responses, logs, or receipts.
- **Local availability and resource bounds:** malformed vault data, remote
  endpoints, model assets, and MCP callers must not cause uncontrolled work,
  deadlocks, or unexpected network use.

### Trust boundaries

| Boundary | Trusted side | Untrusted or separately trusted side | Required invariant |
| --- | --- | --- | --- |
| CLI/MCP input to core | validated core APIs | paths, note text, queries, proposal JSON, MCP arguments | Treat inputs as untrusted; validate before read/write/network use. |
| Vault root to host filesystem | selected canonical vault | traversal strings, symlinks, absolute paths, arbitrary parents | No read or write may escape the configured vault. |
| Canonical source projection to source.read | validated source records | in-vault regular files, invalid Markdown, hidden control material, projection aliases | Containment is necessary but not sufficient; only a current, regular, non-symlink source record may be read. |
| Read-only retrieval to mutation | search and proposal creation | an agent or caller requesting a change | Proposal creation may write only its content-addressed `.power/proposals/` ledger; it cannot write the target note, catalog, or search. Apply requires explicit `approved=True` and an unchanged pre-image hash. |
| Agent handoff to workflow execution | validated work-packet state | packet objective, next action, retrieved note text, and caller-supplied metadata | `.power/work-packets/` stores content-free Markdown checkpoints; state transitions are idempotent and approval-gated, and no packet operation executes its `next_action`. |
| Local process to network | local ONNX/FTS/index paths | OpenRouter, non-loopback Ollama, link/ROT HTTP targets | Default deny; an explicit sensitivity-appropriate egress policy is required before contact. |
| MCP server to client/transport | configured local server | MCP client input | MCP requires a configured vault root and uses local stdio only; no MCP TCP listener or network peer exists. |
| Repository/CI to dependencies | pinned and reviewed source/dependency policy | packages, model artifacts, GitHub Actions execution | dependency audit, CodeQL, integrity checks, and review gates remain required. |

### Assumptions and non-goals

- The operating-system account and the configured vault root are trusted. A
  local attacker who can already read the vault or alter the installed package
  is outside this framework's isolation boundary.
- Stdio MCP clients and local CLI callers are authorized to read the chosen
  vault. The framework constrains paths and writes; it cannot infer a user's
  authorization intent from arbitrary local processes.
- HTTP MCP is removed from the supported runtime. The Web UI is the only
  network-facing HTTP surface, while native MCP remains local stdio; exposing
  the Web UI remotely requires an authenticated reverse proxy, Tailscale, or an
  equivalent trusted access layer.
- Retrieved note content is data, not instructions. Downstream LLM clients
  must still defend their own prompt and tool-execution boundaries.

## Attack Surface, Mitigations, and Attacker Stories

### Primary runtime surfaces

1. **CLI and library calls** accept a vault directory, Markdown, search text,
   policy settings, and transaction proposals. `source.read` is a
   projection-backed core operation; the Web UI delegates to it and MCP has no
   separate raw-file reader.
2. **MCP tools** expose read, index, ingest, maintenance, and memory operations
   to an MCP client. The server resolves only `POWER_VAULT_DIR`
   before accepting a vault and rejects a substituted root.
3. **Vault parsing and persistence** handle YAML frontmatter, Markdown links,
   SQLite/index files, generated catalogs, and atomic note writes.
4. **Optional external integrations** include non-loopback embedding endpoints,
   OpenRouter query expansion/ROT, and HTTP link checking.
5. **Supply-chain and release automation** build packages, run dependency
   auditing, execute CI, and publish documentation.

### Existing controls

- `core/utils.py::resolve_path_in_vault` rejects absolute paths, traversal,
  control characters, non-Markdown targets, missing parents, and symlink
  escapes. `atomic_write_in_vault` uses descriptor-relative operations and
  `O_NOFOLLOW` for the destination directory.
- `core/source_service.py::_resolve_canonical_source` requires exact or stem
  membership in the active or bounded source projection, applies the existing
  P.A.R.A./ignore/catalog eligibility rules, rejects symlinks and unsupported
  files, and checks source metadata, size, modification time, and SHA-256
  before returning content. Rejected non-source paths use typed, redacted
  not-found behavior.
- Search FTS/vector/semantic/rerank/graph/provenance materialization reuses a
  request-scoped canonical source reader for both file bytes and result
  metadata. The Web client disables the legacy caller-selected search database
  override, and application construction does not create task control state
  until a task operation needs it.
- `core/mutation.py` serializes same-vault mutations with an in-process lock
  plus an advisory cross-process file lock. `core/memory_api.py` requires
  explicit approval, validates content and pre-image hashes, and appends a
  content-free receipt with stable trace/span identifiers and an idempotency key.
- `core/handoff.py` validates a durable Markdown packet state machine, writes
  immutable checkpoints atomically, enforces maintenance phase order and
  approval, and counts input-required/approved-maintenance/cancellation human
  interventions without storing retrieved note content.
- `core/egress.py` defaults `POWER_EGRESS_POLICY` to `deny`; remote embeddings,
  query expansion, and ROT paths call the policy guard before network use.
  Loopback model endpoints are treated as local.
- `core/model_policy.py` is the single model-acquisition boundary. It treats
  model names and overrides as untrusted, gives explicit offline flags
  precedence, authorizes remote HF calls through `core/egress.py`, requires
  immutable approved operation/provider/license identities and complete
  runtime-file hashes, and verifies bytes before any model loader receives
  them. Delegated loaders receive a private staging directory containing only
  the approved files. Remote HF acquisition is restricted to the exact HTTPS
  `huggingface.co` origin.
- `mcp/power_server.py` validates the configured vault root, limits write and
  index request rates, masks error details, and fails closed for non-loopback
  HTTP transport.
- `core/models.py` and parser paths use typed validation and safe YAML parsing;
  CI runs lint, type checks, tests, dependency audit, package smoke tests, and
  CodeQL.

### Attacker stories and residual risk

- A malicious note or MCP argument attempts `../`, a symlink swap, or an
  absolute filename to overwrite a host file. Path and atomic-write controls
  must reject it before a file descriptor outside the vault is used.
- A caller requests `.power` state, a JSON/SQLite file, invalid Markdown, or a
  symlink through `source.read`. Filesystem containment alone does not
  authorize the request; the source projection must reject it without
  returning file contents, size, digest, or control-path metadata.
- An agent submits a memory proposal without approval, tampers with its durable content
  hash, or applies it after another writer changed the note. The transaction
  API must reject all three cases and preserve receipts without storing note
  content in history.
- A retrieved note tells an agent to bypass approval or execute a packet's next
  action. The packet persists that text only as untrusted caller data, keeps
  authority and approval fields independently validated, and has no execution
  primitive; the agent must reject the instruction.
- A vault contains internal/sensitive text while a remote provider is
  configured. The policy must deny egress unless the operator selected a policy
  at least as permissive as the content sensitivity. Configuration alone is
  not an authorization grant.
- A hostile or unreliable remote link/model endpoint attempts to consume time,
  return malformed responses, or influence downstream reasoning. The current
  controls limit which calls may start. Model downloads additionally require
  central egress authorization, offline precedence, immutable identity approval,
  and complete hash verification before execution; callers must retain
  timeouts, response validation, and treat returned text as untrusted data.
- A local process with the same OS privileges uses the MCP stdio server or
  reads `.power` state. This is a host authorization concern; do not expose the
  server remotely until the transport has authenticated client identity and
  vault-scoped authorization.

## Severity Calibration

### Critical

Critical issues allow an unauthenticated remote party or a default installation
to read arbitrary sensitive vault content, write outside the vault, or execute
code without meaningful operator action. Examples include bypassing the
loopback-only MCP transport to expose unauthenticated write tools, or a
default-policy egress bypass that sends sensitive notes to an attacker.

### High

High issues let a malicious vault, MCP client, or configured provider cross a
core security boundary under realistic use. Examples include a reliable
path/symlink bypass of `atomic_write_in_vault`, applying an unapproved or stale
proposal, leaking full note text through error/log output, or an explicit-policy
egress path that misclassifies sensitive content as public.

### Medium

Medium issues require local access, a trusted client, or non-default operator
configuration but can damage a vault or significantly reduce availability.
Examples include a same-vault mutation lock bypass causing consistent index
corruption, rate-limit bypass for MCP write tools, or unbounded handling of a
malformed remote response after egress was explicitly allowed.

### Low

Low issues have limited impact or need substantial trusted preconditions.
Examples include inaccurate non-sensitive diagnostics, a bounded local denial
of service that requires write access to the vault, or a documentation mismatch
that does not alter runtime enforcement. Informational observations without a
credible boundary crossing are not security findings.

Repository: weby-homelab/power-framework
Version: 3.7.11

## WEB-01 and WEB-05 closure record

Both findings were identified against the `3.7.11` baseline commit
`be83652aec2daedeb2c98b604b5a49d13e989c7e`; their identifiers remain preserved
for traceability. The focused locked-environment security matrix passed with
461 tests.

- **WEB-01 (P1) — CLOSED:** source-read authority is now the canonical
  projection boundary, with existing scope/ignore/Markdown/OKF rules, regular
  non-symlink checks, typed redacted rejection, and projection freshness/hash
  validation. Evidence: `tests/test_source_projection.py`,
  `tests/test_application_v2.py`, and
  `tests/web/contract/test_app_routes.py`.
- **WEB-05 (P1) — CLOSED:** direct and delegated model loaders now share the
  model policy boundary for deny-before-network, all maintained offline flags,
  immutable approved operation/provider/license identity, complete runtime
  hashes, and private verified-file staging before construction. Evidence:
  `tests/test_model_policy.py`,
  `tests/test_embeddings.py`, `tests/test_reranker.py`, and
  `tests/test_egress.py`.

This local closure does not claim remote CI, CodeQL, Docs, package-audit,
dependency-refresh, merge, or release gates. Phase 4 and version `3.7.11`
remain unchanged.

The full local locked suite subsequently passed with **1755 passed, 14 skipped,
4 warnings**, and **82.94% coverage**.
