# POWER 3.8 Pre-Phase-5 Foundation Hardening Gate

> **Status:** ADMISSION CANDIDATE / IMPLEMENTED / LOCALLY VERIFIED / PROTECTED MERGE REQUIRED
>
> **Publication class:** planning-only acceptance contract
>
> **Implementation status:** IMPLEMENTED ON THE FOUNDATION CANDIDATE; MERGED-MAIN STATUS REQUIRES THE PROTECTED NORMAL MERGE
>
> **Scope boundary:** this gate is an integration admission before Phase 5. It
> does not reopen or rewrite Phase 0–4 evidence and it does not implement Phase
> 5, capture adapters, ContextPack runtime, IndexWorkQueue runtime, or model
> ingestion.

## Gate intent

Pre-Phase-5 Foundation Hardening closes the security and authority gaps that
would otherwise make new agent-facing retrieval surfaces unsafe. The gate must
be admitted through a bounded implementation PR, exact-head checks, independent
security review, and a protected normal merge. A planning document is not
evidence that any finding is fixed.

```text
PHASES 0–4: CLOSED / FROZEN
        ↓
Foundation Hardening admission
        ↓
Phase 5A runtime contracts v2 + frozen evaluation corpus
```

## Current findings to revalidate

Each finding below is a planning input. The future implementation must re-read
the exact source and tests on its candidate head before choosing a remediation.

### F1 — implicit mutation authority

Current-code evidence to revalidate:

- `src/power_framework/web/routes/notes.py` exposes an apply form whose default
  approval value is truthy.
- `src/power_framework/web/clients/power.py` has a truthy default for the apply
  client argument.
- The core application boundary already has an explicit approval/authority
  contract, so the web boundary must not weaken it.

Future target:

```text
write or mutation without explicit authorized context
    → fail closed
```

Acceptance evidence must include a request with the approval field omitted, a
request with a malformed approval value, and a proof that no vault, proposal,
task, decision, or index state changes in either case.

### F2 — identity and principal semantics

`actor: str` is an attribution field, not authentication. Revalidate the
application request models, web session boundary, MCP caller context, and local
offline path. Define a future principal/session binding that supports local and
offline operation without inventing a cloud identity system.

Acceptance evidence must prove:

- an unbound or expired principal cannot obtain mutation authority;
- actor labels cannot mint authentication or approval;
- the bound principal is included in bounded, secret-free receipts;
- local/offline use has an explicit trusted boundary and does not silently
  become anonymous apply authority.

### F3 — retrieval database override boundary

Revalidate the application retrieval path and all web/MCP clients for
environment-controlled external search-database overrides. An operator
environment variable must not let an agent-facing request bypass the configured
vault/source boundary or select an arbitrary database.

Acceptance evidence must include:

- an unsafe external override is rejected or ignored by a server-derived policy;
- retrieval is contained by the configured vault and source projection;
- path traversal, symlink, URI, and private-network override attempts fail
  closed;
- direct ApplicationService and agent-facing Web/MCP behavior are equivalent.

### F4 — failure receipts

Revalidate failed mutation, retrieval, authentication, and adapter-facing
operations. Define whether a failed operation emits a bounded structured receipt
and which fields are permitted. Receipts must preserve evidence of the failure
without copying secrets, credentials, raw sensitive payloads, arbitrary model
output, or unbounded exception text.

Acceptance evidence must prove:

- deterministic receipt shape and correlation identifier;
- bounded size and explicit redaction of secrets/content;
- no receipt is falsely marked successful or committed;
- rollback/recovery state is distinguishable from a successful apply;
- repeated failure handling is idempotent and replay-safe.

### F5 — deadline and budget semantics

A post-action elapsed-time check is not cancellation. Revalidate synchronous and
asynchronous application operations, offload helpers, queue leases, and Web/MCP
timeouts. The future contract must distinguish a deadline that rejects work
before execution, a cooperative cancellation signal, a bounded worker budget,
and a receipt for work that could not be cancelled after it began.

Acceptance evidence must prove:

- a deadline is enforced before an unsafe or expensive operation starts;
- async work receives actual cancellation or bounded isolation semantics;
- sync/offloaded work cannot exceed the configured worker and result-size budget;
- timeout, cancellation, and completed-after-deadline outcomes are distinct;
- no timeout path silently mutates or reports an unverified result.

## Required gate evidence

The Foundation Hardening candidate must provide:

1. exact base/head/tree/parent tuple and a source-only diff audit;
2. targeted regression tests for F1–F5 plus existing PSE/Task/Decision/crash
   recovery contracts;
3. Web/MCP boundary tests for approval, principal binding, vault scope,
   redaction, cancellation, and result budgets;
4. independent security review covering path traversal, SSRF, shell injection,
   secret handling, authentication, authorization, and input validation;
5. full applicable lint/type/test/security gates and a protected exact-head
   normal merge;
6. a bounded failure/recovery receipt with no secret or raw-content leakage;
7. an append-only handoff recording all candidate epochs and any unresolved
   decision.

## Non-goals and stop boundaries

- Do not reopen Phase 0–4 closure or rewrite historical handoffs.
- Do not implement Phase 5 retrieval contracts, router, scope pushdown,
  ContextPackCompiler, or MCP context tools in this gate.
- Do not add a cloud identity provider, vector database, capture adapter, or
  persistent IndexWorkQueue merely to satisfy this contract.
- Do not broaden permissions, disable protection, use admin bypass, or treat a
  caller-supplied boolean as a principal.
- Do not claim a finding is resolved from a unit test alone when the boundary
  requires live policy, integration, or adversarial evidence.

## Admission decision

```text
FOUNDATION_HARDENING: ADMISSION CANDIDATE / IMPLEMENTED / LOCALLY VERIFIED / PROTECTED MERGE REQUIRED
PHASE_5: READY FOR SEPARATE PHASE 5A ADMISSION / NOT STARTED
PHASES_0_4: CLOSED / FROZEN
NEXT_RUNTIME_GATE: PROTECTED NORMAL MERGE AND POST-MERGE FOUNDATION VERIFICATION
```
