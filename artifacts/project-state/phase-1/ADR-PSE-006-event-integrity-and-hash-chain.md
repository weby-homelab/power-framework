# ADR-PSE-006: Cryptographic Event Integrity and Hash-Chain Specification

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** Project state transitions represent high-value operational and governance milestones. We must prevent tampering, accidental line reordering, or silent omission of historical events.

## Context and Problem Statement
In Task Manager v2, `TaskEvent` implements an append-only event log with a `payload_digest` and `prev_event_digest`. However, an audit of `core/task_models.py` reveals that `TaskEvent` only chains the payload digests; it does not cryptographically bind the envelope metadata (such as sequence number, timestamp, actor identity, or event type) into the hash chain. For PSE, we must decide whether to replicate this pattern or implement a comprehensive envelope-binding cryptographic chain.

## Decision Drivers
- High assurance tamper-evidence across distributed nodes and multi-agent operations.
- Resistance to subtle attacks: prevent tampering with actor provenance, timestamp retro-dating, or sequence insertion/deletion.
- Deterministic and fast linear verification ($O(N)$) during ledger replay and audit checks.
- Alignment with Requirement #5 (Conscious architectural choice, not blindly copied from TaskEvent).

## Decision Outcome
Chosen Solution: **Two-Tier Envelope-Binding Cryptographic SHA-256 Hash Chain**.

### Specification:
1. **Tier 1 — Payload Digest (`payload_digest`):**
   ```python
   payload_digest = SHA256(POWER_CANONICAL_JSON_V1(payload))
   ```
2. **Tier 2 — Envelope Hash (`event_hash`):**
   The `event_hash` cryptographically seals the entire envelope and metadata, ensuring no field (including `artifact_refs`, `evidence_refs`, `correlation_id`, `causation_id`, `idempotency_key`, `session_id`) can be altered or omitted without invalidating the chain:
   ```python
   payload_digest = SHA256(POWER_CANONICAL_JSON_V1(payload))
   integrity_record = {k: v for k, v in event.items() if k != "event_hash"}
   event_hash = SHA256(POWER_CANONICAL_JSON_V1(integrity_record))
   ```
   *Note:* The hash seals all fields of the envelope (`integrity_record`). `payload_digest` is additionally verified separately to guarantee inner payload integrity independently of the envelope-binding.
3. **Chain Genesis and Linkage Rules:**
   - **Genesis Event (`sequence == 1`):** `prev_event_hash` must be the empty string `""`.
   - **Subsequent Events (`sequence > 1`):** `prev_event_hash` must strictly equal the `event_hash` of the immediately preceding event (`sequence - 1`).
   - **Monotonic Sequence:** Every event must have `sequence == previous_event.sequence + 1`.

### Comparison with TaskEvent:
| Feature | `TaskEvent` (Core v2) | `ProjectEvent` (PSE v1) |
| :--- | :--- | :--- |
| Payload Digest | Yes (`sha256(payload)`) | Yes (`sha256(payload)`) |
| Envelope Binding | No (only payload is digested) | **Yes** (Actor, Timestamp, Sequence, Event Type sealed) |
| Tamper-Resistant Metadata | Vulnerable to metadata edit | **Full cryptographic tamper resistance** |
| Sequence Verification | Validated in memory | **Sealed directly into the hash chain** |

## Consequences
### Positive
- Total cryptographic auditability: any alteration of past events, sequences, timestamps, or authors immediately breaks the chain at that exact point.
- Zero reliance on external or trusting timestamps: the topological order is cryptographically locked.
- Clean and fast chain validation algorithm that can run on startup in milliseconds.

### Negative
- Minor CPU overhead for double SHA-256 calculation (negligible for event append frequency).
- Event append requires obtaining the tail event's `event_hash` under the project lock before computing the new event.
