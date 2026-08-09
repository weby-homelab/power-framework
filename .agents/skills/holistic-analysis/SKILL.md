---
name: holistic-analysis
version: 3.4.0
description: "Perform holistic codebase analysis, step-by-step verified execution, and global quality audit for P.O.W.E.R. vaults. Trigger when analyzing, refactoring, or auditing a project before making changes."
---

# Holistic Analysis & Step-by-Step Verification Protocol

This skill requires agents to follow a strict analysis–execution–validation cycle when working on any project, especially P.O.W.E.R. vaults and knowledge-base infrastructure.

## Stage 1: Sequential Analysis First

- **Forbidden** to write code or propose solutions without full context study.
- Find and read all related project files using `grep_search` or `view_file` — read sequentially, not in large batches.
- Document all findings in order: architectural bugs, outdated patterns, redundant disk/network I/O, and unsafe regex expressions.
- Check POWER 3.2.1 specifics: verify `description` schema has no `max_length` cap, confirm `BGEM3Reranker` is the default (MIT), ensure `RuntimeError` is raised for unknown embed providers, validate that `relations` table exists with triplets persisted via `synthesize_session`, and confirm the single-writer write queue is active.

## Stage 2: Step-by-Step Act

- Break work into minimal isolated steps.
- Implement only one change per step (e.g., one `replace_file_content` per file per step).
- For POWER 3.2.1 remediation work, follow the phase order from the plan: A (OKF friction removal) → C (fail-closed embedder) → B (MIT reranker default) → F (write queue) → E (auto-graph) → D (semantic GT/UDCG) → G (evidence).

## Stage 3: Immediate Feedback & Testing (Validate)

- After every smallest change, run syntax checks (`python -m py_compile` or equivalent linters/tests).
- Do not proceed to the next step until the current step validates with zero errors.
- For P.O.W.E.R. specifically, run the full gate suite after each functional phase:
  ```bash
  ruff check src tests
  mypy src/power_framework
  pytest tests/ -v
  power lint brain
  ```

## Stage 4: Global Audit (Final Quality Check)

Verify against this checklist:

- Are all API-level inputs typed and validated (Pydantic v2 / stdlib)?
- Is I/O optimized (no redundant disk operations on hot paths)?
- Are background threads constrained (`ThreadPoolExecutor` instead of raw threads)?
- Is the image/codebase clean (no systemd artifacts, no empty directories)?
- Does the vault pass `power lint` with exit code 0?
- Are all 19 MCP tools functional via the FastMCP 3.x server?
- Is the `models.lock.json` SHA-pinned for both `canonical_embedding` and `canonical_reranker`?
- Does the semantic GT (`--gt-mode semantic`) show `ndcg@5(reranked) > ndcg@5(fts)`?

## P.O.W.E.R. 3.2.1 Changelog Additions (2026-07-24)

| Change | Impact |
| :--- | :--- |
| Structured dictionary targets & section anchors in graph builder | Precise, deterministic graph edge creation across vaults |
| Refined Low-RAM deployment guidance | Validated memory footprints for constrained hosts (8–12 GB VPS/LXC) |
| Decoupled license badge & ruff format compliance | All source files pass `ruff format`; badge is decoupled from content flow |
| P.O.W.E.R. 3.2.0 test evidence report | Comprehensive gate documentation added to `docs/tests/` |

## Historical Release Status (v3.2.1 — Stable)

All 6 WTF remediation items from the 3.1→3.2.0 plan are complete:

| Issue | Status |
| :--- | :--- |
| #1 Fake UDCG | Partial — curated GT implemented; EACL-2026 validation pending |
| #2 CC-BY-NC reranker default | Fixed — `BGEM3Reranker` (MIT) is now the default |
| #3 Silent fallback on TF | Fixed — unknown providers raise `RuntimeError`; fallback requires explicit gate |
| #4 OKF description cap | Fixed — `max_length` removed; truncation only in catalog render |
| #5 Half-manual Graph RAG | Fixed — auto-triplet extraction + semantic suggestions via dense embeddings |
| #6 SQLite locks | Fixed — single-writer `asyncio.Queue` worker serializes writes |

Memory contract (≤12 GB) is pending final RSS measurement on target hardware.
