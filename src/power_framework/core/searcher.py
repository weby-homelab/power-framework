"""
P.O.W.E.R. Search Engine.

Multi-mode search across vault notes:
- "fts": SQLite FTS5 full-text search with weighted scoring (default)
- "vector": TF-vector cosine similarity for semantic-like ranking
- "hybrid": Reciprocal Rank Fusion merge of FTS + vector results
- "semantic": Dense embedding cosine similarity via fastembed
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .chunker import SemanticChunker
from .db import _init_db
from .embeddings import get_embedding_manager
from .ignore import should_skip
from .index_worker import request_sync, set_vault_dir
from .models import OKFMetadata  # noqa: TC001
from .parser import read_file_content, validate_metadata
from .query_expansion import QueryExpander
from .reranker import RerankerManager
from .utils import get_cache_dir

logger = logging.getLogger(__name__)

# Module-level cross-encoder reranker singleton. The fastembed/qwen3 cross-encoder
# model is expensive to load (~seconds); constructing a fresh RerankerManager per
# query (as the old code did) reloaded the model on every call, inflating
# hybrid_reranked latency to 5-40s per query. Caching it here keeps the model
# resident across queries within a process.
_reranker_singleton: object | None = None


def _get_reranker():
    """Return the active reranker (cached), falling back Jina <- ColBERT if needed.

    POWER 3.0 Phase 3: ColBERT is opt-in; if it is requested but unavailable we
    transparently fall back to the canonical Jina v2 cross-encoder so search
    never breaks on a misconfigured host.
    """
    global _reranker_singleton
    if _reranker_singleton is None:
        from .reranker import get_reranker

        try:
            _reranker_singleton = get_reranker()
        except Exception as e:  # noqa: BLE001
            logger.warning("Reranker init failed (%s); retrying with Jina v2 default.", e)
            from .reranker import RerankerManager

            _reranker_singleton = RerankerManager()
    return _reranker_singleton


def _db_path() -> Path:
    """Resolve the search index DB path, honoring POWER_SEARCH_DB override.

    Tests set POWER_SEARCH_DB to an isolated temp file so the shared
    ``~/.cache/power-framework/power_search.db`` is not cross-contaminated
    between test cases.
    """
    import os

    override = os.getenv("POWER_SEARCH_DB")
    if override:
        return Path(override)
    return get_cache_dir() / "power_search.db"


SNIPPET_WINDOW = 40
MAX_SNIPPET_LENGTH = 120
TITLE_WEIGHT = 10.0
TAG_WEIGHT = 5.0
DESCRIPTION_WEIGHT = 3.0
CONTENT_WEIGHT = 1.0
# Max candidates passed to the cross-encoder reranker (Performance Plan §4).
RERANK_CANDIDATE_LIMIT = 20
# Max characters of each candidate doc fed to the reranker (truncated excerpt).
# Keeps cross-encoder token cost bounded on CPU (Performance Plan §4).
RERANK_TEXT_CHARS = 800


@dataclass
class SearchResult:
    """A single search result with relevance info."""

    rel_path: str
    title: str
    description: str
    note_type: str
    score: float
    snippet: str
    match_count: int
    tags: list[str] = field(default_factory=list)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens."""
    return re.findall(r"[a-z0-9а-яєіїґ']+", text.lower())  # noqa: RUF001


def _make_snippet(content: str, terms: list[str]) -> str:
    """Extract a relevant snippet around the first match."""
    lower = content.lower()
    best_pos = -1
    for term in terms:
        pos = lower.find(term.lower())
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        return content[: SNIPPET_WINDOW * 2].strip()

    start = max(0, best_pos - SNIPPET_WINDOW)
    end = min(len(content), best_pos + SNIPPET_WINDOW)

    snippet = content[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    if len(snippet) > MAX_SNIPPET_LENGTH:
        snippet = snippet[:MAX_SNIPPET_LENGTH] + "..."

    return snippet


def _score_note(
    content: str,
    metadata: OKFMetadata,
    terms: list[str],
) -> tuple[float, int, str]:
    """Score a single note against search terms (backward compat / fallback)."""
    total_score = 0.0
    total_matches = 0

    title_lower = metadata.title.lower()
    desc_lower = metadata.description.lower()
    content_lower = content.lower()
    tags_lower = [t.lower() for t in metadata.tags]

    for term in terms:
        term_lower = term.lower()

        title_count = title_lower.count(term_lower)
        if title_count:
            total_score += title_count * TITLE_WEIGHT
            total_matches += title_count

        tag_count = sum(1 for t in tags_lower if term_lower in t)
        if tag_count:
            total_score += tag_count * TAG_WEIGHT
            total_matches += tag_count

        desc_count = desc_lower.count(term_lower)
        if desc_count:
            total_score += desc_count * DESCRIPTION_WEIGHT
            total_matches += desc_count

        body_count = content_lower.count(term_lower)
        if body_count:
            total_score += body_count * CONTENT_WEIGHT
            total_matches += body_count

    snippet = _make_snippet(content, terms) if total_matches > 0 else ""
    return total_score, total_matches, snippet


def _scan_and_search(vault_dir: Path, terms: list[str]) -> list[SearchResult]:
    """Scan vault and return scored search results (fallback)."""
    results: list[SearchResult] = []

    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue
        if should_skip(vault_dir, str(filepath.relative_to(vault_dir))):
            continue

        try:
            content = read_file_content(filepath)
            metadata = validate_metadata(content)
            if metadata is None:
                continue

            score, match_count, snippet = _score_note(content, metadata, terms)
            if score == 0:
                continue

            rel_path = str(filepath.relative_to(vault_dir))
            results.append(
                SearchResult(
                    rel_path=rel_path,
                    title=metadata.title,
                    description=metadata.description,
                    note_type=metadata.type,
                    score=score,
                    snippet=snippet,
                    match_count=match_count,
                    tags=metadata.tags,
                )
            )
        except Exception:  # noqa: S112
            continue

    return results


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
    import json

    cursor = conn.cursor()
    if force_rebuild and sync_embeddings:
        logger.info("Force rebuild: clearing dense-embedding tables ...")
        cursor.execute("DELETE FROM doc_embeddings")
        cursor.execute("DELETE FROM chunk_embeddings")
        conn.commit()

    disk_files: dict[str, float] = {}
    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue
        if should_skip(vault_dir, str(filepath.relative_to(vault_dir))):
            continue

        try:
            rel_path = str(filepath.relative_to(vault_dir))
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

    embedder = get_embedding_manager() if sync_embeddings else None

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
    for idx, (rel_path, mtime) in enumerate(disk_files.items()):
        if idx % 50 == 0:
            logger.info("Sync scan: %d/%d (%s)", idx, len(disk_files), rel_path)
        if rel_path not in db_files or db_files[rel_path] != mtime:
            filepath = vault_dir / rel_path
            try:
                content = read_file_content(filepath)
                metadata = validate_metadata(content)
                if metadata is None:
                    cursor.execute("DELETE FROM fts_notes WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM file_metadata WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM doc_embeddings WHERE rel_path = ?", (rel_path,))
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

            full_text = " ".join(
                [metadata.title, " ".join(metadata.tags), metadata.description, content]
            )
            tokens = _tokenize(full_text)
            tf_vec = _compute_tf_vector(tokens)
            cursor.execute(
                "INSERT OR REPLACE INTO tf_vectors (rel_path, tf_data, mtime) VALUES (?, ?, ?)",
                (rel_path, json.dumps(tf_vec), mtime),
            )
        except Exception as e:  # noqa: PERF203
            logger.warning("FTS/TF write failed for %s: %s", rel_path, e)
            continue
    conn.commit()

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
            for i, chunk_text in enumerate(chunks):
                chunk_items.append((f"{rel_path}::chunk_{i}", rel_path, chunk_text, mtime))
        except Exception as e:  # noqa: PERF203
            logger.warning("Chunk prep failed for %s: %s", rel_path, e)
            continue

    _embed_and_store(embedder, cursor, conn, doc_items, chunk_items)
    _maybe_vacuum(conn, to_delete, db_files)


def _embed_and_store(embedder, cursor, conn, doc_items, chunk_items) -> None:
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
                return embedder.embed_batch(texts, batch_size=cur)
            except Exception as e:  # noqa: PERF203
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
        for (chunk_id, rel_path, _, mtime), vec in zip(items, vecs, strict=True):
            blob = struct.pack(f"{len(vec)}f", *vec)
            cursor.execute(
                "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime) VALUES (?, ?, ?, ?, ?)",
                (chunk_id, rel_path, blob, _, mtime),
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
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
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


def _maybe_vacuum(conn, to_delete, db_files) -> None:
    # Performance Plan §2: do NOT run VACUUM on every sync (it rebuilds the
    # whole DB and blocks writers). Only vacuum when a meaningful fraction of
    # rows were deleted (significant churn), otherwise leave free pages for
    # incremental reuse.
    if to_delete and len(to_delete) >= max(10, len(db_files) // 10):
        try:
            conn.execute("PRAGMA incremental_vacuum")
        except Exception as e:  # pragma: no cover
            logger.debug("incremental_vacuum failed: %s", e)


def _fts_search(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
) -> list[SearchResult]:
    """SQLite FTS5 full-text search with weighted BM25 scoring."""
    clean_query = re.sub(
        r'[^\w\s"а-яєіїґ\']',  # noqa: RUF001
        " ",
        query,
        flags=re.IGNORECASE,
    )
    terms: list[str] = []
    for match in re.finditer(r'"([^"]+)"|(\S+)', clean_query):
        phrase = match.group(1)
        word = match.group(2)
        if phrase:
            terms.append(f'"{phrase.strip()}"')
        elif word:
            terms.append(f"{word.strip()}*")

    fts_query = " AND ".join(terms) if terms else ""
    if not fts_query:
        return []

    db_path = _db_path()

    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        _init_db(conn)

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                rel_path,
                title,
                description,
                note_type,
                -bm25(fts_notes, 10.0, 5.0, 3.0, 1.0) as score,
                snippet(fts_notes, 3, '...', '...', '...', 15) as snippet_text,
                tags
            FROM fts_notes
            WHERE fts_notes MATCH ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (fts_query, max_results),
        )

        results: list[SearchResult] = []
        for row in cursor.fetchall():
            rel_path, title, description, note_type, score, snippet, tags_str = row
            tags = tags_str.split(" ") if tags_str else []
            match_count = 1
            results.append(
                SearchResult(
                    rel_path=rel_path,
                    title=title,
                    description=description,
                    note_type=note_type,
                    score=float(score),
                    snippet=snippet,
                    match_count=match_count,
                    tags=tags,
                )
            )

        conn.close()
        return results
    except Exception:
        terms_fallback: list[str] = []
        for match in re.finditer(r'"([^"]+)"|(\S+)', query.strip()):
            term = (match.group(1) or match.group(2)).strip().lower()
            if term:
                terms_fallback.append(term)
        if not terms_fallback:
            return []
        fallback_results = _scan_and_search(vault_dir, terms_fallback)
        fallback_results.sort(key=lambda r: (-r.score, -r.match_count, r.title))
        return fallback_results[:max_results]


def _compute_tf_vector(tokens: list[str]) -> dict[str, float]:
    """Compute a normalized term-frequency vector from tokens."""
    counter = Counter(tokens)
    total = len(tokens) or 1
    return {word: count / total for word, count in counter.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse term-frequency vectors."""
    intersection = set(vec_a) & set(vec_b)
    if not intersection:
        return 0.0
    dot_product = sum(vec_a[word] * vec_b[word] for word in intersection)
    norm_a = sum(v * v for v in vec_a.values()) ** 0.5
    norm_b = sum(v * v for v in vec_b.values()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


def _vector_search(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
) -> list[SearchResult]:
    """
    Search vault notes using TF vector cosine similarity.

    Loads pre-computed term-frequency vectors from SQLite,
    then ranks by cosine similarity.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_vec = _compute_tf_vector(query_tokens)
    db_path = _db_path()

    import json

    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        _init_db(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tf_vectors")
        if cursor.fetchone()[0] == 0:
            # Materialize TF vectors (cheap FTS-only sync) so direct
            # _vector_search calls work even before an explicit index.
            _sync_vault_to_db(vault_dir, conn, sync_embeddings=False)

        cursor.execute("""
            SELECT t.rel_path, t.tf_data, f.title, f.description, f.note_type, f.tags, f.content
            FROM tf_vectors t
            JOIN fts_notes f ON t.rel_path = f.rel_path
        """)
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return []

    scored: list[tuple[float, SearchResult]] = []

    for rel_path, tf_data_str, title, description, note_type, tags_str, content in rows:
        try:
            filepath = vault_dir / rel_path
            if not filepath.is_file():
                continue
            if should_skip(vault_dir, rel_path):
                continue

            doc_vec = json.loads(tf_data_str)
            similarity = _cosine_similarity(query_vec, doc_vec)

            if similarity == 0:
                continue

            tags = tags_str.split(" ") if tags_str else []
            snippet = _make_snippet(content, query_tokens)
            scored.append(
                (
                    similarity,
                    SearchResult(
                        rel_path=rel_path,
                        title=title,
                        description=description,
                        note_type=note_type,
                        score=similarity,
                        snippet=snippet,
                        match_count=len(query_tokens),
                        tags=tags,
                    ),
                )
            )
        except Exception:  # noqa: S112
            continue

    scored.sort(key=lambda x: (-x[0], x[1].title))
    return [r for _, r in scored[:max_results]]


def _rrf_merge(
    fts_results: list[SearchResult],
    vector_results: list[SearchResult],
    k: int = 60,
) -> list[SearchResult]:
    """Merge two ranked result lists using Reciprocal Rank Fusion."""
    rrf_scores: dict[str, float] = {}

    for rank, result in enumerate(fts_results):
        rrf_scores[result.rel_path] = 1.0 / (k + rank + 1)

    for rank, result in enumerate(vector_results):
        rrf_scores[result.rel_path] = rrf_scores.get(result.rel_path, 0.0) + 1.0 / (k + rank + 1)

    doc_map: dict[str, SearchResult] = {}
    for r in fts_results + vector_results:
        if r.rel_path not in doc_map or r.score > doc_map[r.rel_path].score:
            doc_map[r.rel_path] = r

    merged: list[SearchResult] = []
    for path, score in sorted(rrf_scores.items(), key=lambda x: -x[1]):
        result = doc_map[path]
        merged.append(
            SearchResult(
                rel_path=result.rel_path,
                title=result.title,
                description=result.description,
                note_type=result.note_type,
                score=score,
                snippet=result.snippet,
                match_count=result.match_count,
                tags=result.tags,
            )
        )

    return merged


def _semantic_search(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
) -> list[SearchResult]:
    """Search vault notes using dense embedding cosine similarity over chunks.

    Queries chunk_embeddings, groups by rel_path (taking the max similarity
    across its chunks), and populates the snippet with the best chunk's content.
    """
    if not query or not query.strip():
        return []

    db_path = _db_path()

    # B7/FP-7 (POWER 3.0 Sync-or-FTS-Fallback): NEVER return a silent [] when
    # the dense index is unavailable. If embeddings cannot be produced or the
    # chunk_embeddings table is empty/broken, degrade to FTS with an explicit
    # warning so callers get real results and operators see WHY dense was
    # skipped — instead of an empty list that looks like "no matches".
    def _fts_fallback(reason: str) -> list[SearchResult]:
        logger.warning(
            "Semantic search unavailable (%s); falling back to FTS for query %r",
            reason,
            query,
        )
        # Ensure the (cheap, no-model) FTS index exists so the fallback returns
        # real results even on a cold index — otherwise the "fallback" would
        # itself be a silent [] (defeats B7/FP-7).
        try:
            fconn = sqlite3.connect(str(db_path), timeout=30)
            fconn.execute("PRAGMA busy_timeout=30000")
            fconn.execute("PRAGMA journal_mode=WAL")
            _init_db(fconn)
            fcur = fconn.cursor()
            fcur.execute("SELECT COUNT(*) FROM file_metadata")
            if fcur.fetchone()[0] == 0:
                _sync_vault_to_db(vault_dir, fconn, sync_embeddings=False)
            fconn.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("FTS fallback index refresh failed: %s", e)
        return _fts_search(vault_dir, query, max_results=max_results)

    try:
        embedder = get_embedding_manager()
        query_vec = embedder.embed(query)
    except Exception as e:  # noqa: BLE001
        return _fts_fallback(f"embedder error: {type(e).__name__}")

    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        _init_db(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunk_embeddings")
        if cursor.fetchone()[0] == 0:
            # Embeddings are not materialized yet. Perform a synchronous
            # (one-time, batched) embedding sync so the query returns real
            # results. Batching inside _sync_vault_to_db bounds peak RAM.
            # Close our read connection first so the writer doesn't contend on
            # the same SQLite lock (avoids "database is locked" under load).
            logger.info("Semantic index empty; running synchronous embedding sync")
            conn.close()
            try:
                sync_conn = sqlite3.connect(str(db_path), timeout=60)
                sync_conn.execute("PRAGMA busy_timeout=60000")
                sync_conn.execute("PRAGMA journal_mode=WAL")
                _init_db(sync_conn)
                _sync_vault_to_db(vault_dir, sync_conn, sync_embeddings=True)
                sync_conn.close()
            except sqlite3.OperationalError as e:
                if "locked" in str(e):
                    return _fts_fallback("embedding sync deferred (db locked)")
                # disk I/O error or similar: the dense index is unusable this
                # call — fall back rather than raising into a silent [].
                return _fts_fallback(f"embedding sync failed: {e}")
            conn = sqlite3.connect(str(db_path), timeout=60)
            conn.execute("PRAGMA busy_timeout=60000")
            conn.execute("PRAGMA journal_mode=WAL")
            _init_db(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT rel_path, embedding, content FROM chunk_embeddings")
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:  # noqa: BLE001
        return _fts_fallback(f"db error: {type(e).__name__}")

    if not rows:
        # Sync ran but produced no chunk_embeddings (e.g. every batch skipped
        # under memory pressure). Fall back to FTS instead of silent [].
        return _fts_fallback("no dense vectors after sync")

    import numpy as np

    q_arr = np.asarray(query_vec, dtype=np.float32)
    q_norm = float(np.linalg.norm(q_arr))
    if q_norm == 0:
        # Zero query vector = broken/degenerate embedding. Don't return a silent
        # [] — degrade to FTS (B7/FP-7).
        return _fts_fallback("zero query embedding")

    chunk_scores: list[tuple[float, str, str]] = []
    for rel_path, blob, content in rows:
        try:
            dim = len(blob) // 4
            chunk_vec = np.frombuffer(blob, dtype=np.float32)
            if chunk_vec.shape[0] != dim:
                continue
        except Exception:  # noqa: S112
            continue

        # Vectorized cosine similarity (Performance Plan §5): one dot + norm
        # instead of a Python loop over every dimension.
        d_norm = float(np.linalg.norm(chunk_vec))
        if d_norm == 0:
            continue
        similarity = float(np.dot(q_arr, chunk_vec) / (q_norm * d_norm))
        if similarity <= 0:
            continue
        chunk_scores.append((similarity, rel_path, content))

    if not chunk_scores:
        # Dense index present but nothing scored positive for this query (a
        # classic symptom of a dead cross-lingual embedder, e.g. Granite's
        # 0.000 UA↔EN recall). Fall back to FTS rather than a silent [] (B7).
        return _fts_fallback("no positive dense matches")

    doc_best: dict[str, tuple[float, str]] = {}
    for similarity, rel_path, content in chunk_scores:
        if rel_path not in doc_best or similarity > doc_best[rel_path][0]:
            doc_best[rel_path] = (similarity, content)

    scored_docs = sorted(doc_best.items(), key=lambda x: -x[1][0])
    top_paths = [rel for rel, _ in scored_docs[:max_results]]

    results: list[SearchResult] = []
    for rel_path in top_paths:
        filepath = vault_dir / rel_path
        try:
            content = read_file_content(filepath)
            metadata = validate_metadata(content)
            if metadata is None:
                continue
            similarity, snippet = doc_best[rel_path]
            results.append(
                SearchResult(
                    rel_path=rel_path,
                    title=metadata.title,
                    description=metadata.description,
                    note_type=metadata.type,
                    score=similarity,
                    snippet=snippet,
                    match_count=1,
                    tags=metadata.tags,
                )
            )
        except Exception:  # noqa: S112
            continue

    return results


def search_vault(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
    mode: str = "reranked",
) -> list[SearchResult]:
    """
    Search the vault for notes matching the query.

    Args:
        vault_dir: Path to the vault root directory.
        query: Search query string.
        max_results: Maximum number of results to return.
        mode: Search mode. POWER 3.0 canonical mode is "reranked" (default):
              FTS5/BM25 -> top-150 -> cross-encoder reranker (Jina v2) -> top-20,
              with a dense-embedding fallback only when FTS yields < 5 hits.
              Developer/debug modes: "fts" (BM25), "vector" (TF cosine),
              "hybrid" (RRF of FTS + vector), "semantic" (dense embedding),
              "hybrid_reranked" (alias of "reranked").

    Returns:
        List of SearchResult sorted by relevance (highest first).
    """
    # Defensive: callers (CLI, tests, external integrations) may pass a string
    # path; downstream code uses Path operators (vault_dir / rel_path), so
    # coerce to a resolved Path once here.
    vault_dir = Path(vault_dir).expanduser().resolve()

    # 1. Background indexer (Performance Plan §1): dense-embedding synchronization
    #    (the 176s cold-start root cause) is NO LONGER done synchronously here.
    #    We still run a lightweight FTS-only sync (cheap: no model load, <1s for
    #    hundreds of files) so FTS/vector/hybrid stay fresh, and enqueue a
    #    non-blocking background sync for embeddings when a semantic mode is
    #    requested. Staleness is reported via the coverage footer (§6).
    set_vault_dir(vault_dir)
    sync_emb = mode in ("semantic", "hybrid_reranked")
    if sync_emb:
        request_sync(vault_dir, mode="semantic")
    else:
        # Cheap synchronous FTS refresh ONLY when the index is empty/missing,
        # so non-semantic modes stay correct on first use without re-syncing
        # the whole vault on every query (Performance Plan §1). Incremental
        # mtime checks inside _sync_vault_to_db keep repeat calls near-free.
        try:
            conn = sqlite3.connect(str(_db_path()), timeout=30)
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            _init_db(conn)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM file_metadata")
            if cur.fetchone()[0] == 0:
                _sync_vault_to_db(vault_dir, conn, sync_embeddings=False)
            conn.close()
        except Exception as e:
            logger.warning("Session-level FTS sync failed: %s", e)

    expander = QueryExpander()
    variants = expander.expand(query)

    if mode == "hybrid":
        fts_all: list[SearchResult] = []
        vec_all: list[SearchResult] = []
        for variant in variants:
            fts_all.extend(_fts_search(vault_dir, variant, max_results=max_results * 2))
            vec_all.extend(_vector_search(vault_dir, variant, max_results=max_results * 2))

        # Deduplicate FTS by rel_path (keeping max score) and sort
        fts_map: dict[str, SearchResult] = {}
        for r in fts_all:
            if r.rel_path not in fts_map or r.score > fts_map[r.rel_path].score:
                fts_map[r.rel_path] = r
        fts_dedup = sorted(fts_map.values(), key=lambda x: -x.score)

        # Deduplicate Vector by rel_path (keeping max score) and sort
        vec_map: dict[str, SearchResult] = {}
        for r in vec_all:
            if r.rel_path not in vec_map or r.score > vec_map[r.rel_path].score:
                vec_map[r.rel_path] = r
        vec_dedup = sorted(vec_map.values(), key=lambda x: -x.score)

        # Single RRF fusion at the end
        return _rrf_merge(fts_dedup, vec_dedup)[:max_results]

    # For non-hybrid modes, gather results, dedup by rel_path keeping max score, and sort
    all_results: list[SearchResult] = []
    for variant in variants:
        if mode == "vector":
            results = _vector_search(vault_dir, variant, max_results=max_results)
        elif mode == "semantic":
            results = _semantic_search(vault_dir, variant, max_results=max_results)
        elif mode in ("reranked", "hybrid_reranked"):
            results = _hybrid_reranked_search(vault_dir, variant, max_results=max_results)
            # R5 (POWER 3.0): dense fallback ONLY when FTS/rerank yields too few
            # hits — keeps the canonical path cheap (no model load) for the common
            # case, but never silently returns a short list when the vault clearly
            # has relevant dense matches. This is the inverse of the old behavior
            # where semantic was the default and FTS was the fallback.
            if len(results) < 5:
                dense = _semantic_search(vault_dir, variant, max_results=max_results)
                _merge_by_rel_path(all_results, dense)
        else:
            results = _fts_search(vault_dir, variant, max_results=max_results)
        all_results.extend(results)

    res_map: dict[str, SearchResult] = {}
    for r in all_results:
        if r.rel_path not in res_map or r.score > res_map[r.rel_path].score:
            res_map[r.rel_path] = r

    final_results = sorted(res_map.values(), key=lambda x: (-x.score, x.title))
    return final_results[:max_results]


def _hybrid_reranked_search(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
) -> list[SearchResult]:
    """Canonical POWER 3.0 retrieval: FTS/BM25 -> top-150 -> Jina v2 rerank -> top-20.

    Implements the R5 canonical search mode. Broad FTS recall (top-150) is merged
    with TF-vector candidates via RRF, then a cross-encoder reranker (Jina v2
    multilingual) re-ranks the leading pool. The reranker is cached (singleton)
    so repeated queries stay fast.
    """
    candidates = _fts_search(vault_dir, query, max_results=150)
    vector_results = _vector_search(vault_dir, query, max_results=150)
    candidates = _rrf_merge(candidates, vector_results)

    if not candidates:
        return []

    # Performance Plan §4: bound the reranker to the top-K RRF candidates
    # (default 20) instead of reranking all 150 full-document texts, AND rerank
    # only the leading excerpt (truncated to RERANK_TEXT_CHARS) of each doc.
    # Cross-encoders on CPU are dominated by token count, so truncating slashes
    # latency ~10x with negligible nDCG loss (MAR@5 preserved).
    rerank_pool = candidates[: min(len(candidates), RERANK_CANDIDATE_LIMIT)]

    documents: list[str] = []
    for result in rerank_pool:
        filepath = vault_dir / result.rel_path
        try:
            content = read_file_content(filepath)
            documents.append(content[:RERANK_TEXT_CHARS])
        except Exception:
            documents.append("")

    reranker = _get_reranker()
    reranked_scores = reranker.rerank(query, documents)

    for result, score in zip(rerank_pool, reranked_scores, strict=False):
        result.score = score

    # Keep non-reranked tail (beyond the pool) with their RRF score so results
    # beyond the rerank limit still surface, just unsorted by the cross-encoder.
    reranked = rerank_pool[:]
    reranked.sort(key=lambda r: -r.score)
    tail = candidates[len(rerank_pool) :]
    return (reranked + tail)[:max_results]


def _merge_by_rel_path(target: list[SearchResult], incoming: list[SearchResult]) -> None:
    """Merge ``incoming`` into ``target``, keeping the highest score per rel_path."""
    seen: dict[str, float] = {r.rel_path: r.score for r in target}
    for r in incoming:
        if r.rel_path not in seen or r.score > seen[r.rel_path]:
            target.append(r)
            seen[r.rel_path] = r.score


def format_search_results(
    results: list[SearchResult],
    query: str,
    mode: str = "fts",
    vault_dir: Path | None = None,
) -> str:
    """Format search results into a human-readable report string.

    When ``vault_dir`` is provided, a coverage footer (Performance Plan §6)
    reports indexed / total file counts so callers can see staleness honestly.
    """
    if not results:
        return f"No results found for '{query}'."

    mode_label = {
        "fts": "FTS",
        "vector": "Vector",
        "hybrid": "Hybrid (FTS+Vector)",
        "semantic": "Semantic (Dense Embedding)",
        "hybrid_reranked": "Hybrid (RRF + Rerank)",
    }.get(mode.lower(), mode.upper())

    lines = [
        f"=== Search Results for '{query}' ===",
        f"Mode: {mode_label}  |  Found {len(results)} matching note(s):",
        "",
    ]

    for i, r in enumerate(results, 1):
        score_str = f"{r.score:.4f}"
        lines.append(f"{i}. [{r.note_type}] {r.title}  (score: {score_str})")
        lines.append(f"   Path: {r.rel_path}")
        lines.append(f"   {r.description}")
        if r.snippet:
            lines.append(f"   ...{r.snippet}...")
        lines.append("")

    if vault_dir is not None:
        from .index_worker import get_coverage

        try:
            indexed, total = get_coverage(vault_dir)
            pending = max(0, total - indexed)
            footer = f"Index coverage: {indexed}/{total}"
            if pending:
                footer += f"  (pending: {pending} — background indexing in progress)"
            lines.append(footer)
        except Exception:  # pragma: no cover
            logger.debug("coverage footer computation failed")

    return "\n".join(lines)
