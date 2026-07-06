"""
P.O.W.E.R. ROT Scoring — Content Dedup, Freshness, Link Rot, Usage Tracking.

Implements Track A2 (Smart ROT without embeddings):
  - ContentDedupDetector: TF-Vector cosine similarity for body content
  - FreshnessScorer: Type-based exponential decay
  - LinkRotChecker: HTTP HEAD checks for external URLs
  - UsageTracker: SQLite-based access counter
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from .parser import extract_frontmatter_raw, read_file_content
from .searcher import _compute_tf_vector, _cosine_similarity, _tokenize
from .utils import EXCLUDED_DIRS

CONTENT_DEDUP_THRESHOLD = 0.75

TYPE_HALF_LIFE_DAYS: dict[str, int] = {
    "Daily Log": 30,
    "Project": 180,
    "Area": 365,
    "Resource": 365,
    "System Guide": 365,
    "Archive": 730,
}

DEFAULT_HALF_LIFE_DAYS = 180


class ContentDedupDetector:
    """Detect content-level duplicates using TF-Vector cosine similarity."""

    def __init__(self, threshold: float = CONTENT_DEDUP_THRESHOLD):
        self.threshold = threshold

    def detect(
        self,
        vault_dir: Path,
    ) -> list[tuple[str, str, float]]:
        """
        Find content-duplicate note pairs using TF-Vector cosine similarity.

        Returns list of (path_a, path_b, similarity_score).
        Lower than threshold = not reported.
        """
        notes: dict[str, dict[str, float]] = {}
        paths: list[str] = []
        dedup_pairs: list[tuple[str, str, float]] = []
        checked: set[tuple[str, str]] = set()

        for filepath in vault_dir.rglob("*.md"):
            rel = filepath.relative_to(vault_dir)
            if any(part in EXCLUDED_DIRS for part in rel.parts):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception:
                logging.exception("Failed to read %s", filepath)
                continue

            body = self._get_body(content)
            tokens = _tokenize(body)
            if len(tokens) < 20:
                continue

            vec = _compute_tf_vector(tokens)
            rel_path = str(rel)
            notes[rel_path] = vec
            paths.append(rel_path)

        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = paths[i], paths[j]
                pair = (a, b) if a < b else (b, a)
                if pair in checked:
                    continue
                checked.add(pair)
                sim = _cosine_similarity(notes[a], notes[b])
                if sim >= self.threshold:
                    dedup_pairs.append((a, b, sim))

        dedup_pairs.sort(key=lambda x: (-x[2], x[0], x[1]))
        return dedup_pairs

    @staticmethod
    def _get_body(content: str) -> str:
        """Extract body content, stripping frontmatter."""
        raw = extract_frontmatter_raw(content)
        if raw is not None:
            return content[content.index("---", 3 if content[3] == "\n" else 4) + 4 :].strip()
        return content.strip()


class FreshnessScorer:
    """Compute freshness scores based on note type and last modified timestamp."""

    def score_all(self, vault_dir: Path) -> dict[str, float]:
        """
        Score all notes in vault by freshness (0.0 = stale, 1.0 = fresh).

        Uses exponential decay: score = 2^(-age_days / half_life_days)
        """
        from .parser import parse_frontmatter

        now = datetime.now(timezone.utc)
        scores: dict[str, float] = {}

        for filepath in vault_dir.rglob("*.md"):
            rel = filepath.relative_to(vault_dir)
            if any(part in EXCLUDED_DIRS for part in rel.parts):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception:
                logging.exception("Failed to read %s", filepath)
                continue

            fm = parse_frontmatter(content)
            if fm is None:
                continue

            note_type = str(fm.get("type", ""))
            ts = fm.get("timestamp")

            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (now - ts).total_seconds() / 86400.0
            else:
                age = 0.0

            half_life = TYPE_HALF_LIFE_DAYS.get(note_type, DEFAULT_HALF_LIFE_DAYS)
            score = 2.0 ** (-age / half_life) if half_life > 0 else 1.0
            scores[str(rel)] = round(min(1.0, max(0.0, score)), 4)

        return scores


class LinkRotChecker:
    """Check external links for HTTP health via HEAD requests."""

    EXTERNAL_LINK_PATTERN = re.compile(r"\[.*?\]\((https?://[^\s)]+)\)")

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def check_all(self, vault_dir: Path) -> dict[str, list[tuple[str, int]]]:
        """
        Check all external links in vault notes.

        Returns dict: rel_path -> list of (url, status_code)
        Only includes broken links (status >= 400 or connection error).
        """
        results: dict[str, list[tuple[str, int]]] = {}

        for filepath in vault_dir.rglob("*.md"):
            rel = filepath.relative_to(vault_dir)
            if any(part in EXCLUDED_DIRS for part in rel.parts):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception:
                logging.exception("Failed to read %s", filepath)
                continue

            urls = self.EXTERNAL_LINK_PATTERN.findall(content)
            if not urls:
                continue

            broken: list[tuple[str, int]] = []
            for url in urls:
                status = self._head_status(url)
                if status >= 400 or status == -1:
                    broken.append((url, status))

            if broken:
                results[str(rel)] = broken

        return results

    def _head_status(self, url: str) -> int:
        """Perform HTTP HEAD request and return status code. Returns -1 on error."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return -1
        try:
            req = urllib.request.Request(url, method="HEAD")  # noqa: S310
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                return int(resp.status)  # type: ignore[no-any-return]
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return -1


class UsageTracker:
    """SQLite-based access counter for vault notes."""

    def __init__(self, vault_dir: Path):
        self.db_path = vault_dir / ".power_usage.db"
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS note_usage (
                    rel_path TEXT PRIMARY KEY,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT
                )
            """)
            conn.commit()
            conn.close()

    def track_access(self, rel_path: str) -> None:
        """Increment access counter for a note."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT INTO note_usage (rel_path, access_count, last_accessed)
                   VALUES (?, 1, ?)
                   ON CONFLICT(rel_path) DO UPDATE SET
                       access_count = access_count + 1,
                       last_accessed = ?""",
                (rel_path, now, now),
            )
            conn.commit()
            conn.close()

    def get_count(self, rel_path: str) -> int:
        """Get access count for a note."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT access_count FROM note_usage WHERE rel_path = ?",
                (rel_path,),
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else 0

    def get_all_counts(self) -> dict[str, int]:
        """Get access counts for all tracked notes."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT rel_path, access_count FROM note_usage")
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return counts

    def get_all_usage(self) -> dict[str, dict]:
        """Get full usage data for all tracked notes."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT rel_path, access_count, last_accessed FROM note_usage ORDER BY access_count DESC"
            )
            data = {
                row[0]: {
                    "access_count": row[1],
                    "last_accessed": row[2],
                }
                for row in cursor.fetchall()
            }
            conn.close()
            return data
