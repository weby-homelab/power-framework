# P.O.W.E.R. Framework v2.0 Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade P.O.W.E.R. Framework to an AI-native RAG and GraphRAG knowledge system using dense embeddings, cross-encoder rerankers, typed relations, query expansion, contextual chunking, and semantic ROT detection.

**Architecture:** We will introduce a lightweight vector backend using `fastembed` (ONNX Runtime, no PyTorch) for text embeddings and reranking. The search pipeline will combine BM25 FTS5 and dense semantic search, followed by a Cross-Encoder reranker. The metadata schema will be upgraded to support typed relations.

**Tech Stack:** Python 3.10+, fastembed (ONNX, CPU-optimized), Pydantic v2, SQLite FTS5, pytest.

---

## Tasks

### Task 1: Update Security Policy Supported Versions
**Files:**
- Modify: `SECURITY.md:5-9`

**Step 1: Write a description of target modifications**
Modify `SECURITY.md` to reflect `1.8.x` as the currently supported version.

**Step 2: Run verification**
View the file contents.

**Step 3: Modify the file**
Replace `1.4.x` with `1.8.x` in `SECURITY.md`.

**Step 4: Verify**
Confirm that the table in `SECURITY.md` shows `1.8.x` as supported.

**Step 5: Commit**
```bash
git add SECURITY.md
git commit -m "docs: update security policy supported versions to 1.8.x"
```

---

### Task 2: Dense Semantic Embeddings using FastEmbed
**Files:**
- Modify: `pyproject.toml`
- Create: `src/power_framework/core/embeddings.py`
- Modify: `src/power_framework/core/searcher.py`
- Create: `tests/test_embeddings.py`

**Step 1: Write tests for the embedding manager**
Write tests in `tests/test_embeddings.py` validating that the embedding manager can initialize and generate dense float embeddings of the expected size (e.g. 384 for MiniLM).

**Step 2: Verify tests fail**
Run the tests. Expected: Fail (cannot import `EmbeddingManager`).

**Step 3: Implement EmbeddingManager and update pyproject.toml**
Add `fastembed` to `pyproject.toml` and implement `EmbeddingManager` in `src/power_framework/core/embeddings.py`. Integrate semantic search mode in `src/power_framework/core/searcher.py` using SQLite or local numpy arrays for cosine similarity comparisons.

**Step 4: Run tests to verify they pass**
Run `pytest tests/test_embeddings.py -v`. Expected: PASS.

**Step 5: Commit**
```bash
git add pyproject.toml src/power_framework/core/embeddings.py src/power_framework/core/searcher.py tests/test_embeddings.py
git commit -m "feat: integrate fastembed for dense semantic embeddings"
```

---

### Task 3: Cross-Encoder Reranker
**Files:**
- Create: `src/power_framework/core/reranker.py`
- Modify: `src/power_framework/core/searcher.py`
- Create: `tests/test_reranker.py`

**Step 1: Write tests for reranker**
Write tests verifying that `RerankerManager` ranks documents given a query and a set of candidate document snippets, placing the most relevant document first.

**Step 2: Verify tests fail**
Run the tests. Expected: Fail (module `reranker` not found).

**Step 3: Implement Cross-Encoder Reranker**
Implement `RerankerManager` using `fastembed`'s TextRerankers. Update the hybrid search mode in `searcher.py` to fetch a wider set of candidates (e.g. 50) and rerank them to the requested `max_results`.

**Step 4: Verify tests pass**
Run `pytest tests/test_reranker.py -v`. Expected: PASS.

**Step 5: Commit**
```bash
git add src/power_framework/core/reranker.py src/power_framework/core/searcher.py tests/test_reranker.py
git commit -m "feat: implement cross-encoder reranker for search refinement"
```

---

### Task 4: Query Expansion & Rewriting
**Files:**
- Create: `src/power_framework/core/query_expansion.py`
- Modify: `src/power_framework/core/searcher.py`
- Create: `tests/test_query_expansion.py`

**Step 1: Write tests for query expansion**
Test that `expand_query` generates synonyms or alternate query phrasings to improve retrieval coverage.

**Step 2: Verify tests fail**
Run the tests. Expected: Fail.

**Step 3: Implement Query Expansion**
Implement a rule-based query expander using synonym mapping, and an optional API-driven query expander (using the `OPENROUTER_API_KEY` from the environment if available) as a fallback/advanced mode.

**Step 4: Verify tests pass**
Run `pytest tests/test_query_expansion.py -v`. Expected: PASS.

**Step 5: Commit**
```bash
git add src/power_framework/core/query_expansion.py src/power_framework/core/searcher.py tests/test_query_expansion.py
git commit -m "feat: add query expansion and rewriting layer"
```

---

### Task 5: Typed Knowledge Graph & Traversal
**Files:**
- Modify: `src/power_framework/core/models.py`
- Modify: `src/power_framework/core/relations.py`
- Create: `tests/test_typed_relations.py`

**Step 1: Write tests for typed relations**
Verify that Pydantic parsing accepts `related` fields with typed metadata schemas (e.g. `{path: "...", relation: "extends", confidence: 0.9}`) and generates proper validation errors on invalid types.

**Step 2: Verify tests fail**
Run the tests. Expected: Fail.

**Step 3: Update model schemas and implement relations traversal**
Update `OKFMetadata` to accept both simple strings (for backward compatibility) and structured `TypedRelation` objects. Implement relation traversal and a Mermaid diagram generator in `relations.py`.

**Step 4: Verify tests pass**
Run `pytest tests/test_typed_relations.py -v`. Expected: PASS.

**Step 5: Commit**
```bash
git add src/power_framework/core/models.py src/power_framework/core/relations.py tests/test_typed_relations.py
git commit -m "feat: implement typed knowledge graph and traversal"
```

---

### Task 6: Contextual Retrieval & Chunking
**Files:**
- Create: `src/power_framework/core/chunker.py`
- Modify: `src/power_framework/core/searcher.py`
- Create: `tests/test_chunker.py`

**Step 1: Write tests for Contextual Retrieval chunker**
Write tests validating that long notes are split into semantic chunks, and each chunk is prefixed with document-level summaries (Contextual Retrieval) before indexing.

**Step 2: Verify tests fail**
Run the tests. Expected: Fail.

**Step 3: Implement semantic chunker with context injection**
Implement structured chunking in `chunker.py`. Add logic to generate a short context description (either using metadata or short summaries) and prepend it to the chunk content when feeding to the embeddings.

**Step 4: Verify tests pass**
Run `pytest tests/test_chunker.py -v`. Expected: PASS.

**Step 5: Commit**
```bash
git add src/power_framework/core/chunker.py src/power_framework/core/searcher.py tests/test_chunker.py
git commit -m "feat: implement contextual retrieval and semantic chunking"
```

---

### Task 7: Semantic ROT & Contradiction Detection
**Files:**
- Modify: `src/power_framework/core/rot_scoring.py`
- Create: `tests/test_semantic_rot.py`

**Step 1: Write tests for semantic ROT checks**
Test that `ContentDedupDetector` successfully identifies notes that are semantically identical (high cosine similarity using dense embeddings) even when they use different wording, and test that contradiction checks identify conflicting facts between high-overlap notes.

**Step 2: Verify tests fail**
Run the tests. Expected: Fail.

**Step 3: Integrate dense embeddings into ROT audit**
Update `ContentDedupDetector` in `rot_scoring.py` to use dense embedding cosine similarity. Implement a basic contradiction detector that Flags notes with high semantic overlap but contradictory metadata or facts.

**Step 4: Verify tests pass**
Run `pytest tests/test_semantic_rot.py -v`. Expected: PASS.

**Step 5: Commit**
```bash
git add src/power_framework/core/rot_scoring.py tests/test_semantic_rot.py
git commit -m "feat: upgrade ROT audit to use semantic dedup and contradiction check"
```
