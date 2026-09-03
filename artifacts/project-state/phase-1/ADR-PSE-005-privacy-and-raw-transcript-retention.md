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
Chosen Solution: **Strict Payload Privacy Perimeter with Content-Free Digest Evidence**.

### Privacy & Retention Rules:
1. **No Raw LLM Transcripts in Event Payloads:**
   - Raw multi-megabyte LLM conversation turns, prompt completions, and system messages are strictly prohibited in `ProjectEvent.payload`.
   - Only concise, structured summaries, validated semantic extractions (e.g. newly discovered risks, updated deliverables), and phase recommendations may be emitted as events.
2. **Mandatory Credential & Secret Scrubbing:**
   - Before any event is serialized to the canonical ledger, all payload fields pass through an automated credential scrubbing filter that redacts API keys, tokens, SSH keys, and `.env` variable values matching known secret patterns.
3. **Content-Free Evidence Hashes:**
   - Where proof of an external activity is required (e.g. test runs, security scans, agent receipts), PSE records the cryptographic SHA-256 digest of the artifact in `evidence_refs` or `artifact_digests`, rather than embedding the raw log data into the event stream.
4. **Separation of Raw Logs:**
   - Raw execution transcripts are kept in ephemeral, local-only directories (e.g. `.system_generated/logs/` or `/tmp/power/`) subject to local retention and rotation policies (e.g. 14 days), completely detached from the project's immutable event ledger.

## Consequences
### Positive
- Event ledgers remain lightweight, deterministic, and safe for fleet-wide replication and long-term storage.
- Accidental exposure of API tokens or personal credentials in project history is systematically prevented.
- Complete regulatory and privacy compliance across multi-user or agentic environments.

### Negative
- Post-mortem debugging of subtle agent reasoning failures requires correlating the event ledger with separate ephemeral transcript logs.
