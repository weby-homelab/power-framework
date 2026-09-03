# MISSION: Phase 0 Forensic Analysis & Architecture Mapping for POWER 3.7.11

You are the Forensic Codebase Specialist subagent for the Lead Orchestrator on WS.
Your task is to conduct an exhaustive forensic audit of the POWER 3.7.11 codebase in `/root/gemma/projects/.power-framework-3.7.11-worktree` and produce three authoritative markdown reports in `/root/gemma/projects/.power-framework-3.7.11-worktree/artifacts/project-state/phase-0/`:

1. `architecture_map.md`
2. `gap_matrix.md`
3. `overlap_decisions.md`

STRICT CONSTRAINTS:
- DO NOT WRITE ANY PRODUCTION CODE FOR PROJECT STATE ENGINE (PSE). No files in `src/power_framework/project_state/` or elsewhere. Phase 0 is forensic analysis only.
- ZERO HALLUCINATIONS: Every statement, class, function, parameter, and file path must be verified against actual code in `src/power_framework/`. Cite exact file paths, class names, method signatures, and line numbers.
- NO PSEUDOCODE OR PLACEHOLDERS (`...`).
- Ukrainian language for analytical narrative, technical terms in English where appropriate.

## REPORT 1: `architecture_map.md`
Document the exact architecture of POWER 3.7.11 across the following 18 integration dimensions:
1. **ApplicationService & Application Envelope**: `src/power_framework/core/application.py`, `ApplicationService`, request/response envelope, error handling, session context.
2. **Vault Mutation Boundary & Storage**: `src/power_framework/core/mutation.py`, `vault_storage.py`, `write_queue.py`, atomic writes, write locks, rollback mechanisms.
3. **Task v2 Subsystem**: `src/power_framework/core/task_models.py`, `task_store.py`, `task_service.py`, task lifecycle states, transition validation, task events, durability.
4. **Decision Workflow**: `src/power_framework/core/decision_service.py`, typed decision schemas, approval workflows, ADR representations.
5. **Handoff Workflow**: `src/power_framework/core/handoff.py`, handoff creation, transition, actor assignment, continuity.
6. **Memory Subsystem**: `src/power_framework/core/memory_api.py`, transactional memory, proposal, approval/apply, receipts, history replay, validation.
7. **Session Synthesis & Ingestion**: `src/power_framework/core/synthesize.py`, `importer.py`, session parsing, OKF frontmatter generation.
8. **Indexing, Search & Graph RAG**: `src/power_framework/core/searcher.py`, `indexer.py`, `relations.py`, SQLite FTS, vector embeddings (`experimental/embeddings.py`), cross-encoder reranker (`experimental/reranker.py`), Graph extraction (`experimental/graph_extraction.py`).
9. **CLI Registration & Conventions**: `src/power_framework/core/cli.py`, subparser architecture, flag conventions, exit codes, CPU throttling hooks.
10. **MCP Server & Tool Registry**: `src/power_framework/mcp/power_server.py`, `entrypoint.py`, FastMCP tool registration, schemas, risk annotations, idempotency.
11. **Web API & GUI**: `src/power_framework/web/app.py`, `routes/`, client adapter `web/clients/power.py`, authentication, CSRF, rate limiting.
12. **Configuration & Environment**: `src/power_framework/core/capabilities.py`, env var discovery, model configuration, vault resolution.
13. **Logging & Observability**: `src/power_framework/core/utils.py`, `loguru` / standard logging setup, receipt logging, telemetry.
14. **Rate Limits & Concurrency**: Lock mechanisms, concurrency limits, web rate limiter (`web/auth/rate_limiter.py`).
15. **Resource Throttling & Hardware Guards**: `src/power_framework/core/cpu_throttling.py`, thread caps, memory limits, MPS 50% GPU guard compliance.
16. **Support Matrix & Platform Compatibility**: `pyproject.toml`, supported Python versions (3.13, 3.14), platform checks.
17. **State Migration & Schema Evolution**: `src/power_framework/core/state_migration.py`, vault schema migrations, version tracking.
18. **Release Evidence & Attestation**: `scripts/verify_*.py`, `release/evidence/`, attestation receipts, public surface verification.

For each dimension, specify:
- Exact file paths and line number ranges.
- Primary classes, interfaces, and function signatures.
- Architectural contracts and invariants.
- Exact extension points available for Project State Engine (PSE).

## REPORT 2: `gap_matrix.md`
Construct an exhaustive evaluation matrix analyzing the 14 mandatory PSE capabilities against POWER 3.7.11:
1. Append-only Event Ledger (hash-chained, durable, auditable).
2. Session & Actor Provenance (multi-agent, human, session ID, tool call attribution).
3. Temporal Validity & Supersession (bitemporal/supersedes/invalidates graph).
4. Semantic Entity Typing (FACT, DECISION, ASSUMPTION, HYPOTHESIS, RISK, ISSUE, DEPENDENCY, OBSERVATION, LESSON).
5. Project Lifecycle Engine (DISCOVERY -> PLANNING -> EXECUTION -> MONITORING -> CLOSING -> CLOSED with deterministic gates).
6. RAID Log Management (Risks, Assumptions, Issues, Dependencies tracking).
7. RACI & Actor Governance (Responsible, Accountable, Consulted, Informed mapping).
8. DoR / DoD Governance Gates (Definition of Ready / Done contract enforcement).
9. Deterministic State Replay (rebuilding current project state from canonical event log).
10. Contradiction & Supersession Detection (identifying conflicting claims/decisions).
11. Context Compilation (role/task-based context packs: architecture, bugfix, planning, etc.).
12. Automatic Agent Capture (Level A explicit API, Level B hook/session capture, Level C import).
13. Privacy, Redaction & Threat Boundaries (metadata-only, structured, full-content modes, secret scrubbing).
14. Materialized Project Views (`meta.json`, `ADR-*.md`, `raid_log.json`, `dependencies.json`, `lessons-*.md`).

For each capability, fill the matrix columns:
- Capability
- Status (`Exists`, `Partial`, `Missing`)
- Existing POWER Foundation (cite exact code/class)
- Proposed Reuse Path / Extension Mechanism (without creating parallel core)
- Risk & Architectural Considerations

## REPORT 3: `overlap_decisions.md`
Provide clear, binding architectural integration decisions to prevent duplication across the 6 major overlapping areas:
1. **Task v2 (`task_models.py`, `task_store.py`) vs PSE Project Tasks**: Reuse, adapter, extension, or duplicate? (Strictly mandate reuse/extension; forbid parallel task store).
2. **Decision Workflow (`decision_service.py`) vs PSE Decisions & ADRs**: Reuse, adapter, extension, or duplicate?
3. **Transactional Memory (`memory_api.py`) vs PSE Event Ledger & State**: Distinguish vault-level note memory from project-level state engine.
4. **Handoff Workflow (`handoff.py`) vs PSE Context Packs & Agent Handoff**: Reuse/extend handoff with ContextPack integration.
5. **Existing Receipt/Audit Logs vs PSE Append-Only Ledger**: Integration and boundaries.
6. **Search & Graph Index (`searcher.py`, `relations.py`) vs PSE Derived Search**: Ensure PSE derived indexes feed into existing SQLite / FTS / Graph acceleration without becoming canonical.

For every area, define:
- Target classification: `REUSE`, `ADAPTER`, `EXTENSION`, `DEPRECATION`, or `PROHIBITED DUPLICATE`.
- Technical justification with code references.
- Exact boundary contract between POWER core and PSE.

Produce all three files completely, with high rigor, deep code citations, and zero placeholders.
