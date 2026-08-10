"""Tests for Performance Plan §1-§6 search and explicit-sync behavior."""

from __future__ import annotations

import sqlite3
import tempfile
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from power_framework.core.coverage import get_index_coverage
from power_framework.core.searcher import (
    RERANK_CANDIDATE_LIMIT,
    DenseIndexUnavailableError,
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
    The fixture deliberately builds an FTS-only index; semantic and reranked
    modes must reject it instead of silently changing retrieval contracts.
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

    from power_framework.core import embeddings as _emb
    from power_framework.core.searcher import _sync_vault_to_db

    if not _emb._embeddings_available():
        pytest.skip("BGE-M3 embedder unavailable in this environment")

    db_path = get_cache_dir() / "power_search.db"
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    _sync_vault_to_db(sample_vault, conn, sync_embeddings=True)
    conn.close()
    return sample_vault


class TestExplicitIndexing:
    """§1: search never starts a worker; indexing remains an explicit action."""

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

    def test_coverage_reports_counts(self, indexed_vault):
        indexed, total = get_index_coverage(indexed_vault)
        assert total > 0
        assert indexed == total

    def test_coverage_reads_published_generation(self, sample_vault, monkeypatch, tmp_path):
        monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "power-cache"))

        from power_framework.core.generation_index import sync_vault_atomically

        sync_vault_atomically(sample_vault, sync_embeddings=False)

        indexed, total = get_index_coverage(sample_vault)
        assert total == 5
        assert indexed == total

    def test_coverage_excludes_paginated_catalog_pages(self, tmp_path):
        resources = tmp_path / "03_Resources"
        resources.mkdir()
        (resources / "real-note.md").write_text("# Real note\n", encoding="utf-8")
        (resources / "_index-2.md").write_text("# Generated catalog page\n", encoding="utf-8")

        indexed, total = get_index_coverage(tmp_path)

        assert indexed == 0
        assert total == 1


class TestSemanticNumpy:
    """Semantic search requires a compatible dense index before model loading."""

    def test_semantic_search_rejects_fts_only_index(self, indexed_vault):
        with pytest.raises(DenseIndexUnavailableError, match="power sync"):
            _semantic_search(indexed_vault, "test project resource", max_results=5)

    def test_semantic_search_rejects_missing_index(self, tmp_path):
        with pytest.raises(DenseIndexUnavailableError, match="power sync"):
            _semantic_search(tmp_path, "anything", max_results=5)


class TestBoundedRerank:
    """§4: hybrid_reranked passes at most RERANK_CANDIDATE_LIMIT to reranker."""

    def test_rerank_limit_constant(self):
        assert RERANK_CANDIDATE_LIMIT == 20

    def test_hybrid_reranked_uses_hermetic_reranker(self, indexed_vault, monkeypatch):
        from power_framework.core import searcher

        class FakeReranker:
            def rerank(self, query: str, documents: list[str]) -> list[float]:
                del query
                return [float(len(documents) - rank) for rank in range(len(documents))]

        monkeypatch.setattr(searcher, "_get_reranker", lambda: FakeReranker())
        monkeypatch.setattr(searcher, "_semantic_search", lambda *args, **kwargs: [])
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
        assert tempfile.gettempdir() not in str(cache)
        assert cache.exists() or cache.parent.exists()


class TestSemanticFailClosed:
    """Dense retrieval never silently falls back to a different mode."""

    def test_does_not_load_embedder_without_dense_index(self, indexed_vault, monkeypatch):
        from power_framework.core import searcher

        monkeypatch.setattr(
            searcher,
            "get_embedding_manager",
            lambda: pytest.fail("embedder must not load before index validation"),
        )
        with pytest.raises(DenseIndexUnavailableError, match="power sync"):
            searcher._semantic_search(indexed_vault, "test project", max_results=5)

    def test_empty_vault_reports_missing_dense_index(self, tmp_path):
        from power_framework.core import searcher

        with pytest.raises(DenseIndexUnavailableError, match="power sync"):
            searcher._semantic_search(tmp_path, "anything", max_results=5)
