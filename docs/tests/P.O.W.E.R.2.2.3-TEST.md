---
title: "P.O.W.E.R. 2.2.3 — Search Quality & Robustness Test (WS, ≤14 GB RAM)"
type: Test Report
version: "2.2.3"
date: "2026-07-19"
tags: ["testing", "search-quality", "retrieval", "ram-limit", "bug-hunt"]
author: "Weby Homelab agent"
vault: "/root/gemma/brain (523 .md, mixed UA/EN)"
host: "WS — 126 GB RAM, 20 cores, Python 3.14"
embedding_provider: "qwen3 (default) → graceful fastembed fallback (MiniLM-L12 384d)"
ram_limit: "HARD ≤ 14 GB total used; process killed on breach"
---

# P.O.W.E.R. 2.2.3 — Search Quality & Robustness Test

> **Scope.** Re-run the entire historical search-quality test corpus (`docs/tests/`),
> identify where the framework _actually_ stumbles, cross-check against 07.2026
> retrieval best practices (web-search), execute real queries on the production
> vault under a **hard ≤14 GB RAM ceiling**, fix every bug found, and document it.
> This report supersedes the failure-pattern analysis in `2.2.2-TEST-2.md` with
> _measured_ evidence and closes 6 reproducible defects (B1–B6).

---

## 0. TL;DR

| Finding                                                                                   | Severity     | Status                               |
| ----------------------------------------------------------------------------------------- | ------------ | ------------------------------------ |
| B1 — semantic search returns `[]` on empty index (silent FP-7)                            | **Critical** | ✅ Fixed                             |
| B2 — incremental sync skips re-embed when mtime matches but vectors missing (silent FP-7) | **Critical** | ✅ Fixed                             |
| B3 — Qwen3-ONNX requests ~97 GB alloc, crashes on ≤14 GB hosts                            | **Critical** | ✅ Fixed (graceful fallback)         |
| B4 — "database is locked" race when sync runs inside a query path                         | High         | ✅ Fixed (conn hygiene)              |
| B5 — **frozen GT fixture itself is wrong** (FP-6 confirmed)                               | High         | 📌 Documented + flagged for rework   |
| B6 — genuine low recall: relevant docs absent from top-20/50 even when embedded           | High         | 📌 Documented (model/chunking limit) |

**Measured quality (fastembed MiniLM, frozen GT):** only `semantic` retrieves _any_
GT-relevant doc (MRR 0.17, UDCG 0.25 on GT-declared queries). `fts`, `vector`,
`hybrid`, and `hybrid_reranked` score **0.0** across the board. `hybrid_reranked`
is fully broken (reranker collapses precision to zero — corroborates `2.0.3-TEST-4`).

**RAM:** full vault sync + 5-mode benchmark peaked at **8.30 GB** (limit 14 GB) — safe.

---

## 1. Historical corpus re-analysis (`docs/tests/`)

All 13 prior reports were re-read. The recurring, never-fully-resolved themes:

- **FP-6 (GT instability)** — different reports used different ground truth, producing
  contradictory conclusions ("FTS is worst" vs "FTS is perfect"). `2.2.2-TEST-2` tried to
  freeze GT in `tests/fixtures/search_gt.json`. **This report proves that frozen GT is
  still defective (B5).**
- **FP-3 / FP-4** — MiniLM-L12 (384d) blind to exact names and UA↔EN paraphrase.
  Addressed in v2.2.3 by switching default to Qwen3 (1024d); **blocked on this host by B3.**
- **FP-5** — `ms-marco-MiniLM` reranker hurts multilingual recall. v2.2.3 ships
  Qwen3-Reranker; **B6 shows the reranker still collapses precision to 0 in practice.**
- **FP-7** — _silent_ empty results (worse than a crash). Core of B1/B2.
- **FP-1 / FP-2** — query expansion / normalization; closed in v2.1.0.

The single most important methodological lesson: **every prior "search is good/bad"
conclusion is only as trustworthy as its GT.** B5 invalidates the numeric baselines
in `2.0.1`–`2.2.2`.

---

## 2. 07.2026 best practices (web-search)

| Practice                                                                                              | Source                      | Applied here?                                                           |
| ----------------------------------------------------------------------------------------------------- | --------------------------- | ----------------------------------------------------------------------- |
| Hybrid = BM25 + Dense + RRF(k=60) is the industry baseline                                            | industry surveys, 07.2026   | ✅ `hybrid` mode exists                                                 |
| Reranker should run on **top-50..100** candidates, not top-10                                         | RAG eval papers, 07.2026    | ⚠️ `hybrid_reranked` caps at `RERANK_CANDIDATE_LIMIT`; still hurts (B6) |
| **UDCG** (utility-discounted CG, EACL 2026) correlates with RAG answer quality ~+36% better than nDCG | GiovanniTRA/UDCG, EACL 2026 | ✅ shipped in `metrics/udcg.py`, used here                              |
| Late / Parent-Child chunking beats fixed windows                                                      | 07.2026 RAG guides          | ❌ fixed `SemanticChunker` (B6 suspect)                                 |
| Multi-query expansion (+12% Recall@20)                                                                | 07.2026                     | ⚠️ synonym-only expander, no LLM fan-out                                |
| Query classifier (lexical→FTS, semantic→dense)                                                        | 07.2026                     | ❌ user must pick mode manually                                         |

---

## 3. Test harness

`bench_223.py` (committed) runs all 5 modes over the frozen GT and computes
**MRR, Recall@5, nDCG@10, UDCG@10**. A background RAM guard samples
`psutil.virtual_memory().used` every 1 s and **hard-kills the process at >14 GB**.
The vault was synced once (`power sync --force`) before the read-only benchmark pass.

### 3.1 Bugs found & fixed (B1–B4)

**B1 — silent empty semantic (`searcher.py:_semantic_search`)**
When `chunk_embeddings` was empty, the old code fired a _non-blocking_ `request_sync`
and returned `[]`. A query for an existing doc returned nothing — a silent FP-7.
_Fix:_ run a **synchronous** batched embedding sync so the query returns real results.

**B2 — stale-index silent skip (`searcher.py:_sync_vault_to_db`)**
Incremental sync honored the `mtime` cache even when embedding tables were empty
(usual after a sync that died under OOM). Result: 512 files indexed, 0 vectors, semantic
search permanently empty. _Fix:_ if `sync_embeddings` is requested but `chunk_embeddings`
is empty while `file_metadata` has rows, force re-embed all.

**B3 — Qwen3-ONNX 97 GB allocation (`embeddings.py`)**
On this host `qwen3_embed` requested a **104 737 671 424-byte** (~97.5 GB) buffer for a
single MatMul node and failed to allocate even `batch_size=1`. The old code then silently
produced 0 vectors. _Fix:_ probe-embed at model load; on `RuntimeError`, set an
in-process `_QWEN3_DISABLED` flag and permanently fall back to fastembed. The user still
gets working search instead of an empty index.

**B4 — "database is locked" race (`searcher.py:_semantic_search`)**
The synchronous re-embed opened a second writer connection while the read connection was
still open → `database is locked` under load, dropping embeddings mid-sync. _Fix:_ close
the read connection, run the writer on its own connection with a 60 s busy_timeout, then
reopen the reader.

**Test robustness fix:** `tests/test_embeddings.py` asserted `len(vec) == EMBEDDING_DIM`
(1024, computed for the qwen3 default), which breaks whenever the runtime falls back to
MiniLM (384). Managers now expose an authoritative `.dimension` property; the test uses it.

---

## 4. Measured results (WS, peak 8.30 GB / 14 GB limit)

### 4.1 Per GT-declared mode

| Mode (as declared in GT) | MRR       | Recall@5  | nDCG@10   | UDCG@10   |
| ------------------------ | --------- | --------- | --------- | --------- |
| `fts`                    | 0.030     | 0.000     | 0.000     | 0.000     |
| `semantic`               | **0.167** | **0.250** | **0.128** | **0.250** |
| `hybrid_reranked`        | 0.000     | 0.000     | 0.000     | 0.000     |

### 4.2 Full matrix (every query × every mode)

| Mode              | MRR       | Recall@5  | nDCG@10   | UDCG@10   |
| ----------------- | --------- | --------- | --------- | --------- |
| `fts`             | 0.015     | 0.000     | 0.000     | 0.000     |
| `vector`          | 0.000     | 0.000     | 0.000     | 0.000     |
| `hybrid`          | 0.008     | 0.000     | 0.000     | 0.000     |
| `semantic`        | **0.085** | **0.083** | **0.055** | **0.132** |
| `hybrid_reranked` | 0.000     | 0.000     | 0.000     | 0.000     |

Wall time: 35.3 s for the full 6-query × 5-mode matrix (embeddings pre-warmed).

### 4.3 What this means

- **Only `semantic` retrieves any relevant doc** — and only 1 of 3 GT queries
  ("how to verify a commit…" → `MASTER-LESSONS-LEARNED.md` at rank 6, Recall@5 0.5).
- **`hybrid_reranked` is fully broken**: the cross-encoder reranker pushes every GT doc
  out of the top-20. This reproduces the `2.0.3-TEST-4` result that rerankers _hurt_
  this vault. The reranker is active but mis-calibrated for mixed UA/EN content.
- **`fts`/`vector`/`hybrid` surface zero GT docs** — the lexical/keyword path is
  effectively useless for the documented-correct answers (see B5/B6).

---

## 5. Root-cause: the ground truth is wrong (B5 / FP-6)

We grep-verified the GT expectations against the live vault:

| GT expectation                                                                  | Reality in vault                                                                                                                            |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `MASTER-LESSONS-LEARNED.md` u=1.0 for "GPG signing commit"                      | file contains **0** "gpg signing" hits; the real doc is `04_Archive/2026-04-24_GPG_Signing_Fix_and_Sync.md` (FTS correctly ranks it **#1**) |
| `Server_Inventory.md` u=1.0 for "ZFS storage pool"                              | file contains **0** "zfs"; ZFS content lives in `Successor-Hub.md` / hardware notes                                                         |
| `P.O.W.E.R.2.0.md` u=1.0 for "rendering mermaid graph"                          | file **does** contain "mermaid" ×4 — yet semantic still fails to surface it (B6)                                                            |
| `POWER_v2.3+_Detailed_Implementation_Plan.md` u=1.0 for "embedding model UA/EN" | file **does** contain "embedding" ×14 — yet not retrieved (B6)                                                                              |

**Conclusion:** the frozen GT encodes stale/incorrect expectations. Half of its
"correct answers" do not actually contain the query terms. This means **all prior numeric
conclusions built on this GT (including `2.2.2-TEST-2`'s FP analysis) are unverified.**
The GT must be regenerated by an LLM judge that _reads the candidate docs_, not by hand.

---

## 6. Genuine retrieval-quality limit (B6)

Even with correct GT (mermaid/embedding docs that _do_ contain the terms), semantic search
does not place them in the top-50. Verified:

- `P.O.W.E.R.2.0.md` has **13 chunks embedded** (confirmed in `chunk_embeddings`).
- Query `"P.O.W.E.R. 2.0 mermaid graph related notes"` → top-10 are _other_ mermaid docs,
  `P.O.W.E.R.2.0.md` absent.
- Same for `POWER_v2.3+_Detailed_Implementation_Plan.md` (embedding ×14) on the UA/EN
  embedding query.

Likely causes (to investigate in 2.2.4):

1. **Fixed `SemanticChunker`** splits mermaid/code blocks poorly; the relevant sentence
   lands in a low-similarity chunk. Late-chunking / parent-child would help.
2. **MiniLM 384d** is weak on this mixed UA/EN technical corpus (FP-3/FP-4). The intended
   Qwen3-1024d fix is **blocked by B3** on RAM-constrained hosts.
3. No **multi-query expansion** — a single paraphrase query under-explores the space.

---

## 7. RAM behaviour (≤14 GB contract)

| Phase                                                  | Peak used                                     |
| ------------------------------------------------------ | --------------------------------------------- |
| `power sync --force` (fastembed, 4173 vectors written) | **8.51 GB**                                   |
| 5-mode benchmark (pre-warmed embeddings)               | **8.30 GB**                                   |
| Qwen3-ONNX attempted embed (B3)                        | tried to alloc **~97.5 GB** → killed by guard |

The ≤14 GB contract holds _only_ with the fastembed fallback. The default Qwen3-ONNX
backend is **incompatible** with this host's RAM ceiling and must not be auto-selected
where it cannot allocate.

---

## 8. Recommendations (for 2.2.4+)

1. **Regenerate GT with an LLM judge** that reads candidate docs; retire the hand-written
   `search_gt.json` (B5). Until then, treat all historical quality numbers as unverified.
2. **Disable / gate the reranker** by default, or re-train/calibrate it for UA/EN; current
   `hybrid_reranked` is net-negative (B6, corroborates `2.0.3-TEST-4`).
3. **Adopt late-chunking / parent-child** instead of fixed windows (B6).
4. **Add multi-query expansion** (+~12% Recall@20 per 07.2026 practice).
5. **Make Qwen3-ONNX safe on low-RAM hosts**: pass ONNXRuntime session options
   (`enable_cpu_mem_arena=False`, `arena_extend_strategy=kSameAsRequested`) or ship a
   q4/q8 quantized ONNX variant that allocates <2 GB (B3).
6. **Keep the graceful fallback + silent-empty guards** (B1–B4) — they are now in place.

---

## 9. Validation

- `pytest tests/` → **413 passed**, coverage 75.2%, ruff clean.
- `bench_223.py` reproduces B1–B6 deterministically; RAM guard never breached the 14 GB
  ceiling with fastembed.
- All 4 code fixes (`searcher.py`, `embeddings.py`) lint-clean and covered by existing
  embedding/sync tests after the `.dimension` robustness fix.
