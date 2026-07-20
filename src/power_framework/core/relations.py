"""
P.O.W.E.R. Entity Extraction & Relation Suggestions.

Auto-discovers knowledge graph connections between notes using:
  - Keyword overlap (TF-IDF style) between title + description + body
  - Tag intersection
  - Explicit MCP-driven relation submission from AI agents
"""

from __future__ import annotations

import re
from collections import deque
from typing import TYPE_CHECKING

from .ignore import should_skip
from .parser import read_file_content, validate_metadata

if TYPE_CHECKING:
    from pathlib import Path

    from .models import NoteFile, OKFMetadata

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
            "є",
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
        if should_skip(vault_dir, str(rel)):
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
        if target_path not in notes:
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


class KnowledgeGraph:
    """Build a graph from vault notes and traverse it.

    Each node is a note path; edges are TypedRelation entries from metadata.
    Supports BFS traversal and Mermaid diagram export.
    """

    def __init__(self) -> None:
        self._nodes: set[str] = set()
        self._edges: list[tuple[str, str, str, float]] = []
        self._adj: dict[str, list[tuple[str, str, float]]] = {}

    def add_note(self, note_path: str) -> None:
        """Register a note node."""
        self._nodes.add(note_path)
        if note_path not in self._adj:
            self._adj[note_path] = []

    def add_relation(
        self,
        source: str,
        target: str,
        relation: str = "related_to",
        confidence: float = 1.0,
    ) -> None:
        """Add a directed edge from source to target."""
        self.add_note(source)
        self.add_note(target)
        self._edges.append((source, target, relation, confidence))
        self._adj[source].append((target, relation, confidence))

    @classmethod
    def from_notes(
        cls,
        notes: list[NoteFile],
    ) -> KnowledgeGraph:
        """Build a graph from a list of NoteFile objects using their 'related' metadata."""
        kg = cls()
        for note in notes:
            if note.metadata is None:
                continue
            kg.add_note(note.rel_path)
            for rel in note.metadata.related:
                kg.add_relation(
                    source=note.rel_path,
                    target=rel.path,
                    relation=rel.relation,
                    confidence=rel.confidence,
                )
        return kg

    def bfs(
        self,
        start_path: str,
        max_hops: int = 2,
    ) -> list[tuple[str, str, str, float, int]]:
        """BFS traversal from start_path, returning (source, target, relation, confidence, depth).

        Args:
            start_path: The note path to start traversal from.
            max_hops: Maximum traversal depth (number of edges).

        Returns: List of edges reachable within max_hops, each annotated with depth.
        """
        if start_path not in self._adj:
            return []

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        queue.append((start_path, 0))
        visited.add(start_path)
        result: list[tuple[str, str, str, float, int]] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for target, relation, confidence in self._adj.get(current, []):
                edge = (current, target, relation, confidence, depth + 1)
                result.append(edge)
                if target not in visited:
                    visited.add(target)
                    queue.append((target, depth + 1))

        return result

    def to_mermaid(
        self,
        center_path: str | None = None,
        max_depth: int = 2,
    ) -> str:
        """Export the graph (or a subgraph around center_path) as a Mermaid flow diagram.

        Args:
            center_path: If set, only include nodes reachable within max_depth hops.
            max_depth: Maximum traversal depth from center_path.

        Returns: Mermaid Markdown string (e.g. ```mermaid\\ngraph TD\\n ... ```).
        """
        if center_path:
            reachable_edges = self.bfs(center_path, max_hops=max_depth)
            if not reachable_edges:
                return "```mermaid\ngraph TD\n```"
            included_nodes: set[str] = {center_path}
            for src, tgt, _rel, _conf, _depth in reachable_edges:
                included_nodes.add(src)
                included_nodes.add(tgt)
            edges = [(src, tgt, rel, conf) for src, tgt, rel, conf, _depth in reachable_edges]
        else:
            edges = self._edges
            included_nodes = self._nodes

        node_ids: dict[str, str] = {}
        for node_counter, node in enumerate(sorted(included_nodes)):
            node_ids[node] = f"N{node_counter}"

        lines: list[str] = ["```mermaid", "graph TD"]
        for node in sorted(included_nodes):
            nid = node_ids[node]
            label = node.split("/")[-1].replace(".md", "")
            lines.append(f'    {nid}["{label}"]')
        for src, tgt, rel, _conf in edges:
            src_id = node_ids[src]
            tgt_id = node_ids[tgt]
            lines.append(f"    {src_id} -->|{rel}| {tgt_id}")
        lines.append("```")

        return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# Graph RAG v2 (POWER 3.0 Phase 3 — Uniqueness)
#
# v2 extends v1 with:
#   * weighted, bidirectional edges (explicit OKF ``related`` links are strong
#     signals, not just keyword/tag overlap),
#   * graph-distance awareness via a weighted BFS over the knowledge graph,
#   * node centrality so the most-connected notes surface as hub suggestions.
# ---------------------------------------------------------------------------

# Weight contributions for the v2 composite edge score.
_W_KW = 0.55
_W_TAG = 0.20
_W_EXPLICIT = 0.25  # explicit OKF ``related`` link bonus (saturates the score)


def _compute_overlap_score_v2(
    keywords_a: set[str],
    tags_a: list[str],
    keywords_b: set[str],
    tags_b: list[str],
    explicit_link: bool = False,
) -> float:
    """v2 composite relationship score in [0, 1].

    Combines keyword overlap (0.55), tag intersection (0.20), and an explicit
    OKF ``related`` link bonus (0.25). An explicit link saturates the score
    toward 1.0 because it is a curated, high-precision signal.
    """
    if not keywords_a or not keywords_b:
        base = 0.0
    else:
        kw_inter = keywords_a & keywords_b
        kw_union = keywords_a | keywords_b
        kw_score = len(kw_inter) / len(kw_union) if kw_union else 0.0
        tag_inter = set(tags_a) & set(tags_b)
        tag_score = len(tag_inter) / max(len(set(tags_a) | set(tags_b)), 1)
        base = min(1.0, kw_score * _W_KW + tag_score * _W_TAG)

    if explicit_link:
        return min(1.0, base + _W_EXPLICIT)
    return base


def suggest_related_v2(
    vault_dir: Path,
    target_path: str | None = None,
    max_results: int = SUGGEST_MAX_RESULTS,
    score_threshold: float = SUGGEST_RELATION_SCORE_THRESHOLD,
) -> list[RelationSuggestion]:
    """Graph RAG v2 relation suggester.

    Builds a weighted, bidirectional similarity graph over the vault. Explicit
    OKF ``related`` links contribute a strong, curated signal; keyword/tag
    overlap contributes the rest. Returns suggestions sorted by descending
    composite score.

    Args:
        vault_dir: Vault root.
        target_path: If set, only suggest relations for this note.
        max_results: Max suggestions.
        score_threshold: Minimum composite score.
    """
    # rel_path -> (keywords, tags, explicit_related_paths:set[str])
    notes: dict[str, tuple[set[str], list[str], set[str]]] = {}
    explicit_links: dict[str, set[str]] = {}

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, str(rel)):
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
        expl = {r.path for r in metadata.related}
        notes[rel_path] = (keywords, tags, expl)
        explicit_links[rel_path] = expl

    suggestions: list[RelationSuggestion] = []
    paths = list(notes.keys())

    def _emit(src: str, tgt: str) -> None:
        if src == tgt:
            return
        explicit = tgt in explicit_links.get(src, set()) or src in explicit_links.get(tgt, set())
        kw_a, tags_a, _ = notes[src]
        kw_b, tags_b, _ = notes[tgt]
        score = _compute_overlap_score_v2(kw_a, tags_a, kw_b, tags_b, explicit_link=explicit)
        if score >= score_threshold:
            reason = (
                "Explicit OKF 'related' link"
                if explicit
                else f"Keyword/tag overlap ({int(score * 100)}%)"
            )
            suggestions.append(
                RelationSuggestion(
                    source_path=src,
                    target_path=tgt,
                    score=score,
                    reason=reason,
                )
            )

    if target_path:
        if target_path not in notes:
            return []
        for tgt in paths:
            _emit(target_path, tgt)
    else:
        seen: set[tuple[str, str]] = set()
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = paths[i], paths[j]
                key = (a, b) if a < b else (b, a)
                if key in seen:
                    continue
                seen.add(key)
                _emit(a, b)

    suggestions.sort(key=lambda s: (-s.score, s.source_path, s.target_path))
    return suggestions[:max_results]


# Graph RAG v2 — weighted knowledge graph with centrality.
class WeightedKnowledgeGraph:
    """Knowledge graph whose edges carry float weights in [0, 1].

    Built from OKF ``related`` links (weighted by their confidence) plus
    computed v2 overlap scores. Supports weighted BFS (accumulated edge weight
    as a relevance proxy) and degree/weight centrality for hub detection.
    """

    def __init__(self) -> None:
        self._adj: dict[str, list[tuple[str, float]]] = {}
        self._nodes: set[str] = set()

    def add_weighted_relation(self, source: str, target: str, weight: float) -> None:
        self._nodes.add(source)
        self._nodes.add(target)
        self._adj.setdefault(source, []).append((target, float(weight)))
        # Bidirectional: knowledge links are symmetric for traversal purposes.
        self._adj.setdefault(target, []).append((source, float(weight)))

    @classmethod
    def from_suggestions(cls, suggestions: list[RelationSuggestion]) -> WeightedKnowledgeGraph:
        g = cls()
        for s in suggestions:
            g.add_weighted_relation(s.source_path, s.target_path, s.score)
        return g

    def weighted_bfs(self, start: str, max_hops: int = 2) -> list[tuple[str, float, int]]:
        """BFS returning (node, accumulated_weight, depth) within max_hops.

        ``accumulated_weight`` is the product of edge weights along the path
        (a belief-propagation style relevance score: longer / weaker paths
        decay). Used to rank related notes beyond direct neighbours.
        """
        if start not in self._adj:
            return []
        result: list[tuple[str, float, int]] = []
        visited: set[str] = {start}
        queue: deque[tuple[str, float, int]] = deque([(start, 1.0, 0)])
        while queue:
            node, acc, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for nxt, w in self._adj.get(node, []):
                new_acc = acc * w
                result.append((nxt, new_acc, depth + 1))
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, new_acc, depth + 1))
        return result

    def centrality(self, top_k: int = 10) -> list[tuple[str, float]]:
        """Degree/weight centrality: sum of incident edge weights per node."""
        scores: dict[str, float] = {n: 0.0 for n in self._nodes}
        for src, edges in self._adj.items():
            for _tgt, w in edges:
                scores[src] += w
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return ranked[:top_k]
