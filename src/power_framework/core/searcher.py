"""
P.O.W.E.R. Full-Text Search Engine.

Zero-dependency search across vault notes with ranked results,
context snippets, and metadata-aware scoring.
"""

from __future__ import annotations

import re
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
    return re.findall(r"[a-z0-9а-яєіїґ']+", text.lower())


def _make_snippet(content: str, terms: list[str]) -> str:
    """Extract a relevant snippet around the first match of any term."""
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
    """Score a single note against search terms using weighted TF matching."""
    total_score = 0.0
    total_matches = 0

    title_lower = metadata.title.lower()
    desc_lower = metadata.description.lower()
    content_lower = content.lower()
    tags_lower = [t.lower() for t in metadata.tags]

    for term in terms:
        term_lower = term.lower()

        # Title match (highest weight)
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

        # Body content match (lowest weight)
        body_count = content_lower.count(term_lower)
        if body_count:
            total_score += body_count * CONTENT_WEIGHT
            total_matches += body_count

    snippet = _make_snippet(content, terms) if total_matches > 0 else ""
    return total_score, total_matches, snippet


def _scan_and_search(vault_dir: Path, terms: list[str]) -> list[SearchResult]:
    """Scan vault and return scored search results."""
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
        except Exception:
            continue

    return results


def search_vault(vault_dir: Path, query: str, max_results: int = 20) -> list[SearchResult]:
    """
    Search the vault for notes matching the query.

    Supports:
    - Multi-word queries (space-separated terms)
    - Phrase matching via double quotes
    - Case-insensitive matching
    - Weighted scoring: title > tags > description > body

    Returns ranked results sorted by relevance score.
    """
    if not query or not query.strip():
        return []

    vault_dir = Path(vault_dir).resolve()
    if not vault_dir.is_dir():
        return []

    # Parse query into terms (split by whitespace, handle quoted phrases)
    terms: list[str] = []
    for match in re.finditer(r'"([^"]+)"|(\S+)', query.strip()):
        term = (match.group(1) or match.group(2)).strip().lower()
        if term:
            terms.append(term)

    if not terms:
        return []

    results = _scan_and_search(vault_dir, terms)

    # Sort by score descending, then by match count
    results.sort(key=lambda r: (-r.score, -r.match_count, r.title))

    return results[:max_results]


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
