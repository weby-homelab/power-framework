# ADR-0008: Phase 5D Runtime ContextPack Issuance and Authorization Boundary

## Status

Accepted. Authoritative architectural decision for Phase 5D (P38-WP02) runtime ContextPack issuance, contract tightening, MCP boundary separation, and access policy ownership.

---

## Context

Phase 5A introduced `ContextPack` in `power_framework.core.context_contracts` under schema version `power.context-runtime.v2`. In Phase 5A, the contract was intentionally bounded to:
```python
class ContextPack(RuntimeModel):
    ...
    implementation_status: Literal["planned"]
```
This allowed downstream components to establish schemas, DTO boundaries, and envelope wrapping before runtime retrieval was implemented.

Phase 5D (P38-WP02) implements the read-only vertical slice:
```text
QueryIntent → RetrievalDomainRouter → DomainMatch[] → effective SearchScope
            → RetrievalPlanner → bounded retrieval stages → ordering
            → ContextPackCompiler → server-issued bounded ContextPack
```

This raises critical architectural and security requirements:
1. **Server-Issued Authority:** A runtime `ContextPack` represents an authoritative, budget-bounded compilation of retrieved evidence. A caller must never be able to manufacture, forge, or tamper with runtime completion status.
2. **Contract Preservation:** There must remain exactly one conceptual `ContextPack` model; parallel competing models (e.g. `ContextPack2`, `SmartContext`, `ContextBundle`) are prohibited.
3. **Phase 5A Fixture Compatibility:** Historical Phase 5A "planned" fixtures and contracts must remain valid without breakage.
4. **Phase 5D vs Phase 5G MCP Boundary:** Disambiguate core application parity from public MCP tool exposure.
5. **Access Policy Ownership:** `AccessPolicy` is server-derived; callers cannot grant themselves privileged raw or quarantine access.

---

## Decision

### 1. Contract Representation & Truthful Status
The contract schema version remains:
```text
power.context-runtime.v2
```
The field `implementation_status` in `ContextPack` is tightened from `Literal["planned"]` to:
```python
implementation_status: Literal["planned", "compiled"]
```
- `"planned"` represents a planned specification or historical Phase 5A fixture (no runtime execution claim).
- `"compiled"` represents a server-issued, fully executed and compiled runtime context pack.

### 2. The Server-Issued Pack Rule
```text
CALLER_CAN_FORGE_RUNTIME_CONTEXTPACK = FALSE
```
Runtime issuance follows the exact proven pattern of `AccessPolicy` and `MemoryActionDecision`:
- A private module-level sentinel token `_CONTEXT_COMPILER_TOKEN = object()` is defined in `context_contracts.py`.
- `ContextPack` includes a private attribute `_issuer_token: object | None = PrivateAttr(default=None)`.
- In `@model_validator(mode="after") def validate_pack_access(self)`:
  ```python
  if self.implementation_status == "compiled" and self._issuer_token is not _CONTEXT_COMPILER_TOKEN:
      raise ValueError("compiled ContextPack must be server-issued by ContextPackCompiler")
  ```
- Because private attributes cannot be set by Pydantic's `__init__`, `model_validate()`, or arbitrary JSON deserialization, any caller attempting `ContextPack(..., implementation_status="compiled")` or `model_validate({"implementation_status": "compiled", ...})` fails closed with a validation error.
- `model_copy(update={"implementation_status": "compiled"})` resets private attributes in Pydantic v2 and fails closed.

### 3. Authorized Issuance Boundary
Only the authorized `ContextPackCompiler` boundary (via `ContextPack._from_compiler(...)` factory) may attach `_CONTEXT_COMPILER_TOKEN`. Arbitrary caller code or external inputs cannot call this private factory with valid arguments without executing the authorized compiler.

### 4. RuntimeContractEnvelope Invariant
In `RuntimeContractEnvelope.bind_discriminator`:
When the discriminator is `ContractName.CONTEXT_PACK` (or `ContextPack`):
- If the payload specifies `implementation_status == "compiled"`, the envelope strictly verifies:
  ```python
  if expected is ContextPack and payload_status == "compiled":
      if not isinstance(payload, ContextPack) or payload._issuer_token is not _CONTEXT_COMPILER_TOKEN:
          raise ValueError("ContextPack payload with compiled status must be server-issued by ContextPackCompiler")
  ```
- Unauthenticated caller JSON in an envelope can never acquire `"compiled"` issuance authority.

### 5. Deterministic Serialization & Canonical Bytes
Deterministic serialization is preserved using `RuntimeModel.model_dump_canonical_json()`, ensuring:
- Lexicographically sorted dictionary keys.
- Deterministic IEEE-754 float formatting with `AfterValidator(_finite)`.
- UTF-8 byte encoding.
- SHA-256 digest computation over canonical bytes.

### 6. Phase 5D vs Phase 5G MCP Boundary
To resolve the planning tension between Phase 5D and Phase 5G:
- **Phase 5D owns:**
  - Core `RetrievalPlanner`
  - Core `ContextPackCompiler`
  - Bounded read-only `ApplicationService.compile_context(...)` operation
  - Transport-neutral schemas and envelopes
  - `Principal.local_cli()` vs `Principal.local_mcp_stdio()` semantic parity tests
- **Phase 5G owns:**
  - Public MCP tool registration (`compile_context`, `explain_context`, `retrieval_plan`, `index_status`, `index_cost`)
  - Server tool-count decisions and FastMCP exposure
- **Phase 5D Invariant:** NO NEW PUBLIC MCP TOOLS are registered during Phase 5D. Parity is verified at the `ApplicationService` layer using trusted principal bindings.

### 7. Access Policy Ownership & Privileged Access Stop Rule
- `AccessPolicy` is strictly server-derived.
- Default production Phase 5D behavior:
  ```text
  raw_access = "none"
  quarantine_access = "none"
  include_archived = False
  include_quarantine = False
  redaction = "mandatory"
  ```
- Any unverified caller request for privileged raw or quarantine access fails closed (`ValueError` / `SearchScopeAccessDeniedError`).
- In the absence of an end-to-end cryptographic capability authorization chain, Phase 5D strictly defaults to unprivileged access. Positive privileged authorization remains an architectural follow-up.

---

## Answers to Mandatory ADR Questions

1. **What runtime contract revision represents a compiled ContextPack?**
   `power.context-runtime.v2`.
2. **Is the existing power.context-runtime.v2 ContextPack preserved, tightened, versioned, or superseded?**
   Preserved and tightened with private issuance token enforcement.
3. **How are historical Phase 5A "planned" fixtures preserved?**
   `implementation_status="planned"` remains fully valid for planned DTOs and test fixtures without requiring an issuance token.
4. **Who may issue a runtime ContextPack?**
   Exclusively `ContextPackCompiler` via `ContextPack._from_compiler(...)`.
5. **How does arbitrary caller JSON fail to become a runtime-issued pack?**
   `validate_pack_access` rejects `implementation_status="compiled"` unless `_issuer_token is _CONTEXT_COMPILER_TOKEN`. Private attributes cannot be set from JSON.
6. **How does RuntimeContractEnvelope prevent forged runtime completion?**
   Envelope discriminator validation verifies the payload object instance and its `_issuer_token`.
7. **What exact truthful implementation/runtime status is serialized?**
   `"compiled"` for compiler-issued packs; `"planned"` for specifications.
8. **Does the change require a new runtime schema identity?**
   No. Schema identity remains `power.context-runtime.v2`.
9. **How is deterministic serialization preserved?**
   Canonical JSON dumping with sorted keys, finite float validation, and UTF-8 encoding.
10. **How is backward compatibility tested?**
    All 35 existing Phase 5A runtime contract tests pass unchanged.
