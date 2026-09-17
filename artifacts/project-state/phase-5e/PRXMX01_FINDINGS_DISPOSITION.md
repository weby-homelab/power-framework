# PRXMX-01 Findings Disposition & Lessons Learned (Phase 5E Admission)

```text
DISPOSITION_SCHEMA: power.disposition.v1
RECORDED_AT_UTC: 2026-09-17T11:08:00Z
GATE: Phase 5E (P38-WP03) Admission
HOST: PRXMX-01 (100.86.120.114)
REPOSITORY: https://github.com/weby-homelab/power-framework
```

---

## 1. Executive Context

During operations on **PRXMX-01**, several operational observations and edge cases regarding the MCP mutation subsystem, timeout handling, index synchronization, and doctor status evaluation were recorded. 

In strict compliance with the Phase 5E boundary, Phase 5E is a read-only shadow benchmark comparing Legacy Retrieval against RetrievalPlanner + ContextPack on frozen evaluation corpus v1.1. Phase 5E **does not permit** rewriting the MCP mutation subsystem, introducing new doctor architectures, modifying mutation receipts, or refactoring long-running async cancellation.

This document classifies all recorded PRXMX-01 findings, documents the bounded workflow fix applied in Phase 5E admission, and preserves the 7 core operational lessons for future cross-cutting work.

---

## 2. Findings Classification Matrix

| Finding ID | Description | Classification | Action in Phase 5E |
| :--- | :--- | :--- | :--- |
| **PRXMX-F01** | Skill documentation drift instructing agents to execute duplicate full-vault `power sync` and `power index` after canonical transactions that already completed internal index/sync. | **DOC/WORKFLOW FIX** (RESOLVED) | Fixed in `skills/power/SKILL.md` and `references/agent-workflow.md`. Explicitly prohibits blind duplicate full-vault sync/index when transaction receipt exists. |
| **PRXMX-F02** | Stale `CURRENT_LIVE_MAIN` and Phase 5E naming drift in `docs/plans/POWER_3.8_CURRENT_STATE.md` following PR #444 merge. | **DOC/WORKFLOW FIX** (RESOLVED) | Fixed in `POWER_3.8_CURRENT_STATE.md` during Phase 5E admission. |
| **PRXMX-F03** | Blind mutation retry following timeout or network glitch, risking duplicate state modifications or race conditions. | **DOC/WORKFLOW FIX** | Preserved as operational mandate: strictly no blind mutation retry after timeout. |
| **PRXMX-F04** | Reliance on manual file inspection rather than verifying cryptographically signed, content-free canonical transaction receipts. | **DOC/WORKFLOW FIX** | Enforced: canonical transaction receipt is stronger evidence than manual filesystem existence. |
| **PRXMX-F05** | LLM reinterpretation of `power doctor` global status when report indicates degraded or failing conditions. | **DOC/WORKFLOW FIX** | Preserved: doctor global status is authoritative machine truth and must not be reinterpreted or rationalized by LLMs. |
| **PRXMX-F06** | Per-operation doctor admission and granular mutation admissibility gates. | **OPEN CROSS-CUTTING DEBT** | Out of scope for Phase 5E. Deferred to dedicated cross-cutting governance/architecture milestones. |
| **PRXMX-F07** | Long-running mutation progress reporting, timeout handling, and latency observability in the MCP layer. | **OPEN CROSS-CUTTING DEBT** | Out of scope for Phase 5E. Deferred to Phase 6+ capture and broker architecture. |
| **PRXMX-F08** | New MCP cancellation protocol and async task lifecycle management. | **OUT OF SCOPE FOR 5E** | Forbidden in Phase 5E. No runtime MCP mutation modifications permitted. |

---

## 3. Preserved PRXMX-01 Operational Lessons

The following seven operational lessons are formally preserved as permanent operational rules:

1. **Version identity must be machine-checked:**
   Never assume or infer runtime version identity from chat narrative, memory, or unverified filenames. Exact package version, Git commit SHA, and tree SHA must be verified against live GitHub before admission or claiming gate completion.

2. **No blind mutation retry after timeout:**
   If a mutation operation experiences a timeout, disconnect, or uncertain delivery, do not blindly retry the mutation. Inspect transaction receipts, ledger state, and idempotency records before determining recovery action.

3. **Canonical transaction receipt is stronger evidence than manual file existence:**
   A file on disk may be corrupted, partial, or unverified. A valid, schema-compliant transaction receipt containing cryptographic hashes, timestamps, and principal bindings is the authoritative evidence of operation success.

4. **Do not duplicate full sync/index after a transaction that already completed them:**
   Canonical transactions (`ingest`, `synthesize`, `memory apply`) perform atomic internal indexing and search synchronization, returning a receipt. Running blind duplicate full-vault `power sync` or `power index` wastes compute, risks lock contention, and introduces false-positive divergence.

5. **Doctor global status must not be reinterpreted by the LLM:**
   The output of `power doctor <path> --json` is an unbendable, fail-closed contract. If doctor reports a non-zero exit or blocking health violation, the agent must not invent workarounds or declare success; it must halt and report the exact doctor finding.

6. **Per-operation doctor admission remains future cross-cutting work:**
   Granular, per-operation health checks and policy evaluation prior to each mutation are recognized as important architectural debt to be addressed across the framework, not patched in an isolated retrieval evaluation phase.

7. **Long mutation progress/latency observability remains future cross-cutting work:**
   Providing fine-grained streaming progress, heartbeat monitoring, and cancellation hooks for heavy mutation tasks remains an open architectural item for Phase 6/7.

---

## 4. Disposition Summary

- **Doc/Workflow Fixes Applied:** Skill documentation updated (`SKILL.md`, `references/agent-workflow.md`); governance documents reconciled.
- **Phase 5E Scope Integrity:** 100% preserved. Zero MCP mutation code modified; zero doctor architecture changes introduced.
