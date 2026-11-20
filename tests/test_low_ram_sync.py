"""
Low-RAM sync tests (v2.2.0).

These guard against the OOM regression where ``_sync_vault_to_db`` embedded
every document/chunk with a per-item ``embed()`` call (9.4 GB peak on a 16 GB
i5-5200U). After the fix, embeddings are produced in batches via
``embed_batch`` and the batch size halves on MemoryError.
"""

from __future__ import annotations

import sqlite3
import struct
import sys
from contextlib import closing
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from power_framework.core import index_sync, searcher
from power_framework.core.constants import DENSE_INDEX_SCHEMA_VERSION

if TYPE_CHECKING:
    from pathlib import Path


# The atomic sync implementation owns the lazy embedding-loader seam.
def _patch_manager(monkeypatch, fake):
    monkeypatch.setattr(index_sync, "_get_embedding_manager", lambda *a, **k: fake)


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


def test_sync_ollama_adapter_uses_bounded_sdk_batches_and_preserves_output_mapping(
    monkeypatch, tmp_path
):
    """The production adapter/indexer path must bound SDK inputs and retain each vector."""
    from power_framework.experimental.embeddings import OllamaEmbeddingManager

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.setenv("POWER_EMBED_PROVIDER", "ollama")

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=3)

    requests: list[tuple[str, ...]] = []
    vector_ids: dict[str, float] = {}

    def embed(**kwargs) -> SimpleNamespace:
        model = kwargs["model"]
        texts = kwargs["input"]
        keep_alive = kwargs["keep_alive"]
        options = kwargs["options"]
        assert model == "synthetic-ollama"
        assert keep_alive == "2m"
        assert "num_thread" in options
        requests.append(tuple(texts))
        vectors = []
        for text in texts:
            if text not in vector_ids:
                vector_ids[text] = float(len(vector_ids) + 1)
            vectors.append([vector_ids[text]])
        return SimpleNamespace(embeddings=vectors)

    fake_ollama = ModuleType("ollama")
    fake_ollama.embed = embed  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setenv("POWER_EMBED_BATCH_SIZE", "2")
    monkeypatch.setenv("POWER_EMBED_COMMIT_EVERY", "2")
    _patch_manager(monkeypatch, OllamaEmbeddingManager(model_name="synthetic-ollama"))

    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))
    with closing(sqlite3.connect(db)) as conn:
        searcher._init_db(conn)
        searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)
        documents = conn.execute(
            "SELECT rel_path, embedding FROM doc_embeddings ORDER BY rel_path"
        ).fetchall()
        chunks = conn.execute(
            "SELECT content, embedding FROM chunk_embeddings ORDER BY content"
        ).fetchall()
        sources = conn.execute(
            "SELECT title, tags, description, content, rel_path FROM fts_notes"
        ).fetchall()

    document_texts = {
        rel_path: " ".join((title, tags, description, content))
        for title, tags, description, content, rel_path in sources
    }
    assert len(requests) == 4
    assert all(0 < len(request) <= 2 for request in requests)
    assert sum(map(len, requests)) == len(documents) + len(chunks) == 6
    assert len(documents) == len(chunks) == 3
    for rel_path, blob in documents:
        assert struct.unpack("f", blob)[0] == vector_ids[document_texts[rel_path]]
    for content, blob in chunks:
        assert struct.unpack("f", blob)[0] == vector_ids[content]


def test_embed_retry_splits_actual_requests_after_memory_error(monkeypatch):
    requests: list[tuple[tuple[str, ...], int]] = []

    class MemorySensitiveEmbedder:
        def embed_batch(self, texts: list[str], batch_size: int) -> list[list[float]]:
            requests.append((tuple(texts), batch_size))
            if len(texts) > 2:
                raise MemoryError("synthetic allocation pressure")
            return [[float(text[-1])] for text in texts]

    monkeypatch.setenv("POWER_EMBED_BATCH_SIZE", "4")
    monkeypatch.setenv("POWER_EMBED_COMMIT_EVERY", "50")
    with closing(sqlite3.connect(":memory:")) as conn:
        searcher._init_db(conn)
        index_sync._embed_and_store(
            MemorySensitiveEmbedder(),
            conn.cursor(),
            conn,
            [(f"note-{index}", f"text-{index}", float(index)) for index in range(4)],
            [],
        )
        rows = conn.execute(
            "SELECT rel_path, embedding FROM doc_embeddings ORDER BY rel_path"
        ).fetchall()

    assert requests == [
        (("text-0", "text-1", "text-2", "text-3"), 4),
        (("text-0", "text-1"), 2),
        (("text-2", "text-3"), 2),
    ]
    assert [struct.unpack("f", blob)[0] for _, blob in rows] == [0.0, 1.0, 2.0, 3.0]


def test_embed_and_store_commits_after_configured_vector_item_count():
    class FakeEmbedder:
        def embed_batch(self, texts: list[str], batch_size: int) -> list[list[float]]:
            del batch_size
            return [[float(len(text))] for text in texts]

    writes_since_commit = 0
    committed_write_counts: list[int] = []

    def trace(statement: str) -> None:
        nonlocal writes_since_commit
        if statement.startswith("INSERT OR REPLACE INTO doc_embeddings") or statement.startswith(
            "INSERT OR REPLACE INTO chunk_embeddings"
        ):
            writes_since_commit += 1
        elif statement == "COMMIT":
            committed_write_counts.append(writes_since_commit)
            writes_since_commit = 0

    with closing(sqlite3.connect(":memory:")) as conn:
        searcher._init_db(conn)
        conn.set_trace_callback(trace)
        index_sync._embed_and_store(
            FakeEmbedder(),
            conn.cursor(),
            conn,
            [(f"note-{index}", f"doc-{index}", float(index)) for index in range(5)],
            [
                (f"chunk-{index}", f"note-{index}", f"body-{index}", float(index))
                for index in range(3)
            ],
            limits=(4, 3),
        )

    assert committed_write_counts == [3, 3, 2]


@pytest.mark.parametrize(
    ("limits", "error_code"),
    [
        ((129, 3), "invalid_power_embed_batch_size:maximum_is_128"),
        ((8, 4097), "invalid_power_embed_commit_every:maximum_is_4096"),
    ],
    ids=["batch-limit", "commit-limit"],
)
def test_embed_and_store_rejects_unbounded_supplied_limits_before_database_mutation(
    limits, error_code
):
    class FakeEmbedder:
        def embed_batch(self, texts: list[str], batch_size: int) -> list[list[float]]:
            del batch_size
            return [[1.0] for _ in texts]

    with closing(sqlite3.connect(":memory:")) as conn:
        searcher._init_db(conn)
        changes_before = conn.total_changes
        with pytest.raises(ValueError, match=error_code):
            index_sync._embed_and_store(
                FakeEmbedder(),
                conn.cursor(),
                conn,
                [("note", "text", 0.0)],
                [],
                limits=limits,
            )
        assert conn.total_changes == changes_before


@pytest.mark.parametrize(
    ("error_type", "message"),
    [
        (TypeError, "synthetic SDK type error"),
        (ValueError, "synthetic invalid-vector protocol error"),
    ],
    ids=["sdk-type-error", "protocol-error"],
)
def test_embed_retry_propagates_non_memory_errors_without_retry(
    monkeypatch, caplog, error_type, message
):
    calls: list[tuple[str, ...]] = []

    class FailingEmbedder:
        def embed_batch(self, texts: list[str], batch_size: int) -> list[list[float]]:
            del batch_size
            calls.append(tuple(texts))
            raise error_type(message)

    monkeypatch.setenv("POWER_EMBED_BATCH_SIZE", "2")
    monkeypatch.setenv("POWER_EMBED_COMMIT_EVERY", "50")
    with closing(sqlite3.connect(":memory:")) as conn, caplog.at_level("WARNING"):
        searcher._init_db(conn)
        with pytest.raises(error_type, match=message):
            index_sync._embed_and_store(
                FailingEmbedder(),
                conn.cursor(),
                conn,
                [("note-0", "text-0", 0.0), ("note-1", "text-1", 1.0)],
                [],
            )

    assert calls == [("text-0", "text-1")]
    assert message not in caplog.text


@pytest.mark.parametrize(
    ("env_name", "value", "error_code"),
    [
        ("POWER_EMBED_BATCH_SIZE", "0", "invalid_power_embed_batch_size:must_be_positive"),
        ("POWER_EMBED_BATCH_SIZE", "-1", "invalid_power_embed_batch_size:must_be_positive"),
        (
            "POWER_EMBED_BATCH_SIZE",
            "not-an-integer",
            "invalid_power_embed_batch_size:expected_integer",
        ),
        ("POWER_EMBED_BATCH_SIZE", "129", "invalid_power_embed_batch_size:maximum_is_128"),
        ("POWER_EMBED_COMMIT_EVERY", "0", "invalid_power_embed_commit_every:must_be_positive"),
        ("POWER_EMBED_COMMIT_EVERY", "-1", "invalid_power_embed_commit_every:must_be_positive"),
        (
            "POWER_EMBED_COMMIT_EVERY",
            "not-an-integer",
            "invalid_power_embed_commit_every:expected_integer",
        ),
        ("POWER_EMBED_COMMIT_EVERY", "4097", "invalid_power_embed_commit_every:maximum_is_4096"),
    ],
    ids=[
        "batch-zero",
        "batch-negative",
        "batch-noninteger",
        "batch-over-cap",
        "commit-zero",
        "commit-negative",
        "commit-noninteger",
        "commit-over-cap",
    ],
)
def test_sync_rejects_invalid_embedding_limits_before_database_mutation(
    monkeypatch, tmp_path, env_name, value, error_code
):
    class FakeEmbedder:
        dimension = 1

        def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
            del batch_size
            return [[1.0] for _ in texts]

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=1)
    monkeypatch.setenv("POWER_EMBED_BATCH_SIZE", "8")
    monkeypatch.setenv("POWER_EMBED_COMMIT_EVERY", "50")
    monkeypatch.setenv(env_name, value)
    _patch_manager(monkeypatch, FakeEmbedder())

    with closing(sqlite3.connect(":memory:")) as conn:
        searcher._init_db(conn)
        changes_before = conn.total_changes
        with pytest.raises(ValueError, match=error_code):
            searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)
        assert conn.total_changes == changes_before


def test_repeated_sections_get_distinct_chunk_ids(monkeypatch, tmp_path):
    """Identical sections in one note must not overwrite each other's vectors."""
    vault = tmp_path / "vault"
    notes = vault / "03_Resources"
    notes.mkdir(parents=True)
    repeated_body = " ".join(["identical-section-token"] * 210)
    (notes / "repeated.md").write_text(
        "---\n"
        "type: Resource\n"
        "title: Repeated sections\n"
        "description: duplicate section regression\n"
        "timestamp: 2026-01-01T00:00:00Z\n"
        "---\n\n"
        f"## Repeated\n{repeated_body}\n\n"
        f"## Repeated\n{repeated_body}\n",
        encoding="utf-8",
    )

    fake = _FakeManager()
    _patch_manager(monkeypatch, fake)
    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))

    with closing(sqlite3.connect(db)) as conn:
        searcher._init_db(conn)
        searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)
        rows = conn.execute("SELECT chunk_id, rel_path FROM chunk_embeddings").fetchall()

    assert len(rows) == 2
    assert len({row[0] for row in rows}) == 2


def test_stale_dense_manifest_rebuilds_chunk_identity_schema(monkeypatch, tmp_path):
    """Changing chunk identity rules must rebuild unchanged notes automatically."""
    vault = tmp_path / "vault"
    notes = vault / "03_Resources"
    notes.mkdir(parents=True)
    note = notes / "stable.md"
    note.write_text(
        "---\n"
        "type: Resource\n"
        "title: Stable note\n"
        "description: stale manifest regression\n"
        "timestamp: 2026-01-01T00:00:00Z\n"
        "---\n\n"
        "stable dense content\n",
        encoding="utf-8",
    )

    fake = _FakeManager()
    _patch_manager(monkeypatch, fake)
    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))

    with closing(sqlite3.connect(db)) as conn:
        searcher._init_db(conn)
        mtime = note.stat().st_mtime
        conn.execute(
            "INSERT INTO file_metadata(rel_path, mtime) VALUES (?, ?)",
            ("03_Resources/stable.md", mtime),
        )
        conn.execute(
            "INSERT INTO chunk_embeddings(chunk_id, rel_path, embedding, content, mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            ("legacy-chunk-id", "03_Resources/stable.md", b"legacy", "legacy", mtime),
        )
        conn.executemany(
            "INSERT INTO dense_index_manifest(manifest_key, manifest_value) VALUES (?, ?)",
            [
                ("schema_version", "2"),
                ("embedding_dimension", "3"),
                ("chunk_count", "1"),
                ("embedding_provider", "_FakeManager"),
                ("embedding_model", "unknown"),
            ],
        )
        conn.commit()

        searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)
        manifest = dict(
            conn.execute("SELECT manifest_key, manifest_value FROM dense_index_manifest")
        )
        chunk_ids = {row[0] for row in conn.execute("SELECT chunk_id FROM chunk_embeddings")}

    assert manifest["schema_version"] == DENSE_INDEX_SCHEMA_VERSION
    assert "legacy-chunk-id" not in chunk_ids


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


class _SpyBgeM3Manager:
    """Offline BGE-M3-shaped double recording batch sizes without loading weights."""

    model_name = "BAAI/bge-m3"
    dimension = 1024

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        self.calls.append((len(texts), batch_size))
        return [[0.1] * 4 for _ in texts]


def test_sync_preflight_refuses_undersized_ram_and_force_does_not_bypass(
    monkeypatch,
    tmp_path: Path,
    caplog,
):
    """Issue #467: undersized host refuses before loading embedder or calling embed_batch."""
    from power_framework.core import cli, generation_index, sync_memory

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.delenv("POWER_EMBED_PROVIDER", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=4)

    spy = _SpyBgeM3Manager()
    loader_calls: list[int] = []

    def _counting_loader(*_a, **_k):
        loader_calls.append(1)
        return spy

    monkeypatch.setattr(index_sync, "_get_embedding_manager", _counting_loader)
    monkeypatch.setattr(sync_memory, "available_memory_bytes", lambda: 512 * 1024 * 1024)

    with (
        caplog.at_level("ERROR"),
        pytest.raises(
            generation_index.IndexGenerationError,
            match=r"Dense sync preflight refused: estimated RAM ~\d+ MiB exceeds available ~512 MiB",
        ),
    ):
        generation_index.sync_vault_atomically(vault, sync_embeddings=True)

    assert len(loader_calls) == 0
    assert spy.calls == []

    # CLI --force must NOT overload low-memory override or load the embedder.
    exit_force = cli._cmd_sync(
        type(
            "Args",
            (),
            {
                "path": str(vault),
                "fts_only": False,
                "force": True,
                "accept_dense_loss": False,
                "allow_low_memory": False,
                "allow_partial": False,
            },
        )()
    )
    assert exit_force == 1
    assert len(loader_calls) == 0
    assert spy.calls == []


def test_sync_preflight_allows_explicit_allow_low_memory_with_batch_one(
    monkeypatch,
    tmp_path: Path,
    caplog,
):
    """Explicit --allow-low-memory logs a warning and runs with batch_size=1."""
    from power_framework.core import cli, sync_memory

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.delenv("POWER_EMBED_PROVIDER", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=3)

    spy = _SpyBgeM3Manager()
    _patch_manager(monkeypatch, spy)
    monkeypatch.setattr(sync_memory, "available_memory_bytes", lambda: 512 * 1024 * 1024)

    with caplog.at_level("WARNING"):
        exit_code = cli._cmd_sync(
            type(
                "Args",
                (),
                {
                    "path": str(vault),
                    "fts_only": False,
                    "force": False,
                    "accept_dense_loss": False,
                    "allow_low_memory": True,
                    "allow_partial": False,
                },
            )()
        )

    assert exit_code == 0
    assert spy.calls
    assert all(bs == 1 and size == 1 for size, bs in spy.calls)
    assert "low-memory override" in caplog.text


def test_sync_shrinks_batch_under_pressure_and_logs_progress_eta(
    monkeypatch,
    tmp_path: Path,
    caplog,
):
    """Mid-sync memory pressure shrinks batch_size cleanly and logs progress/ETA."""
    from power_framework.core import sync_memory

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.delenv("POWER_EMBED_PROVIDER", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=12)

    class _PressureSpy:
        model_name = "BAAI/bge-m3"
        dimension = 1024

        def __init__(self) -> None:
            self.calls: list[int] = []
            self.drop_pressure = False

        def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
            self.calls.append(batch_size)
            self.drop_pressure = True
            return [[0.1] * 4 for _ in texts]

    spy = _PressureSpy()
    _patch_manager(monkeypatch, spy)
    monkeypatch.setenv("POWER_EMBED_BATCH_SIZE", "8")
    monkeypatch.setattr(
        sync_memory,
        "available_memory_bytes",
        lambda: 256 * 1024 * 1024 if spy.drop_pressure else 8 * 1024 * 1024 * 1024,
    )

    db = tmp_path / "power_search.db"
    with closing(sqlite3.connect(str(db), timeout=30)) as conn, caplog.at_level("INFO"):
        searcher._init_db(conn)
        searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)

    assert spy.calls[0] == 8
    assert 4 in spy.calls
    assert spy.calls[-1] == 1
    assert "Embedding progress:" in caplog.text
    assert "%" in caplog.text
    assert "eta=" in caplog.text


def test_sync_fts_only_ignores_tiny_ram_preflight(monkeypatch, tmp_path: Path):
    """--fts-only never triggers dense RAM preflight even on a 128 MiB host."""
    from power_framework.core import generation_index, sync_memory

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=3)

    monkeypatch.setattr(sync_memory, "available_memory_bytes", lambda: 128 * 1024 * 1024)
    report = generation_index.sync_vault_atomically(vault, sync_embeddings=False)
    assert report.actual_files == 3
    assert report.actual_chunks == 0


def test_infer_embedder_dimension_avoids_property_and_remote_side_effects(monkeypatch):
    """infer_embedder_dimension never evaluates Ollama/FastEmbed @property getters."""
    from power_framework.core import sync_memory
    from power_framework.experimental import embeddings

    def _boom(*_a, **_k):
        raise AssertionError("must not trigger remote HTTP calls or model loading before preflight")

    monkeypatch.setattr(embeddings.OllamaEmbeddingManager, "_get_dim", _boom)
    monkeypatch.setattr(embeddings.FastEmbedManager, "_lazy_init", _boom)

    ollama_mgr = embeddings.OllamaEmbeddingManager("qwen3-embedding:0.6b")
    fast_mgr = embeddings.FastEmbedManager("BAAI/bge-small-en-v1.5")

    assert (
        sync_memory.infer_embedder_dimension(
            ollama_mgr, "OllamaEmbeddingManager", ollama_mgr.model_name
        )
        == 1024
    )
    assert (
        sync_memory.infer_embedder_dimension(fast_mgr, "FastEmbedManager", fast_mgr.model_name)
        == 384
    )
    assert (
        sync_memory.estimate_model_arena_bytes(
            "FastEmbedManager", "intfloat/multilingual-e5-large", 1024
        )
        == 1536 * 1024 * 1024
    )
    assert (
        sync_memory.estimate_model_arena_bytes("FastEmbedManager", "BAAI/bge-small-en-v1.5", 384)
        == 512 * 1024 * 1024
    )

    monkeypatch.setenv("POWER_SYNC_VMEM_LIMIT_MB", "")
    assert sync_memory.parse_int_env("POWER_SYNC_VMEM_LIMIT_MB", 0, minimum=0) == 0
    monkeypatch.setenv("POWER_SYNC_VMEM_LIMIT_MB", "not-an-int")
    assert sync_memory.parse_int_env("POWER_SYNC_VMEM_LIMIT_MB", 0, minimum=0) == 0


def test_incremental_noop_sync_skips_embedder_load(monkeypatch, tmp_path: Path):
    """Unchanged incremental sync with matching manifest must not load the heavy embedder."""
    from power_framework.core import generation_index, sync_memory

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.delenv("POWER_EMBED_PROVIDER", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=2)

    spy = _SpyBgeM3Manager()
    loader_calls: list[int] = []

    def _counting_loader(*_a, **_k):
        loader_calls.append(1)
        return spy

    monkeypatch.setattr(index_sync, "_get_embedding_manager", _counting_loader)
    monkeypatch.setattr(
        index_sync,
        "_configured_embedding_identity",
        lambda: ("_SpyBgeM3Manager", "BAAI/bge-m3"),
    )
    monkeypatch.setattr(sync_memory, "available_memory_bytes", lambda: 8 * 1024 * 1024 * 1024)

    first = generation_index.sync_vault_atomically(vault, sync_embeddings=True)
    assert first.actual_files == 2
    assert first.actual_chunks > 0
    assert len(loader_calls) == 1

    second = generation_index.sync_vault_atomically(vault, sync_embeddings=True)
    assert second.actual_files == 2
    assert second.actual_chunks == first.actual_chunks
    assert len(loader_calls) == 1


def test_sync_persists_shrunk_batch_size_after_oom_retry(monkeypatch, tmp_path: Path):
    """A Runtime MemoryError halving batch_size persists for remaining items."""
    from power_framework.core import sync_memory

    monkeypatch.delenv("POWER_SYNC_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.delenv("POWER_EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("POWER_EMBED_BATCH_SIZE", "4")

    vault = tmp_path / "vault"
    vault.mkdir()
    _make_vault(vault, n=6)

    class _OomOnceOnFourSpy:
        model_name = "BAAI/bge-m3"
        dimension = 1024

        def __init__(self) -> None:
            self.batch_sizes: list[int] = []
            self.failed = False

        def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
            self.batch_sizes.append(batch_size)
            if not self.failed and batch_size > 2:
                self.failed = True
                raise MemoryError("oom at bs=4")
            return [[0.1] * 4 for _ in texts]

    spy = _OomOnceOnFourSpy()
    _patch_manager(monkeypatch, spy)
    monkeypatch.setattr(sync_memory, "available_memory_bytes", lambda: 8 * 1024 * 1024 * 1024)

    db = tmp_path / "power_search.db"
    with closing(sqlite3.connect(str(db), timeout=30)) as conn:
        searcher._init_db(conn)
        searcher._sync_vault_to_db(vault, conn, sync_embeddings=True)

    assert spy.batch_sizes[:2] == [4, 2]
    assert all(bs <= 2 for bs in spy.batch_sizes[2:])
