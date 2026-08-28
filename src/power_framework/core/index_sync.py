"""Shared SQLite index projection used by search and atomic generation publication."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import sqlite3
from collections import Counter
from typing import TYPE_CHECKING, Any, cast

from .chunker import SemanticChunker
from .constants import DENSE_INDEX_SCHEMA_VERSION, is_catalog_filename
from .ignore import should_skip
from .parser import read_file_content, validate_metadata
from .source_projection import scan_projection, write_projection

if TYPE_CHECKING:
    from pathlib import Path

    from .models import OKFMetadata

logger = logging.getLogger(__name__)


def _get_embedding_manager() -> Any:
    """Load the optional embedding manager only when a dense sync needs it."""
    from power_framework.experimental.embeddings import get_embedding_manager

    return get_embedding_manager()


def _embedding_manifest_identity(embedder: object) -> tuple[str, str]:
    """Return stable provider and model identifiers without loading the model."""
    provider = type(embedder).__name__
    model = str(getattr(embedder, "model_name", getattr(embedder, "repo", "unknown")))
    return provider, model


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens."""
    return re.findall(r"[a-z0-9а-яєіїґ']+", text.lower())  # noqa: RUF001


def _compute_tf_vector(tokens: list[str]) -> dict[str, float]:
    """Compute a normalized term-frequency vector from tokens."""
    counter = Counter(tokens)
    total = len(tokens) or 1
    return {word: count / total for word, count in counter.items()}


def _stable_chunk_id(
    source_content_hash: str,
    section_identity: str,
    chunk_text: str,
    ordinal: int = 0,
) -> str:
    """Return a stable chunk ID that distinguishes repeated section content."""
    normalized_chunk = " ".join(chunk_text.split()).casefold()
    normalized_section = " ".join(section_identity.split()).casefold()
    payload = "\x00".join((source_content_hash, normalized_section, str(ordinal), normalized_chunk))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chunk_section_identity(chunk_text: str, ordinal: int) -> str:
    """Use the first heading in a chunk, with a deterministic fallback label."""
    for line in chunk_text.splitlines():
        if line.lstrip().startswith("#"):
            return line.lstrip("#").strip() or f"section-{ordinal}"
    return f"section-{ordinal}"


def _sync_vault_to_db(
    vault_dir: Path,
    conn: sqlite3.Connection,
    sync_embeddings: bool = False,
    force_rebuild: bool = False,
) -> None:
    """Synchronize the files in the vault with the SQLite database.

    Args:
        vault_dir: Path to the vault root.
        conn: An open SQLite connection (WAL mode, busy_timeout set).
        sync_embeddings: When False (default) only the lightweight FTS index and
            file metadata are refreshed. This avoids loading the embedding model
            on every FTS search/index. Set True only when vector or semantic
            search actually needs the dense embeddings.
        force_rebuild: Wipe the dense-embedding tables before the pass so every
            note is re-embedded. Required after a provider / dimension change
            (e.g. MiniLM 384d -> Qwen3 1024d) because the incremental sync
            only revisits files whose ``mtime`` changed and would otherwise keep
            stale vectors of the old dimensionality.

    Memory note (v2.2.0): when ``sync_embeddings`` is True the dense embeddings
    are computed in **batches** via ``embedder.embed_batch`` instead of one
    ``embed`` call per document/chunk. This bounds peak RAM (no OOM on 8-12 GB
    hosts) and is ~5-10x faster than per-item embedding. Results are streamed to
    the DB with periodic commits so the working set never holds the whole vault.
    """
    cursor = conn.cursor()
    if sync_embeddings:
        chunk_cnt = cursor.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
        dense_manifest = dict(
            cursor.execute("SELECT manifest_key, manifest_value FROM dense_index_manifest")
        )
        schema_stale = dense_manifest.get("schema_version") != DENSE_INDEX_SCHEMA_VERSION
        if force_rebuild or chunk_cnt == 0 or schema_stale:
            logger.info(
                "Dense embeddings missing, stale, or force rebuild requested: resetting mtime ..."
            )
            try:
                cursor.execute("DELETE FROM doc_embeddings")
                cursor.execute("DELETE FROM chunk_embeddings")
                cursor.execute("UPDATE file_metadata SET mtime = 0")
                conn.commit()
            except sqlite3.OperationalError:
                logger.warning("Embedding tables locked (concurrent sync?), skipping reset")
                conn.rollback()

    disk_files: dict[str, float] = {}
    for filepath in vault_dir.rglob("*.md"):
        # Generated catalogs are navigation, not knowledge. Keep every page
        # out of both sparse and dense indexes, including `_index-N.md` pages.
        if filepath.name in ("index.md", "log.md") or is_catalog_filename(filepath.name):
            continue
        if should_skip(vault_dir, filepath.relative_to(vault_dir).as_posix()):
            continue

        try:
            rel_path = filepath.relative_to(vault_dir).as_posix()
            mtime = filepath.stat().st_mtime
            disk_files[rel_path] = mtime
        except Exception:  # noqa: S112
            continue

    cursor.execute("SELECT rel_path, mtime FROM file_metadata")
    db_files = {row[0]: row[1] for row in cursor.fetchall()}

    to_delete = [rel_path for rel_path in db_files if rel_path not in disk_files]
    if to_delete:
        cursor.executemany("DELETE FROM fts_notes WHERE rel_path = ?", [(r,) for r in to_delete])
        cursor.executemany(
            "DELETE FROM file_metadata WHERE rel_path = ?", [(r,) for r in to_delete]
        )
        cursor.executemany(
            "DELETE FROM doc_embeddings WHERE rel_path = ?", [(r,) for r in to_delete]
        )
        cursor.executemany(
            "DELETE FROM chunk_embeddings WHERE rel_path = ?", [(r,) for r in to_delete]
        )
        cursor.executemany("DELETE FROM tf_vectors WHERE rel_path = ?", [(r,) for r in to_delete])
        cursor.executemany(
            "DELETE FROM temporal_records WHERE rel_path = ?", [(r,) for r in to_delete]
        )

    embedder = _get_embedding_manager() if sync_embeddings else None

    # Recovery guard (fixes silent FP-7): if embeddings were requested but the
    # embedding tables are empty while FTS metadata exists, a prior sync must
    # have failed mid-embedding (e.g. OOM under a RAM limit). Don't trust the
    # mtime cache in that case — re-embed every file so the index isn't left
    # silently empty. Otherwise semantic search returns [] for valid queries.
    if sync_embeddings and embedder is not None:
        try:
            existing_chunks = cursor.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            existing_meta = cursor.execute("SELECT COUNT(*) FROM file_metadata").fetchone()[0]
            if existing_chunks == 0 and existing_meta > 0:
                logger.warning(
                    "Embedding tables empty but %d files indexed; forcing re-embed",
                    existing_meta,
                )
                cursor.execute("UPDATE file_metadata SET mtime = 0")
                conn.commit()
                db_files = dict.fromkeys(db_files, 0.0)
        except Exception as e:
            logger.warning("Embedding recovery check failed: %s", e)

    # v2.2.0: collect changed files first, then embed in batches. This avoids
    # holding the embedding model AND all vectors in memory at once.
    changed: list[tuple[str, str, OKFMetadata, float]] = []  # (rel_path, content, metadata, mtime)
    invalid_changed = False
    for idx, (rel_path, mtime) in enumerate(disk_files.items()):
        if idx % 50 == 0:
            logger.info("Sync scan: %d/%d (%s)", idx, len(disk_files), rel_path)
        if rel_path not in db_files or db_files[rel_path] != mtime:
            filepath = vault_dir / rel_path
            try:
                content = read_file_content(filepath)
                metadata = validate_metadata(content)
                if metadata is None:
                    invalid_changed = True
                    cursor.execute("DELETE FROM fts_notes WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM file_metadata WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM doc_embeddings WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM chunk_embeddings WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM tf_vectors WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM temporal_records WHERE rel_path = ?", (rel_path,))
                    continue
                changed.append((rel_path, content, metadata, mtime))
            except Exception as e:
                logger.warning("Processing failed for %s: %s", rel_path, e)
                continue

    logger.info(
        "Sync: %d changed file(s) of %d (embeddings=%s)",
        len(changed),
        len(disk_files),
        sync_embeddings,
    )

    # --- Lightweight pass: FTS + TF-vector (cheap, no model load) ---
    for rel_path, content, metadata, mtime in changed:
        try:
            tags_str = " ".join(metadata.tags)
            cursor.execute("DELETE FROM fts_notes WHERE rel_path = ?", (rel_path,))
            cursor.execute(
                "INSERT INTO fts_notes (title, tags, description, content, rel_path, note_type) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    metadata.title,
                    tags_str,
                    metadata.description,
                    content,
                    rel_path,
                    metadata.type,
                ),
            )
            cursor.execute(
                "INSERT OR REPLACE INTO file_metadata (rel_path, mtime) VALUES (?, ?)",
                (rel_path, mtime),
            )
            memory_json = (
                None
                if metadata.memory is None
                else json.dumps(metadata.memory.model_dump(mode="json"), sort_keys=True)
            )
            cursor.execute(
                "INSERT OR REPLACE INTO temporal_records (rel_path, memory_json) VALUES (?, ?)",
                (rel_path, memory_json),
            )

            full_text = " ".join(
                [metadata.title, " ".join(metadata.tags), metadata.description, content]
            )
            tokens = _tokenize(full_text)
            tf_vec = _compute_tf_vector(tokens)
            cursor.execute(
                "INSERT OR REPLACE INTO tf_vectors (rel_path, tf_data, mtime) VALUES (?, ?, ?)",
                (rel_path, json.dumps(tf_vec), mtime),
            )
        except Exception as e:
            logger.warning("FTS/TF write failed for %s: %s", rel_path, e)
            continue

    # Backfill the metadata-only projection for legacy databases after schema
    # creation or a database backup. A partial projection is never trusted by
    # retrieval, so rebuild it from already-indexed note content in one sync.
    expected_temporal_paths = {
        str(row[0]) for row in cursor.execute("SELECT rel_path FROM file_metadata").fetchall()
    }
    actual_temporal_paths = {
        str(row[0]) for row in cursor.execute("SELECT rel_path FROM temporal_records").fetchall()
    }
    if expected_temporal_paths != actual_temporal_paths:
        cursor.execute("DELETE FROM temporal_records")
        temporal_rows: list[tuple[str, str | None]] = []
        for rel_path, indexed_content in cursor.execute(
            "SELECT rel_path, content FROM fts_notes"
        ).fetchall():
            try:
                indexed_metadata = validate_metadata(indexed_content)
            except Exception:  # noqa: S112
                continue
            if indexed_metadata is None:
                continue
            memory_json = (
                None
                if indexed_metadata.memory is None
                else json.dumps(indexed_metadata.memory.model_dump(mode="json"), sort_keys=True)
            )
            temporal_rows.append((rel_path, memory_json))
        cursor.executemany(
            "INSERT OR REPLACE INTO temporal_records (rel_path, memory_json) VALUES (?, ?)",
            temporal_rows,
        )

    if not sync_embeddings and (changed or invalid_changed or to_delete):
        # A lightweight FTS sync cannot refresh dense vectors for changed
        # notes. Invalidate the dense contract instead of leaving stale rows
        # that semantic/reranked callers might mistake for current evidence.
        changed_paths = [rel_path for rel_path, *_ in changed]
        cursor.executemany(
            "DELETE FROM doc_embeddings WHERE rel_path = ?", [(path,) for path in changed_paths]
        )
        cursor.executemany(
            "DELETE FROM chunk_embeddings WHERE rel_path = ?", [(path,) for path in changed_paths]
        )
        cursor.execute("DELETE FROM dense_index_manifest")
        logger.info(
            "Dense index invalidated by FTS-only source changes; run power sync for dense search"
        )
    conn.commit()

    # Source APIs consume this complete, rebuildable projection. It is written
    # into the same staged generation transaction as FTS/TF metadata.
    write_projection(conn, scan_projection(vault_dir))

    if not (sync_embeddings and embedder is not None):
        _maybe_vacuum(conn, to_delete, db_files)
        return

    # --- Dense-embedding pass: batched, adaptive batch size (v2.2.0) ---
    # Two queues: doc-level (one vector per note) and chunk-level (one vector
    # per chunk). Embedding is done per-queue in fixed-size batches so peak RAM
    # stays bounded regardless of vault size.
    doc_items: list[tuple[str, str, float]] = []  # (rel_path, full_text, mtime)
    chunk_items: list[tuple[str, str, str, float]] = []  # (chunk_id, rel_path, text, mtime)
    chunker = SemanticChunker()
    files_seen = len(changed)
    files_projected = 0
    for rel_path, content, metadata, mtime in changed:
        try:
            full_text = " ".join(
                [metadata.title, " ".join(metadata.tags), metadata.description, content]
            )
            doc_items.append((rel_path, full_text, mtime))

            cursor.execute("DELETE FROM chunk_embeddings WHERE rel_path = ?", (rel_path,))
            # B6 (POWER 3.0): short notes (<200 tokens) get a single whole-document
            # chunk instead of semantic splitting. Splitting a tiny note yields
            # either 0 chunks (lost from dense retrieval) or fragments that lose
            # cross-sentence context. Whole-doc embedding keeps short notes fully
            # retrievable and matches the FTS/BM25 unit of retrieval.
            approx_tokens = len(re.findall(r"\S+", content))
            if approx_tokens < 200:
                chunks = [
                    f"[Document: {metadata.title} | Description: {metadata.description}]\n{content.strip()}"
                ]
            else:
                chunks = chunker.chunk(
                    content, title=metadata.title, description=metadata.description
                )
            source_content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            for i, chunk_text in enumerate(chunks):
                chunk_items.append(
                    (
                        _stable_chunk_id(
                            source_content_hash,
                            _chunk_section_identity(chunk_text, i),
                            chunk_text,
                            ordinal=i,
                        ),
                        rel_path,
                        chunk_text,
                        mtime,
                    )
                )
            files_projected += 1
        except Exception as exc:
            logger.exception(
                "Chunk projection failed for %s (files_seen=%d files_projected=%d "
                "files_excluded=1): %s: %s",
                rel_path,
                files_seen,
                files_projected,
                type(exc).__name__,
                exc,
            )
            raise RuntimeError(f"chunk projection failed for {rel_path}") from exc

    logger.info(
        "Chunk projection complete: files_seen=%d files_projected=%d files_excluded=0 "
        "projected_chunks=%d",
        files_seen,
        files_projected,
        len(chunk_items),
    )

    _embed_and_store(embedder, cursor, conn, doc_items, chunk_items)
    dense_row = cursor.execute(
        "SELECT COUNT(*), MIN(LENGTH(embedding)) FROM chunk_embeddings"
    ).fetchone()
    dense_count, embedding_bytes = dense_row
    if dense_count and embedding_bytes and embedding_bytes % 4 == 0:
        provider, model = _embedding_manifest_identity(embedder)
        cursor.executemany(
            "INSERT OR REPLACE INTO dense_index_manifest (manifest_key, manifest_value) VALUES (?, ?)",
            [
                ("schema_version", DENSE_INDEX_SCHEMA_VERSION),
                ("embedding_dimension", str(embedding_bytes // 4)),
                ("chunk_count", str(dense_count)),
                ("embedding_provider", provider),
                ("embedding_model", model),
            ],
        )
        conn.commit()
    _maybe_vacuum(conn, to_delete, db_files)
    conn.commit()


def _embed_and_store(
    embedder: Any,
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    doc_items: list[tuple[str, str, float]],
    chunk_items: list[tuple[str, str, str, float]],
) -> None:
    """Embed document + chunk texts in adaptive batches and stream to the DB.

    Peak RAM is bounded by ``batch_size`` and by committing every
    ``POWER_EMBED_COMMIT_EVERY`` items so the SQLite WAL never buffers the whole
    vault (which previously spiked ZFS write interrupts). If the embedding
    backend cannot allocate memory for a batch (ONNXRuntime arena failure or
    Python ``MemoryError``), the batch size is halved and retried — eventually
    down to a single item — so a sync survives memory pressure instead of
    crashing the host.
    """
    import struct

    # Low-RAM default: Qwen3-0.6B on CPU allocates a multi-GB arena per MatMul
    # node at large batch sizes, so keep the default small. Tune up on bigger
    # hosts via POWER_EMBED_BATCH_SIZE.
    batch_size = int(os.getenv("POWER_EMBED_BATCH_SIZE", "8"))
    commit_every = int(os.getenv("POWER_EMBED_COMMIT_EVERY", "50"))

    def _embed_retry(texts: list[str], bs: int) -> list[list[float]] | None:
        """Embed ``texts`` with adaptive halving on any allocation failure.

        Returns the vectors, or ``None`` if even ``batch_size=1`` cannot be
        allocated (e.g. a backend whose single-item inference arena exceeds
        available RAM). Callers skip the item instead of aborting the whole sync.
        """
        cur = bs
        last_err: Exception | None = None
        while cur >= 1:
            try:
                return cast("list[list[float]]", embedder.embed_batch(texts, batch_size=cur))
            except Exception as e:
                last_err = e
                if cur == 1:
                    break
                cur //= 2
                logger.warning(
                    "Embedding allocation failed (bs=%d): %s — shrinking to %d",
                    cur * 2,
                    type(e).__name__,
                    cur,
                )
        logger.error(
            "Embedding skipped: backend cannot allocate even batch_size=1 (%s). "
            "Use a smaller model or raise POWER_SYNC_VMEM_LIMIT_MB.",
            type(last_err).__name__,
        )
        return None

    def _store_docs(items: list[tuple[str, str, float]]) -> None:
        texts = [t for _, t, _ in items]
        vecs = _embed_retry(texts, batch_size)
        if vecs is None:
            return
        for (rel_path, _, mtime), vec in zip(items, vecs, strict=True):
            blob = struct.pack(f"{len(vec)}f", *vec)
            cursor.execute(
                "INSERT OR REPLACE INTO doc_embeddings (rel_path, embedding, mtime) VALUES (?, ?, ?)",
                (rel_path, blob, mtime),
            )

    def _store_chunks(items: list[tuple[str, str, str, float]]) -> None:
        texts = [t for _, _, t, _ in items]
        vecs = _embed_retry(texts, batch_size)
        if vecs is None:
            return
        for (chunk_id, rel_path, chunk_content, mtime), vec in zip(items, vecs, strict=True):
            blob = struct.pack(f"{len(vec)}f", *vec)
            cursor.execute(
                "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime) VALUES (?, ?, ?, ?, ?)",
                (chunk_id, rel_path, blob, chunk_content, mtime),
            )

    def _safe_commit() -> None:
        """Commit, but surface disk I/O errors LOUDLY instead of silently
        corrupting chunk_embeddings (fixes B8).

        A ``sqlite3.OperationalError: disk I/O error`` mid-embedding used to be
        swallowed by a broad ``except`` upstream, leaving the embedding tables
        half-written and the semantic index quietly broken. We roll back the
        pending transaction and re-raise so ``_sync_vault_to_db`` can abort the
        pass cleanly (the mtime cache is only advanced on a successful commit,
        so the next sync re-embeds the missed files rather than trusting a
        corrupt partial index).
        """
        try:
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.error(
                "DB commit failed during embedding pass (%s) — rolling back "
                "partial chunk_embeddings to avoid a silently corrupt index.",
                e,
            )
            with contextlib.suppress(Exception):
                conn.rollback()
            raise

    total = len(doc_items) + len(chunk_items)
    for i in range(0, len(doc_items), batch_size):
        _store_docs(doc_items[i : i + batch_size])
        if (i // batch_size) % commit_every == 0:
            _safe_commit()
    for i in range(0, len(chunk_items), batch_size):
        _store_chunks(chunk_items[i : i + batch_size])
        if (i // batch_size) % commit_every == 0:
            _safe_commit()
    _safe_commit()
    logger.info("Embedding pass complete: %d vector(s) written", total)
    rowc = cursor.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
    logger.info("DEBUG AT END OF EMBED_AND_STORE: chunk_embeddings=%d", rowc)


def _maybe_vacuum(
    conn: sqlite3.Connection, to_delete: list[str], db_files: dict[str, float]
) -> None:
    # Performance Plan §2: do NOT run VACUUM on every sync (it rebuilds the
    # whole DB and blocks writers). Only vacuum when a meaningful fraction of
    # rows were deleted (significant churn), otherwise leave free pages for
    # incremental reuse.
    if to_delete and len(to_delete) >= max(10, len(db_files) // 10):
        try:
            conn.execute("PRAGMA incremental_vacuum")
        except Exception as e:  # pragma: no cover
            logger.debug("incremental_vacuum failed: %s", e)
