"""
P.O.W.E.R. ROT Scoring — Content Dedup, Freshness, Link Rot, Usage Tracking.

Implements Track A2 (Smart ROT):
  - ContentDedupDetector: Dense embedding cosine similarity for body content
  - ContradictionDetector: Flags semantically similar pairs with contradictions
  - FreshnessScorer: Type-based exponential decay
  - LinkRotChecker: HTTP HEAD checks for external URLs
  - UsageTracker: SQLite-based access counter
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from power_framework.core.egress import (
    DEFAULT_LLM_API_BASE,
    EgressDeniedError,
    EgressOperation,
    configured_llm_origins,
    require_remote_egress,
    safe_http_request,
    validate_llm_endpoint,
)
from power_framework.core.ignore import should_skip
from power_framework.core.parser import FRONTMATTER_PATTERN, parse_frontmatter, read_file_content
from power_framework.core.utils import (
    get_cpu_worker_limit,
    is_regular_vault_file,
    iter_vault_markdown_files,
    run_opencode_cli,
)
from power_framework.experimental.embeddings import get_embedding_manager


class EmbeddingProvider(Protocol):
    """Minimal embedding contract consumed by semantic ROT detectors."""

    def embed(self, text: str) -> list[float]:
        """Return one deterministic vector for ``text``."""


logger = logging.getLogger(__name__)

CONTENT_DEDUP_THRESHOLD = 0.75
CONTRADICTION_SIMILARITY_THRESHOLD = 0.7
OPENROUTER_MODELS = [
    "openrouter/google/gemini-2.5-flash",
    "openrouter/qwen/qwen3.5-flash-02-23",
]

TYPE_HALF_LIFE_DAYS: dict[str, int] = {
    "Daily Log": 30,
    "Project": 180,
    "Area": 365,
    "Resource": 365,
    "System Guide": 365,
    "Archive": 730,
}

DEFAULT_HALF_LIFE_DAYS = 180


def _dense_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = sum(v * v for v in vec_a) ** 0.5
    norm_b = sum(v * v for v in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class ContentDedupDetector:
    """Detect content-level duplicates using dense embedding cosine similarity."""

    def __init__(
        self,
        threshold: float = CONTENT_DEDUP_THRESHOLD,
        embedder: EmbeddingProvider | None = None,
    ):
        self.threshold = threshold
        self.embedder = embedder or get_embedding_manager()

    def detect(
        self,
        vault_dir: Path,
    ) -> list[tuple[str, str, float]]:
        """
        Find content-duplicate note pairs using dense embedding cosine similarity.

        Returns list of (path_a, path_b, similarity_score).
        Lower than threshold = not reported.
        """
        notes: dict[str, list[float]] = {}
        paths: list[str] = []
        dedup_pairs: list[tuple[str, str, float]] = []
        checked: set[tuple[str, str]] = set()

        for filepath in iter_vault_markdown_files(vault_dir):
            rel = filepath.relative_to(vault_dir)
            if should_skip(vault_dir, rel.as_posix()):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception as exc:
                logger.debug("Cannot read %s: %s", filepath, exc)
                continue

            body = self._get_body(content)
            if len(body) < 50:
                continue

            rel_path = rel.as_posix()
            try:
                vec = self.embedder.embed(body)
            except Exception as exc:
                logger.debug("Cannot embed %s: %s", filepath, exc)
                continue

            notes[rel_path] = vec
            paths.append(rel_path)

        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = paths[i], paths[j]
                pair = (a, b) if a < b else (b, a)
                if pair in checked:
                    continue
                checked.add(pair)
                sim = _dense_cosine_similarity(notes[a], notes[b])
                if sim >= self.threshold:
                    dedup_pairs.append((a, b, sim))

        dedup_pairs.sort(key=lambda x: (-x[2], x[0], x[1]))
        return dedup_pairs

    @staticmethod
    def _get_body(content: str) -> str:
        """Extract body content, stripping frontmatter."""
        match = FRONTMATTER_PATTERN.match(content)
        if match:
            return content[match.end() :].strip()
        return content.strip()


class ContradictionDetector:
    """Find semantically similar note pairs that may contain contradictory facts."""

    def __init__(
        self,
        similarity_threshold: float = CONTRADICTION_SIMILARITY_THRESHOLD,
        api_key: str | None = None,
        embedder: EmbeddingProvider | None = None,
        allow_remote_llm: bool = False,
        sensitivity: str = "sensitive",
    ):
        self.similarity_threshold = similarity_threshold
        self.api_key = (
            api_key
            or os.environ.get("POWER_LLM_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY", "")
        )
        self.api_base = os.environ.get("POWER_LLM_API_BASE", DEFAULT_LLM_API_BASE).rstrip("/")
        self.model = os.environ.get("POWER_LLM_MODEL", OPENROUTER_MODELS[0])
        self.embedder = embedder or get_embedding_manager()
        self.allow_remote_llm = allow_remote_llm
        self.sensitivity = sensitivity

    def detect(self, vault_dir: Path) -> list[tuple[str, str, str]]:
        """
        Find pairs of notes that are semantically similar but contradictory.

        Returns list of (path_a, path_b, reason).
        """
        notes: dict[str, str] = {}
        embeddings: dict[str, list[float]] = {}
        paths: list[str] = []
        results: list[tuple[str, str, str]] = []
        checked: set[tuple[str, str]] = set()

        for filepath in iter_vault_markdown_files(vault_dir):
            rel = filepath.relative_to(vault_dir)
            if should_skip(vault_dir, rel.as_posix()):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception as exc:
                logger.debug("Cannot read %s: %s", filepath, exc)
                continue

            body = self._get_body(content)
            if len(body) < 50:
                continue

            rel_path = rel.as_posix()
            notes[rel_path] = body
            try:
                embeddings[rel_path] = self.embedder.embed(body)
            except Exception as exc:
                logger.debug("Cannot embed %s: %s", filepath, exc)
                continue
            paths.append(rel_path)

        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = paths[i], paths[j]
                pair = (a, b) if a < b else (b, a)
                if pair in checked:
                    continue
                checked.add(pair)
                sim = _dense_cosine_similarity(embeddings[a], embeddings[b])
                if sim >= self.similarity_threshold:
                    reason = self._check_contradiction(notes[a], notes[b], a, b, vault_dir)
                    if reason:
                        results.append((a, b, reason))

        return results

    def _check_contradiction(
        self,
        body_a: str,
        body_b: str,
        path_a: str,
        path_b: str,
        vault_dir: Path,
    ) -> str | None:
        """Check if two texts contradict. Returns reason string or None."""
        if self.allow_remote_llm and (self.api_key or self.api_base == "opencode"):
            return self._llm_contradiction_check(body_a, body_b)
        return self._metadata_contradiction_check(path_a, path_b, vault_dir)

    def _llm_contradiction_check(self, body_a: str, body_b: str) -> str | None:
        """Call LLM to check for contradictions."""
        prompt = (
            "You are a contradiction detection system. Analyze the following two "
            "texts from a knowledge base and determine if they contain contradictory "
            "facts, instructions, or statements.\n\n"
            f"TEXT 1:\n{body_a}\n\n"
            f"TEXT 2:\n{body_b}\n\n"
            "Do these texts contradict each other? Answer with either:\n"
            "YES: <specific reason why they contradict>\n"
            "NO\n\n"
            "Only answer YES if there is a clear factual contradiction. "
            "Differences in wording or complementary information should be marked NO."
        )

        if self.api_base == "opencode":
            res_text = run_opencode_cli(prompt)
            if not res_text:
                return None
            res_text = res_text.strip()
            if res_text.upper().startswith("YES"):
                return res_text
            return None

        if not self.api_key:
            return None

        require_remote_egress(EgressOperation.ROT, self.sensitivity)

        endpoint_url = f"{self.api_base}/chat/completions"
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.1,
            }
        ).encode("utf-8")

        try:
            validate_llm_endpoint(endpoint_url)
            response = safe_http_request(
                endpoint_url,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                body=payload,
                require_https=True,
                allowed_origins=configured_llm_origins(),
                allow_query=False,
                max_redirects=0,
                timeout=15,
            )
            if response.status >= 400:
                return None
            body = json.loads(response.body.decode("utf-8"))
            content = body["choices"][0]["message"]["content"].strip()
            if content.upper().startswith("YES"):
                reason = content[4:].strip()
                return reason or "Semantic contradiction detected"
        except (
            EgressDeniedError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
        ) as exc:
            logger.debug("LLM contradiction check failed: %s", type(exc).__name__)

        return None

    def _metadata_contradiction_check(
        self,
        path_a: str,
        path_b: str,
        vault_dir: Path,
    ) -> str | None:
        """Fallback: compare metadata fields for contradictions."""
        try:
            path_a_file = vault_dir / path_a
            path_b_file = vault_dir / path_b
            if not is_regular_vault_file(vault_dir, path_a_file) or not is_regular_vault_file(
                vault_dir, path_b_file
            ):
                return None
            content_a = read_file_content(path_a_file)
            content_b = read_file_content(path_b_file)
        except (OSError, UnicodeError, ValueError):
            return None

        fm_a = parse_frontmatter(content_a) or {}
        fm_b = parse_frontmatter(content_b) or {}

        status_a = str(fm_a.get("status", "")).strip().lower()
        status_b = str(fm_b.get("status", "")).strip().lower()
        if (
            status_a
            and status_b
            and status_a != status_b
            and ({"active", "archived", "draft"} & {status_a, status_b})
        ):
            return f"Conflicting status: '{status_a}' vs '{status_b}'"

        owner_a = str(fm_a.get("owner", "")).strip()
        owner_b = str(fm_b.get("owner", "")).strip()
        if owner_a and owner_b and owner_a.lower() != owner_b.lower():
            return f"Different owners: '{owner_a}' vs '{owner_b}'"

        expiry_a = fm_a.get("expiry")
        expiry_b = fm_b.get("expiry")
        if expiry_a and expiry_b:
            try:
                from datetime import date as date_type

                now = datetime.now(UTC).date()
                expired_a = isinstance(expiry_a, date_type) and expiry_a < now
                expired_b = isinstance(expiry_b, date_type) and expiry_b < now
                if expired_a != expired_b:
                    return "Opposite expiry dates: one expired, other not"
            except (ValueError, TypeError):
                # Invalid date formats; handled during normal schema validation.
                pass

        priority_a = str(fm_a.get("priority", "")).strip().lower()
        priority_b = str(fm_b.get("priority", "")).strip().lower()
        if priority_a and priority_b and priority_a != priority_b:
            return f"Conflicting priorities: '{priority_a}' vs '{priority_b}'"

        return None

    @staticmethod
    def _get_body(content: str) -> str:
        """Extract body content, stripping frontmatter."""
        match = FRONTMATTER_PATTERN.match(content)
        if match:
            return content[match.end() :].strip()
        return content.strip()


class FreshnessScorer:
    """Compute freshness scores based on note type and last modified timestamp."""

    def score_all(self, vault_dir: Path) -> dict[str, float]:
        """
        Score all notes in vault by freshness (0.0 = stale, 1.0 = fresh).

        Uses exponential decay: score = 2^(-age_days / half_life_days)
        """
        from power_framework.core.parser import parse_frontmatter

        now = datetime.now(UTC)
        scores: dict[str, float] = {}

        for filepath in iter_vault_markdown_files(vault_dir):
            rel = filepath.relative_to(vault_dir)
            if should_skip(vault_dir, rel.as_posix()):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception as exc:
                logger.debug("Cannot read %s: %s", filepath, exc)
                continue

            fm = parse_frontmatter(content)
            if fm is None:
                continue

            note_type = str(fm.get("type", ""))
            ts = fm.get("timestamp")

            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                age = (now - ts).total_seconds() / 86400.0
            else:
                age = 0.0

            half_life = TYPE_HALF_LIFE_DAYS.get(note_type, DEFAULT_HALF_LIFE_DAYS)
            score = 2.0 ** (-age / half_life) if half_life > 0 else 1.0
            scores[rel.as_posix()] = round(min(1.0, max(0.0, score)), 4)

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
        from concurrent.futures import ThreadPoolExecutor

        results: dict[str, list[tuple[str, int]]] = {}
        to_check: list[tuple[str, str]] = []

        for filepath in iter_vault_markdown_files(vault_dir):
            rel = filepath.relative_to(vault_dir)
            if should_skip(vault_dir, rel.as_posix()):
                continue
            if filepath.name in ("index.md", "log.md", "_index.md"):
                continue

            try:
                content = read_file_content(filepath)
            except Exception as exc:
                logger.debug("Cannot read %s: %s", filepath, exc)
                continue

            urls = self.EXTERNAL_LINK_PATTERN.findall(content)
            to_check.extend((rel.as_posix(), url) for url in urls)

        if not to_check:
            return results

        # Parallelize check using ThreadPoolExecutor (strict 50% CPU limit)
        def check_url(item: tuple[str, str]) -> tuple[str, str, int]:
            rel_path, url = item
            status = self._head_status(url)
            return rel_path, url, status

        cpu_limit = get_cpu_worker_limit()
        with ThreadPoolExecutor(max_workers=cpu_limit) as executor:
            check_results = list(executor.map(check_url, to_check))

        for rel_path, url, status in check_results:
            if status >= 400 or status == -1:
                if rel_path not in results:
                    results[rel_path] = []
                results[rel_path].append((url, status))

        return results

    def _head_status(self, url: str) -> int:
        """Perform HTTP HEAD request and return status code. Returns -1 on error."""
        try:
            require_remote_egress(EgressOperation.ROT, "public")
        except EgressDeniedError:
            return -1
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            response = safe_http_request(
                url,
                method="HEAD",
                headers=headers,
                require_https=False,
                max_redirects=3,
                timeout=self.timeout,
            )
            if response.status in {403, 405, 501}:
                response = safe_http_request(
                    url,
                    method="GET",
                    headers=headers,
                    require_https=False,
                    max_redirects=3,
                    timeout=self.timeout,
                )
            return int(response.status)
        except EgressDeniedError:
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

    @staticmethod
    def read_all_counts(vault_dir: Path) -> dict[str, int]:
        """Read an existing usage database without creating or changing it."""
        database = Path(vault_dir) / ".power_usage.db"
        if database.is_symlink() or not database.is_file():
            return {}
        with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as conn:
            rows = conn.execute("SELECT rel_path, access_count FROM note_usage").fetchall()
        return {str(rel_path): int(access_count) for rel_path, access_count in rows}

    def track_access(self, rel_path: str) -> None:
        """Increment access counter for a note."""
        now = datetime.now(UTC).isoformat()
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
