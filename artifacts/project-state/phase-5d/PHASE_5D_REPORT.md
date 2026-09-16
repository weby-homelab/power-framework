# Phase 5D (P38-WP02) Engineering Report

## Multi-Domain RetrievalPlanner + Conflict Resolution + ContextPack Read-Only Vertical Slice

```text
STATUS: IMPLEMENTED & VERIFIED
PR BOUNDARY: PR-5D-B
BASE COMMIT: b8ee40ab1286c12ad12a78f28877bc9da924ebf4
TEST SUITE: 50 / 50 PASSING (Phase 5D) + 35 / 35 PASSING (Phase 5A Regression)
```

---

## 1. Executive Summary

Phase 5D delivers the foundational read-only vertical slice connecting query intent to a bounded, server-issued ContextPack. The slice enforces a strict authority hierarchy over semantic similarity, isolates untrusted retrieved data through deterministic screening and redaction, guarantees caller anti-forgery via runtime compiler tokens, prevents budget escalation, and maintains absolute zero query-side disk mutations.

---

## 2. Core Architecture & Runtime Components

### 2.1 RetrievalPlanner (`power_framework.core.retrieval_planner`)
- **Multi-Domain Routing:** Interfaces with `RetrievalDomainRouter` and `DomainPolicyRegistry` to determine relevant domains, respecting `max_domains` budget caps.
- **Privileged Access Gate:** Fails closed (`SearchScopeAccessDeniedError`) when privileged scopes (`include_archived`, `include_quarantine`) are requested without an explicit, server-issued privileged `AccessPolicy`.
- **Bounded Retrieval Stages:** Executes class-compliant retrieval pipelines:
  - `PROJECT_STATE`: Canonical ledger retrieval (`TaskService`, `DecisionService`).
  - `FTS`: Scoped lexical BM25 retrieval.
  - `SEMANTIC`: Vector search (enabled under BALANCED/DEEP profiles with active generation).
  - `GRAPH_ASSISTED`: Bound graph expansion within scope.
  - `RERANK` / `RAW_FALLBACK`: Bounded fallback stages with explicit skipping tracking (`attempted | skipped == planned`).
- **Deduplication:** Merges cross-domain and multi-stage duplicate items, preserving the highest authority and highest score.
- **Safety Screening:** Non-destructively screens candidate excerpts:
  - *Prompt Injections:* Flagged with `_INJECTION_PATTERN`, quarantined to `TrustState.QUARANTINED`, and excluded for unprivileged callers (`"quarantine_policy_excluded"`).
  - *Secret Leaks:* Redacts GitHub tokens, passwords (`AddMax13$`), and private keys to `[REDACTED_SECRET]` with `redaction_status="redacted"`.
  - *Authority Spoofs:* Unbacked assertions of canonical status in raw text are downranked to `Authority.UNVERIFIED` and `TrustState.RAW`, and excluded for unprivileged callers (`"raw_access_denied"`).
  - *Noise Filter:* Whitespace and near-empty excerpts are marked `NoiseState.DOWNRANKED`.
- **Evidence Ordering Policy:** Sorts candidates strictly by:
  1. Authority rank (`CANONICAL` > `VERIFIED` > `CURATED` > `PROPOSED` > `UNVERIFIED` > `UNKNOWN`).
  2. Temporal freshness (`CURRENT` > `STALE` > `EXPIRED`).
  3. Supersession (`ACTIVE` > `SUPERSEDED`).
  4. Contradiction (`NONE` > `CONFLICTED`).
  5. Semantic score (descending).
  6. Source identifier (deterministic tie-breaker).
- **Runtime Audit:** For authority-sensitive queries (`PROJECT_STATE`, `TASK`, `DECISION`, `GOVERNANCE`), asserts that raw evidence never outranks canonical evidence (`RuntimeError("AUTHORITY_ORDER_VIOLATION")`).

### 2.2 ContextPackCompiler (`power_framework.core.context_compiler`)
- **Bounded Packing:** Enforces `max_candidates`, `max_tokens`, and aggregate byte ceiling (`MAX_CONTEXT_PACK_BYTES = 256_000`).
- **Explainability Generation:** Produces bounded explainability decisions (<= 64 records, each <= 128 characters) and source revisions.
- **Server-Issued Factory:** Constructs `ContextPack` with `implementation_status="compiled"` stamped with private `_CONTEXT_COMPILER_TOKEN`.
- **Copy Immunity:** Overrides `model_copy()` to forbid copying or mutation of server-issued packs.

### 2.3 Context Contracts (`power_framework.core.context_contracts`)
- **Anti-Forgery Invariants:** `validate_pack_access` enforces that any pack with `implementation_status="compiled"` must carry the server's `_CONTEXT_COMPILER_TOKEN`.
- **RuntimeContractEnvelope Integration:** Envelope validator `bind_discriminator` rejects raw or unauthenticated compiled packs.
- **Backward Compatibility:** Preserves historical Phase 5A `implementation_status="planned"` fixtures without requiring compiler tokens.
- **Budget Policy Layering:** `RetrievalBudgetPolicy.default(caller_hint=...)` enforces pure layering where caller hints can only lower caps, raising `CallerBudgetEscalationError` if higher limits are attempted.

### 2.4 ApplicationService (`power_framework.core.application`)
- **`compile_context(...)`:** Read-only use case returning `ApplicationEnvelope(operation="compile_context", status="ok")` with duration receipt and zero mutations (`mutation=False`).
- **Parity Assurance:** Principal parity verified between `Principal.local_cli()` and `Principal.local_mcp_stdio()`.
- **Zero New Public MCP Tools:** Deferred public FastMCP exposure to Phase 5G.

---

## 3. Verified Invariants Matrix

| Invariant | Specification | Verification Result |
| :--- | :--- | :--- |
| **Authority over Similarity** | Canonical ledger records outrank higher semantic scores for authority-sensitive queries. | **PASS** (`test_authority_sensitive_ordering_canonical_beats_high_semantic_score`) |
| **Domain != Authority** | Domains partition retrieval space; authority is derived from verified provenance. | **PASS** (`test_deduplication_preserves_highest_authority_and_score`) |
| **Retrieved Text Untrusted** | Untrusted text cannot elevate trust or claim Truth/Action authority. | **PASS** (`test_retrieved_text_never_grants_truth_or_action_authority`) |
| **Anti-Forgery Token** | Callers cannot directly instantiate or deserialize compiled ContextPacks. | **PASS** (`test_caller_cannot_instantiate_compiled_pack`, `test_runtime_contract_envelope_rejects_unauthenticated_compiled_dict`) |
| **Budget Escalation Rejection** | Caller hints exceeding server caps raise `CallerBudgetEscalationError`. | **PASS** (`test_compile_context_caller_budget_escalation_rejection`) |
| **Zero Query-Side Writes** | Vault directory tree SHA-256 is 100% identical before and after repeated queries. | **PASS** (`test_compile_context_zero_query_side_writes_vault_unmodified`) |
| **Non-Destructive Screening** | On-disk files remain byte-for-byte identical during safety screening. | **PASS** (`test_non_destructive_screening_files_untouched`) |
| **Deterministic Accounting** | Consumed tokens equal bounded sum of item costs under `power.tokens.deterministic.v1`. | **PASS** (`test_deterministic_token_accounting`) |
| **Zero Public MCP Tools** | Phase 5D registers 0 new FastMCP tools; verified at `ApplicationService` boundary. | **PASS** (Zero MCP registrations in Phase 5D) |
| **Legacy Retrieval Default** | `ApplicationService.retrieve()` legacy retrieval remains default behavior. | **PASS** (`tests/test_foundation_hardening.py` unaffected) |

---

## 4. Test Matrix Summary (50 Items)

1. **`tests/test_phase5d_retrieval_planner.py` (10 tests):**
   - FAST, BALANCED, DEEP plan generation and stage partitioning.
   - Domain router integration and scoping.
   - Multi-stage retrieval and deduplication.
   - Stage accounting completeness (`attempted | skipped == planned`).
   - Fallback degradation reasons.

2. **`tests/test_phase5d_context_compiler.py` (11 tests):**
   - Candidate budget limit enforcement.
   - Token budget ceiling enforcement.
   - Byte budget limit enforcement.
   - Anti-forgery direct instantiation rejection.
   - Anti-forgery deserialization rejection.
   - `model_copy()` mutation rejection.
   - `RuntimeContractEnvelope` binding and forgery rejection.
   - Deterministic token accounting and canonical serialization.
   - Historical `"planned"` status preservation.

3. **`tests/test_phase5d_authority_security.py` (14 tests):**
   - Prompt injection quarantine (unprivileged exclusion vs privileged retention).
   - Secret redaction (GitHub tokens, AddMax13$, RSA private keys).
   - Authority spoof downranking (unbacked claims forced to RAW/UNVERIFIED).
   - Authority ordering invariant (`Authority.CANONICAL` > `Authority.CURATED` with higher score).
   - Temporal boundary & supersession filtering.
   - Non-destructive disk verification.
   - Empty noise downranking.
   - Cross-domain deduplication.
   - Untrusted text authority denial.
   - Authority violation runtime invariant audit.

4. **`tests/test_phase5d_application_service.py` (15 tests):**
   - `Principal.local_cli()` invocation.
   - `Principal.local_mcp_stdio()` invocation.
   - CLI vs MCP STDIO caller parity.
   - Default intent (`LOOKUP`).
   - Automatic unprivileged `AccessPolicy` derivation.
   - Privileged scope rejection without policy.
   - Privileged scope acceptance with approval reference.
   - Caller budget escalation rejection (`CallerBudgetEscalationError`).
   - Zero query-side disk writes audit.
   - Empty query rejection.
   - Bounded explainability format and size limits.
   - Task and decision canonical integration.
   - Deterministic token accounting parity.
   - Audit receipt emission.
   - String and enum parameter coercion.

5. **Regression Verification:**
   - `tests/test_phase5a_runtime_contracts.py`: 35 / 35 PASSING.

---

## 5. Conclusion & Transition to Gate Merge

Phase 5D runtime implementation and tests are complete, fully validated, and ready for commit and PR submission (PR-5D-B).
Post-merge governance updates will follow under PR-5D-C.
Phase 5E, Phase 5F, Phase 5G, and POWER 3.8.0 release actions remain strictly NOT STARTED.
