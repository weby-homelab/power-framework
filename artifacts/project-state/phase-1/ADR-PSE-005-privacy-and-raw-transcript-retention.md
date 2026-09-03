# ADR-PSE-005: Privacy Boundary, Credential Sanitization, and Raw Transcript Retention

- **Status:** ACCEPTED
- **Date:** 2026-09-03
- **Deciders:** POWER Architecture Guild, Weby Homelab
- **Context:** The POWER framework operates with autonomous LLM agents that process conversations, tool invocations, and workspace code. PSE event streams are persistent and may be synchronized or shared across fleet nodes.

## Context and Problem Statement
LLM interactions generate large quantities of verbose conversation transcripts, tool outputs, terminal logs, and potentially sensitive tokens (API keys, passwords, bearer tokens, private keys). Storing raw chat transcripts or unsanitized tool outputs directly inside the canonical event ledger (`events.jsonl`) introduces severe security risks, potential secret leakage, and unmanageable event log bloat.

## Decision Drivers
- Zero-Credential Leakage Mandate: Secrets must never be persisted in public or durable project ledgers.
- Compliance with Gate G1.6 (Explicit Privacy Contract).
- Lean, auditable, high-density event streams suitable for long-term archiving.
- Clear boundary between high-level project domain state and low-level agent operational logs.

## Decision Outcome
Chosen Solution: **Three-Tier Privacy Profiles with Strict Payload Perimeter and Defense-in-Depth Sanitization**.

### Privacy & Retention Profiles:
PSE establishes three explicit operational privacy modes:
1. **`metadata-only`**:
   - Captures strictly session boundaries, tool invocation manifests, and operational metadata.
   - Zero content or reasoning tokens are analyzed or retained.
2. **`structured-events` (DEFAULT)**:
   - Evaluates agent dialogue and tool outputs in-memory into concise, structured PSE domain events (`ProjectEvent`, RAID items, RACI assignments, gate evaluations).
   - Once structured events are appended to the ledger, the in-memory dialogue buffer is immediately and permanently discarded.
   - Raw multi-turn prompts, completions, and thinking blocks are strictly prohibited in `ProjectEvent.payload`.
3. **`full-content` (Explicit Opt-In Only)**:
   - Available strictly via explicit opt-in configuration for deep offline debugging and auditing.
   - Stores sanitized conversation turns in an isolated, local-only raw-evidence store (e.g. `.power/raw-evidence/` or `.system_generated/logs/`).
   - **Absolute Boundaries:**
     - NEVER stored inside `ProjectEvent.payload`.
     - NEVER committed to Git repositories.
     - NEVER synchronized across fleet nodes by default.
     - Enforces strict POSIX local permissions (mode `0600` / `0700`) and a strict time-to-live retention window (e.g. 14 days) with automatic pruning.

### Defense-in-Depth Secret Sanitization:
- **Pragmatic Defense-in-Depth:**
  Credential and secret scrubbing is treated as an automated defense-in-depth hygiene layer rather than an absolute panacea. We acknowledge that no heuristic regex filter can claim "zero leak" or "100% compliance" against novel secret encodings.
- **Scrubbing Pipeline:**
  Before any event is serialized to the canonical ledger, all payload fields pass through multi-pattern scrubbing filters targeting API tokens, bearer keys, private certificates, and `.env` patterns, redacting detected secrets with `[REDACTED]`.
- **Content-Free Evidence Hashes:**
  Where verification of an external artifact or test output is needed, PSE records the cryptographic SHA-256 digest in `evidence_refs` rather than embedding large or sensitive raw blobs into the event stream.

## Consequences
### Positive
- Clear privacy boundaries with a sensible `structured-events` default for autonomous agents.
- Lean, deterministic event ledgers safe for long-term storage and fleet replication.
- Defense-in-depth sanitization minimizes credential leakage surface area.

### Negative
- Post-mortem investigation in default mode depends on structured event summaries unless `full-content` local evidence retention is explicitly enabled.
