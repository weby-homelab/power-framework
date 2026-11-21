"""Shared SQLite index projection used by search and atomic generation publication."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import re
import sqlite3
import time
from collections import Counter
from typing import TYPE_CHECKING, Any, cast

from . import sync_memory
from .chunker import SemanticChunker
from .constants import DENSE_INDEX_SCHEMA_VERSION, SKIP_FILES, is_catalog_filename
from .ignore import should_skip
from .parser import read_file_content, validate_metadata
from .source_projection import scan_projection, write_projection
from .utils import iter_vault_markdown_files

if TYPE_CHECKING:
    from pathlib import Path

    from .models import OKFMetadata

logger = logging.getLogger(__name__)


def _get_embedding_manager() -> Any:
    """Load the optional embedding manager only when a dense sync needs it."""
    from power_framework.experimental.embeddings import get_embedding_manager

    return get_embedding_manager()


def _configured_embedding_identity() -> tuple[str, str]:
    """Resolve the configured provider/model identity without loading model weights."""
    from power_framework.experimental.embeddings import configured_embedding_identity

    return configured_embedding_identity()


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
    allow_low_memory: bool | None = None,
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
            note is re-embedded. A change in the configured provider or model
            also triggers a rebuild, even when the files have not changed.
        allow_low_memory: Optional explicit override for the pre-flight memory
            estimate check when ``sync_embeddings`` is True.

    Memory note (v2.2.0): when ``sync_embeddings`` is True the dense embeddings
    are computed in **batches** via ``embedder.embed_batch`` instead of one
    ``embed`` call per document/chunk. This bounds peak RAM (no OOM on 8-12 GB
    hosts) and is ~5-10x faster than per-item embedding. Results are streamed to
    the DB with periodic commits so the working set never holds the whole vault.
    """
    embedding_limits = sync_memory.validated_embedding_limits() if sync_embeddings else None
    cursor = conn.cursor()
    rebuild_dense = False
    if sync_embeddings:
        provider, model = _configured_embedding_identity()
        chunk_cnt = cursor.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
        dense_manifest = dict(
            cursor.execute("SELECT manifest_key, manifest_value FROM dense_index_manifest")
        )
        schema_stale = dense_manifest.get("schema_version") != DENSE_INDEX_SCHEMA_VERSION
        identity_stale = (provider, model) != (
            dense_manifest.get("embedding_provider"),
            dense_manifest.get("embedding_model"),
        )
        rebuild_dense = force_rebuild or chunk_cnt == 0 or schema_stale or identity_stale
        if rebuild_dense:
            logger.info(
                "Dense embeddings missing, incompatible, or force rebuild requested: rebuilding"
            )
            # A failed reset must abort rather than re-label vectors from the old model.
            cursor.execute("DELETE FROM doc_embeddings")
            cursor.execute("DELETE FROM chunk_embeddings")
            cursor.execute("DELETE FROM dense_index_manifest")

    disk_files: dict[str, float] = {}
    for filepath in iter_vault_markdown_files(vault_dir):
        # Generated catalogs are navigation, not knowledge. Keep every page
        # out of both sparse and dense indexes, including `_index-N.md` pages.
        if filepath.name in SKIP_FILES or is_catalog_filename(filepath.name):
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

    # Recovery guard (fixes silent FP-7): if embeddings were requested but the
    # embedding tables are empty while FTS metadata exists, a prior sync must
    # have failed mid-embedding (e.g. OOM under a RAM limit). Don't trust the
    # mtime cache in that case — re-embed every file so the index isn't left
    # silently empty. Otherwise semantic search returns [] for valid queries.
    if sync_embeddings and not rebuild_dense:
        try:
            existing_chunks = cursor.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            existing_meta = cursor.execute("SELECT COUNT(*) FROM file_metadata").fetchone()[0]
            if existing_chunks == 0 and existing_meta > 0:
                logger.warning(
                    "Embedding tables empty but %d files indexed; forcing re-embed",
                    existing_meta,
                )
                rebuild_dense = True
        except Exception as e:
            logger.warning("Embedding recovery check failed: %s", e)

    # v2.2.0: collect changed files first, then embed in batches. This avoids
    # holding the embedding model AND all vectors in memory at once.
    changed: list[tuple[str, str, OKFMetadata, float]] = []  # (rel_path, content, metadata, mtime)
    invalid_changed = False
    for idx, (rel_path, mtime) in enumerate(disk_files.items()):
        if idx % 50 == 0:
            logger.info("Sync scan: %d/%d (%s)", idx, len(disk_files), rel_path)
        if rebuild_dense or rel_path not in db_files or db_files[rel_path] != mtime:
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

    if not sync_embeddings:
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
    reused_chunks = 0
    try:
        reusable_width = 0 if rebuild_dense else 4 * int(dense_manifest["embedding_dimension"])
    except (KeyError, ValueError):
        reusable_width = 0
    for rel_path, content, metadata, mtime in changed:
        try:
            full_text = " ".join(
                [metadata.title, " ".join(metadata.tags), metadata.description, content]
            )
            doc_items.append((rel_path, full_text, mtime))

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
            # Reuse only exact embedding input within this note and the
            # compatible model/schema. Keep the new generation's chunk IDs.
            reusable: dict[str, bytes] = {}
            if reusable_width > 0:
                for old_text, vector in cursor.execute(
                    "SELECT content, embedding FROM chunk_embeddings "
                    "WHERE rel_path = ? ORDER BY chunk_id",
                    (rel_path,),
                ):
                    if isinstance(vector, bytes) and len(vector) == reusable_width:
                        reusable.setdefault(old_text, vector)
            cursor.execute("DELETE FROM chunk_embeddings WHERE rel_path = ?", (rel_path,))
            source_content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            for i, chunk_text in enumerate(chunks):
                chunk_id = _stable_chunk_id(
                    source_content_hash,
                    _chunk_section_identity(chunk_text, i),
                    chunk_text,
                    ordinal=i,
                )
                vector = reusable.get(chunk_text)
                if vector is None:
                    chunk_items.append((chunk_id, rel_path, chunk_text, mtime))
                else:
                    cursor.execute(
                        "INSERT OR REPLACE INTO chunk_embeddings "
                        "(chunk_id, rel_path, embedding, content, mtime) VALUES (?, ?, ?, ?, ?)",
                        (chunk_id, rel_path, vector, chunk_text, mtime),
                    )
                    reused_chunks += 1
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
        "chunks_to_embed=%d reused_chunks=%d",
        files_seen,
        files_projected,
        len(chunk_items),
        reused_chunks,
    )

    item_count = len(doc_items) + len(chunk_items)
    if (
        item_count == 0
        and not to_delete
        and not invalid_changed
        and not rebuild_dense
        and chunk_cnt > 0
        and dense_manifest.get("chunk_count") == str(chunk_cnt)
        and dense_manifest.get("embedding_dimension") not in (None, "", "0")
    ):
        logger.info("Dense index already up-to-date (%d chunks); skipping embedder load", chunk_cnt)
        _maybe_vacuum(conn, to_delete, db_files)
        conn.commit()
        return

    if embedding_limits is None:
        embedding_limits = sync_memory.validated_embedding_limits()
    requested_batch_size = embedding_limits[0]
    preflight_dim = sync_memory.infer_embedder_dimension(None, provider, model)
    estimate = sync_memory.preflight_dense_sync_memory(
        provider=provider,
        model=model,
        item_count=item_count,
        embedding_dimension=preflight_dim,
        requested_batch_size=requested_batch_size,
        allow_low_memory=allow_low_memory,
    )

    embedder = _get_embedding_manager()
    actual_provider, actual_model = _embedding_manifest_identity(embedder)
    if not rebuild_dense and (actual_provider, actual_model) != (provider, model):
        raise RuntimeError("embedding manager identity changed while reusing dense vectors")

    _embed_and_store(
        embedder,
        cursor,
        conn,
        doc_items,
        chunk_items,
        initial_batch_size=estimate.recommended_batch_size,
        limits=embedding_limits,
    )
    dense_row = cursor.execute(
        "SELECT COUNT(*), MIN(LENGTH(embedding)), MAX(LENGTH(embedding)) FROM chunk_embeddings"
    ).fetchone()
    dense_count, embedding_bytes, max_embedding_bytes = dense_row
    if dense_count and embedding_bytes != max_embedding_bytes:
        raise RuntimeError("dense chunk vectors have inconsistent dimensions")
    if dense_count and embedding_bytes and embedding_bytes % 4 == 0:
        embedding_dimension = embedding_bytes // 4
    elif dense_count == 0:
        try:
            dimension = embedder.dimension
            embedding_dimension = int(dimension() if callable(dimension) else dimension)
        except (AttributeError, TypeError, ValueError):
            embedding_dimension = 0
    else:
        cursor.execute("DELETE FROM dense_index_manifest")
        conn.commit()
        _maybe_vacuum(conn, to_delete, db_files)
        conn.commit()
        return

    cursor.executemany(
        "INSERT OR REPLACE INTO dense_index_manifest (manifest_key, manifest_value) VALUES (?, ?)",
        [
            ("schema_version", DENSE_INDEX_SCHEMA_VERSION),
            ("embedding_dimension", str(embedding_dimension)),
            ("chunk_count", str(dense_count)),
            ("embedding_provider", actual_provider),
            ("embedding_model", actual_model),
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
    *,
    initial_batch_size: int | None = None,
    limits: tuple[int, int] | None = None,
) -> None:
    """Embed document + chunk texts in adaptive batches and stream to the DB.

    Peak RAM is bounded by ``batch_size`` and by committing every
    ``POWER_EMBED_COMMIT_EVERY`` vectors so the SQLite WAL never buffers the
    whole vault (which previously spiked ZFS write interrupts). Batch size
    shrinks proactively when available RAM drops under pressure; only Python
    ``MemoryError`` triggers adaptive retries, which halve actual request
    slices down to one item. Other provider/protocol errors propagate, and an
    unrecoverable single-item ``MemoryError`` aborts the sync.
    """
    import struct

    if limits is None:
        limits = sync_memory.validated_embedding_limits()
    batch_limit = sync_memory.validate_positive_embedding_limit(
        "POWER_EMBED_BATCH_SIZE", limits[0], sync_memory.MAX_EMBED_BATCH_SIZE
    )
    commit_every = sync_memory.validate_positive_embedding_limit(
        "POWER_EMBED_COMMIT_EVERY", limits[1], sync_memory.MAX_EMBED_COMMIT_EVERY
    )
    active_batch_size = (
        min(batch_limit, max(1, initial_batch_size))
        if initial_batch_size is not None
        else batch_limit
    )
    items_since_commit = 0

    def _embed_retry(texts: list[str], bs: int) -> list[list[float]]:
        """Embed ``texts``, halving actual request slices only on MemoryError."""
        nonlocal active_batch_size
        cur = bs
        while cur >= 1:
            try:
                vectors: list[list[float]] = []
                for start in range(0, len(texts), cur):
                    request = texts[start : start + cur]
                    batch_vectors = cast(
                        "list[list[float]]", embedder.embed_batch(request, batch_size=cur)
                    )
                    if len(batch_vectors) != len(request):
                        raise ValueError("embedding_output_count_mismatch")
                    vectors.extend(batch_vectors)
                if cur < active_batch_size:
                    active_batch_size = cur
                return vectors
            except MemoryError:
                if cur == 1:
                    raise
                previous_size = cur
                next_size = max(1, cur // 2)
                cur = next_size
                logger.warning(
                    "Embedding allocation failed; shrinking actual request size from %d to %d",
                    previous_size,
                    next_size,
                )
        raise RuntimeError("embedding_retry_exhausted")  # pragma: no cover

    def _store_docs(items: list[tuple[str, str, float]], bs: int) -> int:
        texts = [t for _, t, _ in items]
        vecs = _embed_retry(texts, bs)
        for (rel_path, _, mtime), vec in zip(items, vecs, strict=True):
            blob = struct.pack(f"{len(vec)}f", *vec)
            cursor.execute(
                "INSERT OR REPLACE INTO doc_embeddings (rel_path, embedding, mtime) VALUES (?, ?, ?)",
                (rel_path, blob, mtime),
            )
            _commit_after_vector()
        return len(items)

    def _store_chunks(items: list[tuple[str, str, str, float]], bs: int) -> int:
        texts = [t for _, _, t, _ in items]
        vecs = _embed_retry(texts, bs)
        for (chunk_id, rel_path, chunk_content, mtime), vec in zip(items, vecs, strict=True):
            blob = struct.pack(f"{len(vec)}f", *vec)
            cursor.execute(
                "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime) VALUES (?, ?, ?, ?, ?)",
                (chunk_id, rel_path, blob, chunk_content, mtime),
            )
            _commit_after_vector()
        return len(items)

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
    processed = 0
    written = 0
    started_at = time.monotonic()
    last_progress_log = started_at
    items_since_progress_log = 0
    first_batch = True

    def _maybe_shrink_for_pressure() -> None:
        nonlocal active_batch_size
        if active_batch_size <= 1:
            return
        avail = sync_memory.available_memory_bytes()
        if sync_memory.should_shrink_batch_under_pressure(avail):
            next_bs = max(1, active_batch_size // 2)
            logger.warning(
                "Memory pressure detected (available=%d MiB) — shrinking batch size %d -> %d",
                max(0, (avail or 0) // (1024 * 1024)),
                active_batch_size,
                next_bs,
            )
            active_batch_size = next_bs

    def _maybe_log_progress(*, final: bool = False) -> None:
        nonlocal last_progress_log, items_since_progress_log, first_batch
        if total == 0:
            return
        now = time.monotonic()
        if not (
            first_batch
            or final
            or items_since_progress_log >= commit_every
            or (now - last_progress_log) >= 5.0
        ):
            return
        elapsed = max(0.001, now - started_at)
        remaining = max(0, total - processed)
        rate = processed / elapsed if processed > 0 else 0.0
        eta = (remaining / rate) if rate > 0 else 0.0
        logger.info(
            "Embedding progress: %d/%d (%.1f%%) batch_size=%d elapsed=%.1fs eta=%.1fs",
            processed,
            total,
            (processed / total) * 100.0,
            active_batch_size,
            elapsed,
            eta,
        )
        first_batch = False
        last_progress_log = now
        items_since_progress_log = 0

    def _commit_after_vector() -> None:
        nonlocal items_since_commit
        items_since_commit += 1
        if items_since_commit == commit_every:
            _safe_commit()
            items_since_commit = 0

    def _run_queue(queue_items: list[Any], store_fn: Any) -> None:
        nonlocal processed, written, items_since_progress_log
        idx = 0
        while idx < len(queue_items):
            if processed > 0:
                _maybe_shrink_for_pressure()
            batch = queue_items[idx : idx + active_batch_size]
            written += store_fn(batch, active_batch_size)
            idx += len(batch)
            processed += len(batch)
            items_since_progress_log += len(batch)
            _maybe_log_progress(final=processed >= total)

    _run_queue(doc_items, _store_docs)
    _run_queue(chunk_items, _store_chunks)
    if items_since_commit > 0:
        _safe_commit()
    logger.info("Embedding pass complete: %d vector(s) written", written)
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
