"""
Low-RAM sync tests (v2.2.0).

These guard against the OOM regression where ``_sync_vault_to_db`` embedded
every document/chunk with a per-item ``embed()`` call (9.4 GB peak on a 16 GB
i5-5200U). After the fix, embeddings are produced in batches via
``embed_batch`` and the batch size halves on MemoryError.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from power_framework.core import searcher

if TYPE_CHECKING:
    from pathlib import Path


# searcher imports get_embedding_manager directly, so patch it there.
def _patch_manager(monkeypatch, fake):
    monkeypatch.setattr(searcher, "get_embedding_manager", lambda *a, **k: fake)


def _make_vault(vault: Path, n: int = 12) -> None:
    (vault / "03_Resources").mkdir(parents=True, exist_ok=True)
    for i in range(n):
        note = vault / "03_Resources" / f"Note_{i}.md"
        note.write_text(
            f"""---
type: Resource
title: "Resource Note {i}"
description: "Standard details for note {i}"
tags: [resource, note{i}]
timestamp: 2026-01-01T00:00:00
---

This is standard information number {i} regarding containerization and
homelab maintenance. It needs to be embedded in a batch with the others so
peak memory stays bounded on small hosts.
""",
            encoding="utf-8",
        )


class _FakeManager:
    """Records embed vs embed_batch usage and simulates MemoryError once."""

    def __init__(self) -> None:
        self.embed_calls = 0
        self.batch_calls: list[int] = []
        self._memory_error_on = 1  # first batch call raises, then succeeds

    def embed(self, text: str) -> list[float]:
        self.embed_calls += 1
        return [0.1, 0.2, 0.3]

    def embed_batch(self, texts, batch_size: int = 32):
        if self._memory_error_on > 0:
            self._memory_error_on -= 1
            raise MemoryError("simulated OOM")
        self.batch_calls.append(len(texts))
        dim = 3
        return [[float(((j + k) % 7) / 7.0) for k in range(dim)] for j in range(len(texts))]


def test_sync_uses_batch_not_per_item(monkeypatch, tmp_path):
    """Embeddings must go through embed_batch, never per-item embed()."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=10)

    fake = _FakeManager()
    _patch_manager(monkeypatch, fake)

    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))

    conn = sqlite3.connect(str(db), timeout=30)
    searcher._init_db(conn)
    searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)
    conn.close()

    # Critical: no per-item embedding happened.
    assert fake.embed_calls == 0, "per-item embed() must not be used during sync"
    assert len(fake.batch_calls) >= 1, "embed_batch() must be used during sync"

    # Vectors were actually written.
    conn = sqlite3.connect(str(db), timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM doc_embeddings")
    docs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunk_embeddings")
    chunks = cur.fetchone()[0]
    conn.close()
    assert docs == 10, f"expected 10 doc embeddings, got {docs}"
    assert chunks > 0, "expected chunk embeddings to be written"


def test_sync_adaptive_batch_on_memory_error(monkeypatch, tmp_path):
    """A MemoryError during embed_batch must not crash sync; batch shrinks."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=8)

    fake = _FakeManager()
    _patch_manager(monkeypatch, fake)

    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))

    conn = sqlite3.connect(str(db), timeout=30)
    searcher._init_db(conn)
    # Should not raise despite the simulated OOM on the first batch call.
    searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)
    conn.close()

    # After the MemoryError the retry path ran at least one batch.
    assert len(fake.batch_calls) >= 1
    # And critically: it never fell back to per-item embed().
    assert fake.embed_calls == 0


def test_sync_fts_only_skips_embedding(monkeypatch, tmp_path):
    """With sync_embeddings=False the embedder is never loaded."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=5)

    fake = _FakeManager()
    _patch_manager(monkeypatch, fake)

    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))

    conn = sqlite3.connect(str(db), timeout=30)
    searcher._init_db(conn)
    searcher._sync_vault_to_db(vault, conn, sync_embeddings=False)
    conn.close()

    assert fake.embed_calls == 0
    assert len(fake.batch_calls) == 0
    # FTS index still populated.
    conn = sqlite3.connect(str(db), timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fts_notes")
    assert cur.fetchone()[0] == 5
    conn.close()


def test_fastembed_parallel_is_bounded_not_all_cores(monkeypatch, tmp_path):
    """embed_batch must cap fastembed ``parallel`` to EMBED_NUM_THREADS.

    Regresses the 32 GB RSS incident on a 20-core host: fastembed's
    ``parallel=0`` spawned one model subprocess per core (20 copies of the
    MiniLM ONNX model + arena), ballooning RSS to ~30 GB.
    """
    from power_framework.core import embeddings

    captured = {}

    class _FakeModel:
        def embed(self, texts, batch_size=32, parallel=0):
            captured["parallel"] = parallel
            captured["batch_size"] = batch_size
            for _ in texts:
                yield [0.1, 0.2, 0.3]

    class _FakeManager(embeddings.FastEmbedManager):
        def _lazy_init(self):
            self._model = _FakeModel()

    monkeypatch.setenv("POWER_EMBED_NUM_THREADS", "2")
    # Re-import so EMBED_NUM_THREADS is read from the patched env.
    import importlib

    embeddings = importlib.reload(embeddings)
    monkeypatch.setattr(embeddings, "EMBED_NUM_THREADS", 2)

    mgr = _FakeManager()
    list(mgr.embed_batch(["a", "b", "c"], batch_size=8))

    assert captured["parallel"] == 2, (
        f"expected parallel=2 (bounded), got {captured.get('parallel')}"
    )
    assert captured["parallel"] != 0, "parallel=0 spawns one process per core (OOM risk)"
