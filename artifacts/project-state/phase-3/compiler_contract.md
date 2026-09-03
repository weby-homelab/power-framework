# Semantic Compiler Contract — POWER Project State Engine (Phase 3)

- **Framework:** POWER 3.8 — Project State Engine (PSE)
- **Component:** `power_framework.core.semantic_compiler`
- **Specification:** `05_PHASE_3_SEMANTIC_COMPILER.md`
- **Schema Contracts:** `artifacts/project-state/phase-1/semantic-entity-schema-v1.json`
- **Status:** APPROVED & FROZEN

---

## 1. Executive Mission & Architectural Boundaries

The **Project Semantic Compiler** transforms canonical append-only project events and unstructured texts/observations into typed, provenance-bound, validated semantic entities and change proposals.

### Strict Architectural Boundaries:
1. **Candidate & Proposal Production Only:** Phase 3 produces validated semantic entity candidates (`SemanticEntityCandidate`) and contradiction/supersession proposals (`ContradictionProposal`). It **does not** compute the authoritative single-point-of-truth project state projection and **does not** implement `ProjectStateReducer` (which is strictly governed by Phase 4: State Engine & Governance).
2. **Deterministic-First Mandate (G3.1):** All structured events from the canonical ledger (`risk.*`, `assumption.*`, `issue.*`, `dependency.*`, `decision.*`, `observation.recorded`, `lesson.recorded`, `task.*`, `project.*`) are compiled **100% deterministically without invoking any LLM**.
3. **Model Extraction Boundary & Isolation (G3.2 & G3.6):** LLM extraction is reserved strictly for unstructured text (meeting notes, transcripts, external documents) via an abstract provider protocol (`ExtractionProviderProtocol`). Model-extracted entities are unconditionally assigned `verification_status="proposed"` and underlying `provenance.verification_status="unverified"`. Under no circumstances may a model extraction auto-promote an entity to `"verified"`.

---

## 2. Compiler Pipeline Specification

```text
[Input Event / Unstructured Text]
              │
              ▼
   1. Deterministic Normalization
      (Whitespace strip, ISO-8601 formatting, secret scrubbing, passive data isolation)
              │
              ▼
   2. Structured Parser (Deterministic-First, 0 LLM Calls)
      (Direct mapping of 44 canonical event types to RAID, RACI, Decisions, Lessons)
              │
              ▼
   3. Optional Model Extraction (ExtractionProviderProtocol)
      (Invoked ONLY for unstructured text; fail-safe error isolation)
              │
              ▼
   4. Entity Identity & Deduplication
      (Deterministic ID generation f"{prefix}_{sha256(content)[:16]}", provenance merging)
              │
              ▼
   5. Mandatory Provenance Linking
      (source_event_ids, primary_source_event_id, actor, timestamp, source_type, correlation_id)
              │
              ▼
   6. Contradiction & Supersession Engine
      (5 taxonomy categories, non-destructive history preservation)
              │
              ▼
   7. Schema & Invariant Validation
      (Strict Pydantic v2 & JSON Schema draft 2020-12 enforcement)
              │
              ▼
[CompilationResult: Candidates & ContradictionProposals]
```

---

## 3. The 9 Canonical Semantic Entity Types

All semantic entities strictly conform to `artifacts/project-state/phase-1/semantic-entity-schema-v1.json`:

| Semantic Type | ID Prefix & Regex Pattern | Core Fields | Default Initial Status |
| :--- | :--- | :--- | :--- |
| **`FACT`** | `fct_[A-Za-z0-9._-]{2,64}` | `statement`, `category`, `verified_at`, `verification_method` | `verified` (if structured) |
| **`DECISION`** | `dref_[A-Za-z0-9._-]{2,64}` | `decision_id`, `relation`, `status`, `task_id`, `receipt_ref` | `accepted` / `proposed` / `rejected` |
| **`ASSUMPTION`** | `asm_[A-Za-z0-9._-]{2,64}` | `statement`, `rationale`, `confidence`, `status`, `invalidated_by` | `valid` / `invalidated` / `confirmed` |
| **`HYPOTHESIS`** | `hyp_[A-Za-z0-9._-]{2,64}` | `statement`, `rationale`, `validation_criteria`, `confidence`, `status` | `proposed` / `testing` / `validated` |
| **`RISK`** | `rsk_[A-Za-z0-9._-]{2,64}` | `title`, `description`, `probability`, `impact`, `owner`, `status` | `identified` / `mitigated` / `retired` |
| **`ISSUE`** | `iss_[A-Za-z0-9._-]{2,64}` | `title`, `description`, `severity`, `status`, `blocking_task_ids` | `open` / `investigating` / `resolved` |
| **`DEPENDENCY`** | `dep_[A-Za-z0-9._-]{2,64}` | `source_id`, `target_id`, `target_type`, `dependency_kind`, `status` | `pending` / `satisfied` / `broken` |
| **`OBSERVATION`** | `obs_[A-Za-z0-9._-]{2,64}` | `content`, `context`, `observer`, `confidence`, `observed_at` | `verified` (structured) / `proposed` (unstr) |
| **`LESSON`** | `lsn_[A-Za-z0-9._-]{2,64}` | `title`, `summary`, `category`, `applies_to`, `recommendation` | `verified` |

---

## 4. Verification Model & Promotion Hierarchy

The compiler operates with 5 discrete verification statuses:
1. `proposed`: Initial state for all model-extracted candidates and newly proposed associations.
2. `verified`: Certified by deterministic canonical event receipt or human operator assertion.
3. `rejected`: Explicitly disassociated, refuted, or rejected by architectural authority.
4. `superseded`: Replaced by a newer authoritative decision or updated entity; **history preserved**.
5. `invalidated`: Disproven assumption or deprecated fact; **history preserved**.

### Verification Priority for Candidate Merging:
$$\text{verified} > \text{rejected} > \text{invalidated} > \text{superseded} > \text{proposed}$$

**Invariant (G3.2):** If all sources for an entity candidate originate from `model_extraction`, the merged status is **strictly capped at `proposed`**, forbidding auto-promotion.

---

## 5. Contradiction and Supersession Taxonomy (G3.5)

The compiler distinguishes exactly 5 classes of contradiction and supersession:
1. **`conflicting_observation`**: Opposing direct observations regarding the same target subject.
2. **`explicit_correction`**: An event or update explicitly referencing an entity with an `invalidates` or `invalidated_by` link.
3. **`superseding_decision`**: An authoritative decision event that explicitly supersedes an existing decision reference (`supersedes: <id>`).
4. **`stale_fact`**: A verified fact whose temporal validity period (`provenance.valid_to`) has expired relative to current wall-clock time.
5. **`unresolved_contradiction`**: Incompatible factual or assumption claims lacking authoritative resolution or explicit supersession metadata.

**Non-Destructive Invariant:** Prior entities are **NEVER deleted or overwritten**. Both predecessor and successor entities remain in the candidate set, bound together by a `ContradictionProposal`.

---

## 6. Deterministic Identity Generation (G3.4)

Entity IDs are deterministically generated to guarantee idempotent compilation:
$$\text{entity\_id} = \text{prefix} \mathbin{\Vert} \text{"\_"} \mathbin{\Vert} \operatorname{SHA-256}\left(\text{project\_id} \mathbin{\Vert} \text{":"} \mathbin{\Vert} \text{entity\_type} \mathbin{\Vert} \text{":"} \mathbin{\Vert} \operatorname{norm}(\text{content})\right)[0:16]$$

Re-running compilation over the same event stream or duplicate events produces identical IDs, enabling deterministic deduplication and provenance merging without record multiplication.

---

## 7. Prompt Injection & Untrusted Data Isolation (G3.6)

1. **Passive Framing:** All unstructured content is wrapped in `<UNTRUSTED_PROJECT_DATA>` boundaries with explicit instructions that text is passive data.
2. **Pattern Interception:** Injection attempts (`ignore instructions`, `set verification_status='verified'`, `grant root admin`) trigger automated quarantine:
   - Entity confidence forced to `0.0`.
   - Provenance status set to `quarantined`.
   - Verification status restricted to `proposed`.
   - Zero alteration of project policies, file systems, or execution capabilities.
3. **Credential Scrubbing:** GitHub PATs, AWS access keys, Bearer tokens, and private keys are scrubbed before entity generation.
