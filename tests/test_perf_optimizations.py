"""Tests for Performance Plan §1-§6 optimizations in searcher / index_worker."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from power_framework.core import index_worker
from power_framework.core.searcher import (
    RERANK_CANDIDATE_LIMIT,
    _hybrid_reranked_search,
    _init_db,
    _semantic_search,
    format_search_results,
    search_vault,
)
from power_framework.core.utils import get_cache_dir


@pytest.fixture
def indexed_vault(sample_vault: Path, monkeypatch):
    """Build an FTS index (no embeddings) for the sample vault once.

    Phase 1 (POWER 3.0) decoupled semantic embeddings from the core FTS
    index: the canonical embedder (BGE-M3) is a heavyweight, network/model
    download that must NOT be a hard dependency of the FTS path or of CI.
    So the test fixture builds an FTS-only index and relies on the B7
    fallback (semantic -> FTS) for semantic-style queries in tests.
    """

    monkeypatch.setenv("POWER_VAULT_DIR", str(sample_vault))
    from power_framework.core.searcher import _db_path, _sync_vault_to_db

    db_path = _db_path()  # honors POWER_SEARCH_DB isolation
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    _sync_vault_to_db(sample_vault, conn, sync_embeddings=False)
    conn.close()
    return sample_vault


@pytest.fixture
def semantic_indexed_vault(sample_vault: Path, monkeypatch):
    """Build a full FTS + embedding index, skipping if no embedder is available.

    This is environment-gated: if BGE-M3 cannot be loaded (offline CI), the
    fixture is skipped rather than failing — Phase 1 guarantees FTS works
    regardless of the embedder.
    """

    monkeypatch.setenv("POWER_VAULT_DIR", str(sample_vault))
    import pytest as _pytest

    from power_framework.core import embeddings as _emb
    from power_framework.core.searcher import _sync_vault_to_db

    if not _emb._embeddings_available():
        _pytest.skip("BGE-M3 embedder unavailable in this environment")

    db_path = get_cache_dir() / "power_search.db"
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    _sync_vault_to_db(sample_vault, conn, sync_embeddings=True)
    conn.close()
    return sample_vault


class TestBackgroundIndexer:
    """§1: search_vault must NOT synchronously index; it enqueues a request."""

    def test_search_does_not_block_on_sync(self, sample_vault, monkeypatch):
        monkeypatch.setenv("POWER_VAULT_DIR", str(sample_vault))
        # search_vault should return quickly (within <5s) even on an empty DB
        # because it no longer calls _sync_vault_to_db synchronously.
        import time

        t0 = time.time()
        results = search_vault(sample_vault, "test", mode="fts", max_results=5)
        elapsed = time.time() - t0
        assert elapsed < 5.0
        # On an empty index it legitimately returns nothing.
        assert isinstance(results, list)

    def test_request_sync_enqueues(self, sample_vault, monkeypatch):
        monkeypatch.setenv("POWER_VAULT_DIR", str(sample_vault))
        # Prevent the background worker from draining/clearing the queue so the
        # assertion is deterministic (the worker runs in a separate thread).
        monkeypatch.setattr(index_worker, "ensure_indexer_running", lambda: None)
        index_worker._clear_queue()
        index_worker.request_sync(sample_vault, mode="fts")
        # Read from the same (POWER_SEARCH_DB-isolated) path the worker uses.
        conn = sqlite3.connect(str(index_worker._db_path()), timeout=30)
        index_worker._ensure_queue_table(conn)
        row = conn.execute("SELECT mode FROM sync_queue WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "fts"

    def test_coverage_reports_counts(self, indexed_vault):
        indexed, total = index_worker.get_coverage(indexed_vault)
        assert total > 0
        assert indexed == total


class TestSemanticNumpy:
    """§5: _semantic_search uses vectorized numpy cosine."""

    def test_numpy_cosine_returns_ranked(self, indexed_vault):
        res_np = _semantic_search(indexed_vault, "test project resource", max_results=5)
        assert isinstance(res_np, list)
        if res_np:
            scores = [r.score for r in res_np]
            assert scores == sorted(scores, reverse=True)

    def test_semantic_empty_on_no_embeddings(self, tmp_path):
        res = _semantic_search(tmp_path, "anything", max_results=5)
        assert res == []


class TestBoundedRerank:
    """§4: hybrid_reranked passes at most RERANK_CANDIDATE_LIMIT to reranker."""

    def test_rerank_limit_constant(self):
        assert RERANK_CANDIDATE_LIMIT == 20

    def test_hybrid_reranked_returns_results(self, indexed_vault):
        results = _hybrid_reranked_search(indexed_vault, "test project", max_results=5)
        assert isinstance(results, list)
        assert len(results) <= 5


class TestPragmaTuning:
    """§3: _init_db applies cache_size and mmap_size pragmas."""

    def test_pragmas_applied(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "t.db"))
        _init_db(conn)
        cache = conn.execute("PRAGMA cache_size").fetchone()[0]
        mmap = conn.execute("PRAGMA mmap_size").fetchone()[0]
        conn.close()
        assert cache == -65536
        assert mmap >= 1024 * 1024 * 1024


class TestCoverageFooter:
    """§6: format_search_results shows honest index coverage when vault given."""

    def test_footer_present_when_indexed(self, indexed_vault):
        results = search_vault(indexed_vault, "test", mode="fts", max_results=5)
        report = format_search_results(results, "test", mode="fts", vault_dir=indexed_vault)
        assert "Index coverage:" in report

    def test_no_footer_without_vault(self):
        from power_framework.core.searcher import SearchResult

        results = [
            SearchResult(
                rel_path="a.md",
                title="A",
                description="d",
                note_type="Resource",
                score=1.0,
                snippet="",
                match_count=1,
            )
        ]
        report = format_search_results(results, "test", mode="fts")
        assert "Index coverage:" not in report


class TestEmbeddingCacheDir:
    """§2: BGE-M3 ONNX model cache dir is pinned to a persistent location."""

    def test_embedding_cache_dir_persistent(self):
        from power_framework.core.utils import get_embedding_cache_dir

        cache = get_embedding_cache_dir()
        assert cache is not None
        # Must NOT live under a transient /tmp path (persistent across runs
        # per Phase 1 §2); it should resolve under the XDG cache dir.
        assert "/tmp/" not in str(cache)
        assert cache.exists() or cache.parent.exists()


class TestSemanticFallback:
    """B7 / FP-7: semantic search must never silently return [].

    When the embedder is unavailable or the embedding store is empty,
    _semantic_search must degrade to FTS and return real results (or an
    honest empty list only when the FTS index is genuinely empty too).
    """

    def test_falls_back_to_fts_on_dead_embedder(self, indexed_vault, monkeypatch):
        from power_framework.core import searcher as S

        class _Dead:
            def embed(self, text):
                raise RuntimeError("simulated dead embedder")

            def embed_batch(self, texts, batch_size=8):
                raise RuntimeError("simulated dead embedder")

        monkeypatch.setattr(S, "get_embedding_manager", lambda *a, **k: _Dead())
        # Query uses terms present in the indexed sample notes ("test", "project")
        # so the FTS fallback can return real hits (FTS is a strict AND of terms,
        # unlike fuzzy semantic matching).
        res = S._semantic_search(indexed_vault, "test project", max_results=5)
        # Not a silent empty list; FTS fallback returns the indexed notes.
        assert isinstance(res, list)
        assert len(res) > 0

    def test_no_silent_empty_on_empty_vault(self, tmp_path):
        from power_framework.core import searcher as S

        # An empty vault has neither embeddings nor FTS hits -> honest [].
        res = S._semantic_search(tmp_path, "anything", max_results=5)
        assert res == []
