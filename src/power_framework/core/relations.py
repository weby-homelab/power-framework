"""
P.O.W.E.R. Entity Extraction & Relation Suggestions.

Auto-discovers knowledge graph connections between notes using:
  - Keyword overlap (TF-IDF style) between title + description + body
  - Tag intersection
  - Explicit MCP-driven relation submission from AI agents
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .parser import read_file_content, validate_metadata
from .utils import EXCLUDED_DIRS

if TYPE_CHECKING:
    from pathlib import Path

    from .models import OKFMetadata

SUGGEST_MIN_KEYWORD_LEN = 3
SUGGEST_MAX_KEYWORDS = 10
SUGGEST_RELATION_SCORE_THRESHOLD = 0.15
SUGGEST_MAX_RESULTS = 5


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text (ignore short/common words)."""
    stop_words = frozenset(
        {
            "this",
            "that",
            "with",
            "from",
            "have",
            "been",
            "will",
            "would",
            "what",
            "which",
            "their",
            "them",
            "into",
            "about",
            "than",
            "the",
            "and",
            "for",
            "are",
            "not",
            "but",
            "was",
            "has",
            "can",
            "all",
            "its",
            "how",
            "note",
            "also",
            "very",
            "just",
            "only",
            "more",
            "some",
            "such",
            "each",
            "well",
            "new",
            "що",
            "для",
            "так",
            "як",
            "але",
            "його",
            "є�ї",
            "може",
            "бути",
            "були",
            "воно",
            "вона",
            "вони",
        }
    )
    tokens = set(re.findall(r"[a-zA-Zа-яєіїґ]{3,}", text.lower()))  # noqa: RUF001
    return {t for t in tokens if t not in stop_words}


def _compute_overlap_score(
    keywords_a: set[str],
    keywords_b: set[str],
    tags_a: list[str],
    tags_b: list[str],
) -> float:
    """Compute relationship score between two notes (0.0 - 1.0)."""
    if not keywords_a or not keywords_b:
        return 0.0

    kw_intersection = keywords_a & keywords_b
    kw_union = keywords_a | keywords_b
    kw_score = len(kw_intersection) / len(kw_union) if kw_union else 0.0

    tag_intersection = set(tags_a) & set(tags_b)
    tag_score = len(tag_intersection) / max(len(set(tags_a) | set(tags_b)), 1)

    return min(1.0, kw_score * 0.7 + tag_score * 0.3)


class RelationSuggestion:
    """A suggested relation between two notes."""

    def __init__(
        self,
        source_path: str,
        target_path: str,
        score: float,
        reason: str = "",
    ) -> None:
        self.source_path = source_path
        self.target_path = target_path
        self.score = score
        self.reason = reason


def suggest_related(
    vault_dir: Path,
    target_path: str | None = None,
    max_results: int = SUGGEST_MAX_RESULTS,
    score_threshold: float = SUGGEST_RELATION_SCORE_THRESHOLD,
) -> list[RelationSuggestion]:
    """
    Auto-suggest related notes based on keyword and tag overlap.

    Args:
        vault_dir: Path to vault root
        target_path: If set, only suggest relations for this specific note
        max_results: Max suggestions per note
        score_threshold: Minimum similarity score (0.0-1.0)

    Returns: Sorted list of RelationSuggestion (descending score)
    """
    notes: dict[str, tuple[set[str], list[str], str, str]] = {}

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue

        try:
            content = read_file_content(filepath)
        except Exception:  # noqa: S112
            continue

        metadata: OKFMetadata | None = validate_metadata(content)
        if metadata is None:
            continue

        rel_path = str(rel)
        kw_text = f"{metadata.title} {metadata.description} {content}"
        keywords = _extract_keywords(kw_text)
        tags = metadata.tags or []

        notes[rel_path] = (keywords, tags, metadata.title, content)

    suggestions: list[RelationSuggestion] = []

    if target_path:
        candidates = [(p, d) for p, d in notes.items() if p == target_path]
        if not candidates:
            return []
        for src_path in [p for p in notes if p == target_path]:
            src_kw, src_tags, *_ = notes[src_path]
            for tgt_path, (tgt_kw, tgt_tags, *_) in notes.items():
                if tgt_path == src_path:
                    continue
                score = _compute_overlap_score(src_kw, tgt_kw, src_tags, tgt_tags)
                if score >= score_threshold:
                    suggestions.append(
                        RelationSuggestion(
                            source_path=src_path,
                            target_path=tgt_path,
                            score=score,
                            reason=f"Keyword/tag overlap ({int(score * 100)}%)",
                        )
                    )
    else:
        paths = list(notes.keys())
        checked: set[tuple[str, str]] = set()
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                pair = (paths[i], paths[j]) if paths[i] < paths[j] else (paths[j], paths[i])
                if pair in checked:
                    continue
                checked.add(pair)
                kw_a, tags_a, _, _ = notes[paths[i]]
                kw_b, tags_b, _, _ = notes[paths[j]]
                score = _compute_overlap_score(kw_a, kw_b, tags_a, tags_b)
                if score >= score_threshold:
                    suggestions.append(
                        RelationSuggestion(
                            source_path=pair[0],
                            target_path=pair[1],
                            score=score,
                            reason=f"Keyword/tag overlap ({int(score * 100)}%)",
                        )
                    )

    suggestions.sort(key=lambda s: (-s.score, s.source_path, s.target_path))
    return suggestions[:max_results]


def format_relation_suggestions(
    suggestions: list[RelationSuggestion],
    vault_dir: Path,
) -> str:
    """Format relation suggestions into a human-readable report."""
    if not suggestions:
        return "No relation suggestions found."

    lines = [
        "=== P.O.W.E.R. Relation Suggestions ===",
        f"Vault: {vault_dir}",
        f"Found {len(suggestions)} suggestion(s):",
        "",
    ]
    for s in suggestions:
        pct = int(s.score * 100)
        lines.append(f"- {s.source_path}")
        lines.append(f"  -> {s.target_path}  [{pct}% confidence]")
        lines.append(f"  Reason: {s.reason}")
        lines.append("")

    return "\n".join(lines)
