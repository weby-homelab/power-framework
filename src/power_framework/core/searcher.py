"""
P.O.W.E.R. Full-Text Search Engine.

SQLite FTS5-powered search across vault notes with ranked results,
context snippets, and metadata-aware scoring.
"""

from __future__ import annotations

import re
import sqlite3
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
    """Split text into lowercase tokens (kept for backward compatibility)."""
    return re.findall(r"[a-z0-9а-яєіїґ']+", text.lower())  # noqa: RUF001


def _make_snippet(content: str, terms: list[str]) -> str:
    """Extract a relevant snippet around the first match (kept for backward compatibility)."""
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
    """Score a single note against search terms (kept for backward compatibility)."""
    total_score = 0.0
    total_matches = 0

    title_lower = metadata.title.lower()
    desc_lower = metadata.description.lower()
    content_lower = content.lower()
    tags_lower = [t.lower() for t in metadata.tags]

    for term in terms:
        term_lower = term.lower()

        # Title match
        title_count = title_lower.count(term_lower)
        if title_count:
            total_score += title_count * TITLE_WEIGHT
            total_matches += title_count

        # Tag match
        tag_count = sum(1 for t in tags_lower if term_lower in t)
        if tag_count:
            total_score += tag_count * TAG_WEIGHT
            total_matches += tag_count

        # Description match
        desc_count = desc_lower.count(term_lower)
        if desc_count:
            total_score += desc_count * DESCRIPTION_WEIGHT
            total_matches += desc_count

        # Body content match
        body_count = content_lower.count(term_lower)
        if body_count:
            total_score += body_count * CONTENT_WEIGHT
            total_matches += body_count

    snippet = _make_snippet(content, terms) if total_matches > 0 else ""
    return total_score, total_matches, snippet


def _scan_and_search(vault_dir: Path, terms: list[str]) -> list[SearchResult]:
    """Scan vault and return scored search results (kept for backward compatibility / fallback)."""
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
    # 1. Get all markdown files in the vault
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

    # 2. Get files from the database
    cursor = conn.cursor()
    cursor.execute("SELECT rel_path, mtime FROM file_metadata")
    db_files = {row[0]: row[1] for row in cursor.fetchall()}

    # 3. Find files to delete
    to_delete = [rel_path for rel_path in db_files if rel_path not in disk_files]
    if to_delete:
        cursor.executemany("DELETE FROM fts_notes WHERE rel_path = ?", [(r,) for r in to_delete])
        cursor.executemany(
            "DELETE FROM file_metadata WHERE rel_path = ?", [(r,) for r in to_delete]
        )

    # 4. Find files to insert or update
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

                # Delete existing just in case
                cursor.execute("DELETE FROM fts_notes WHERE rel_path = ?", (rel_path,))

                # Insert new fts note
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


def search_vault(vault_dir: Path, query: str, max_results: int = 20) -> list[SearchResult]:
    """
    Search the vault for notes matching the query using SQLite FTS5.

    Supports:
    - Multi-word queries
    - Phrase matching via double quotes
    - Prefix wildcard matching
    - Ranked results sorted by weighted relevance score
    """
    if not query or not query.strip():
        return []

    vault_dir = Path(vault_dir).resolve()
    if not vault_dir.is_dir():
        return []

    # Clean query and tokenize for FTS5 syntax
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
            match_count = 1  # FTS5 matches are ranked by score, match_count is 1 as fallback
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
        # Fallback to in-memory search if SQLite fails
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


def format_search_results(results: list[SearchResult], query: str) -> str:
    """Format search results into a human-readable report string."""
    if not results:
        return f"No results found for '{query}'."

    lines = [
        f"=== Search Results for '{query}' ===",
        f"Found {len(results)} matching note(s):",
        "",
    ]

    for i, r in enumerate(results, 1):
        score_str = f"{r.score:.1f}"
        lines.append(f"{i}. [{r.note_type}] {r.title}  (score: {score_str})")
        lines.append(f"   Path: {r.rel_path}")
        lines.append(f"   {r.description}")
        if r.snippet:
            lines.append(f"   ...{r.snippet}...")
        lines.append("")

    return "\n".join(lines)
