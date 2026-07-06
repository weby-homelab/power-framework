"""
P.O.W.E.R. Search Engine.

Multi-mode search across vault notes:
- "fts": SQLite FTS5 full-text search with weighted scoring (default)
- "vector": TF-vector cosine similarity for semantic-like ranking
- "hybrid": Reciprocal Rank Fusion merge of FTS + vector results
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .models import OKFMetadata  # noqa: TC001
from .parser import read_file_content, validate_metadata
from .utils import EXCLUDED_DIRS

SNIPPET_WINDOW = 40
MAX_SNIPPET_LENGTH = 120
TITLE_WEIGHT = 10.0
TAG_WEIGHT = 5.0
DESCRIPTION_WEIGHT = 3.0
CONTENT_WEIGHT = 1.0


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
        if any(part in EXCLUDED_DIRS for part in filepath.relative_to(vault_dir).parts):
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


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize the SQLite database schema."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_notes USING fts5(
            title,
            tags,
            description,
            content,
            rel_path UNINDEXED,
            note_type UNINDEXED,
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata (
            rel_path TEXT PRIMARY KEY,
            mtime REAL
        )
    """)
    conn.commit()


def _sync_vault_to_db(vault_dir: Path, conn: sqlite3.Connection) -> None:
    """Synchronize the files in the vault with the SQLite database."""
    disk_files: dict[str, float] = {}
    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue
        rel_parts = filepath.relative_to(vault_dir).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue

        try:
            rel_path = str(filepath.relative_to(vault_dir))
            mtime = filepath.stat().st_mtime
            disk_files[rel_path] = mtime
        except Exception:  # noqa: S112
            continue

    cursor = conn.cursor()
    cursor.execute("SELECT rel_path, mtime FROM file_metadata")
    db_files = {row[0]: row[1] for row in cursor.fetchall()}

    to_delete = [rel_path for rel_path in db_files if rel_path not in disk_files]
    if to_delete:
        cursor.executemany("DELETE FROM fts_notes WHERE rel_path = ?", [(r,) for r in to_delete])
        cursor.executemany(
            "DELETE FROM file_metadata WHERE rel_path = ?", [(r,) for r in to_delete]
        )

    for rel_path, mtime in disk_files.items():
        if rel_path not in db_files or db_files[rel_path] != mtime:
            filepath = vault_dir / rel_path
            try:
                content = read_file_content(filepath)
                metadata = validate_metadata(content)
                if metadata is None:
                    cursor.execute("DELETE FROM fts_notes WHERE rel_path = ?", (rel_path,))
                    cursor.execute("DELETE FROM file_metadata WHERE rel_path = ?", (rel_path,))
                    continue

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
            except Exception:  # noqa: S112
                continue

    conn.commit()


def _fts_search(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
) -> list[SearchResult]:
    """SQLite FTS5 full-text search with weighted BM25 scoring."""
    clean_query = re.sub(r'[^\w\s"а-яєіїґ\']', " ", query, flags=re.IGNORECASE)  # noqa: RUF001
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

    db_path = vault_dir / ".power_search.db"

    try:
        conn = sqlite3.connect(db_path)
        _init_db(conn)
        _sync_vault_to_db(vault_dir, conn)

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

    Computes a term-frequency vector for the query and each document,
    then ranks by cosine similarity.  Pure-Python, no external deps.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_vec = _compute_tf_vector(query_tokens)
    scored: list[tuple[float, SearchResult]] = []

    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue
        if any(part in EXCLUDED_DIRS for part in filepath.relative_to(vault_dir).parts):
            continue

        try:
            content = read_file_content(filepath)
            metadata = validate_metadata(content)
            if metadata is None:
                continue

            full_text = " ".join(
                [
                    metadata.title,
                    " ".join(metadata.tags),
                    metadata.description,
                    content,
                ]
            )
            doc_tokens = _tokenize(full_text)
            doc_vec = _compute_tf_vector(doc_tokens)
            similarity = _cosine_similarity(query_vec, doc_vec)

            if similarity == 0:
                continue

            rel_path = str(filepath.relative_to(vault_dir))
            snippet = _make_snippet(content, query_tokens)
            scored.append(
                (
                    similarity,
                    SearchResult(
                        rel_path=rel_path,
                        title=metadata.title,
                        description=metadata.description,
                        note_type=metadata.type,
                        score=similarity,
                        snippet=snippet,
                        match_count=len(query_tokens),
                        tags=metadata.tags,
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


def search_vault(
    vault_dir: Path,
    query: str,
    max_results: int = 20,
    mode: str = "fts",
) -> list[SearchResult]:
    """
    Search the vault for notes matching the query.

    Args:
        vault_dir: Path to the vault root directory.
        query: Search query string.
        max_results: Maximum number of results to return.
        mode: Search mode - "fts" (SQLite FTS5, default),
              "vector" (TF cosine similarity),
              "hybrid" (RRF merge of FTS + vector).

    Returns:
        List of SearchResult sorted by relevance (highest first).
    """
    if not query or not query.strip():
        return []

    vault_dir = Path(vault_dir).resolve()
    if not vault_dir.is_dir():
        return []

    mode = mode.lower()

    if mode == "vector":
        return _vector_search(vault_dir, query, max_results=max_results)

    if mode == "hybrid":
        fts_results = _fts_search(vault_dir, query, max_results=max_results * 2)
        vector_results = _vector_search(vault_dir, query, max_results=max_results * 2)
        return _rrf_merge(fts_results, vector_results)[:max_results]

    return _fts_search(vault_dir, query, max_results=max_results)


def format_search_results(results: list[SearchResult], query: str, mode: str = "fts") -> str:
    """Format search results into a human-readable report string."""
    if not results:
        return f"No results found for '{query}'."

    mode_label = {"fts": "FTS", "vector": "Vector", "hybrid": "Hybrid (FTS+Vector)"}.get(
        mode.lower(), mode.upper()
    )

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

    return "\n".join(lines)
