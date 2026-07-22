"""Tests for TypedRelation, backward compatibility, KnowledgeGraph, and Mermaid export."""

from __future__ import annotations

from datetime import datetime

import pytest

from power_framework.core.models import (
    NoteFile,
    OKFMetadata,
    TypedRelation,
)
from power_framework.core.relations import KnowledgeGraph


class TestTypedRelation:
    """Tests for TypedRelation model."""

    def test_default_relation(self):
        tr = TypedRelation(path="01_Projects/A.md")
        assert tr.path == "01_Projects/A.md"
        assert tr.relation == "related_to"
        assert tr.confidence == 1.0

    def test_custom_relation(self):
        tr = TypedRelation(
            path="01_Projects/B.md",
            relation="depends_on",
            confidence=0.75,
        )
        assert tr.path == "01_Projects/B.md"
        assert tr.relation == "depends_on"
        assert tr.confidence == 0.75

    def test_confidence_bounds(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            TypedRelation(path="x.md", confidence=-0.1)
        with pytest.raises(pydantic.ValidationError):
            TypedRelation(path="x.md", confidence=1.5)

    def test_extra_fields_ignored(self):
        tr = TypedRelation(
            path="x.md",
            relation="related_to",
            confidence=0.5,
            unknown="ignored",
        )
        assert tr.path == "x.md"


class TestBackwardCompatibility:
    """Tests that OKFMetadata still accepts plain strings as 'related'."""

    def test_string_list_auto_converts(self):
        meta = OKFMetadata(
            type="Resource",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            related=["01_Projects/A.md", "02_Areas/B.md"],
        )
        assert len(meta.related) == 2
        for r in meta.related:
            assert isinstance(r, TypedRelation)
        assert meta.related[0].path == "01_Projects/A.md"
        assert meta.related[0].relation == "related_to"
        assert meta.related[0].confidence == 1.0
        assert meta.related[1].path == "02_Areas/B.md"

    def test_mixed_strings_and_typed(self):
        meta = OKFMetadata(
            type="Resource",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            related=[
                "01_Projects/String.md",
                TypedRelation(
                    path="02_Areas/Typed.md",
                    relation="references",
                    confidence=0.9,
                ),
            ],
        )
        assert len(meta.related) == 2
        assert meta.related[0].path == "01_Projects/String.md"
        assert meta.related[0].relation == "related_to"
        assert meta.related[1].path == "02_Areas/Typed.md"
        assert meta.related[1].relation == "references"
        assert meta.related[1].confidence == 0.9

    def test_empty_list(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
        )
        assert meta.related == []

    def test_string_whitespace_stripped(self):
        meta = OKFMetadata(
            type="Resource",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            related=["  path/to/a.md  ", "", " b.md "],
        )
        assert len(meta.related) == 2
        assert meta.related[0].path == "path/to/a.md"
        assert meta.related[1].path == "b.md"

    def test_backward_serialize_to_related_paths(self):
        meta = OKFMetadata(
            type="Resource",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            related=["01_Projects/A.md"],
        )
        paths = [r.path for r in meta.related]
        assert "01_Projects/A.md" in paths


class TestKnowledgeGraph:
    """Tests for KnowledgeGraph construction and BFS traversal."""

    def make_note(self, rel_path: str, related: list[str] | None = None) -> NoteFile:
        meta = OKFMetadata(
            type="Project",
            title=rel_path,
            description="test",
            timestamp=datetime(2026, 1, 1),
            related=related or [],
        )
        return NoteFile(
            abs_path=f"/vault/{rel_path}",
            rel_path=rel_path,
            metadata=meta,
        )

    def test_empty_graph(self):
        kg = KnowledgeGraph()
        assert kg.bfs("nonexistent.md") == []
        mermaid = kg.to_mermaid()
        assert "graph TD" in mermaid

    def test_single_note_no_relations(self):
        note = self.make_note("01_Projects/A.md")
        kg = KnowledgeGraph.from_notes([note])
        assert kg.bfs("01_Projects/A.md") == []
        mermaid = kg.to_mermaid()
        assert "N0" in mermaid
        assert "A" in mermaid

    def test_direct_relations(self):
        note_a = self.make_note(
            "01_Projects/A.md",
            related=["02_Areas/B.md", "03_Resources/C.md"],
        )
        note_b = self.make_note("02_Areas/B.md")
        note_c = self.make_note("03_Resources/C.md")
        kg = KnowledgeGraph.from_notes([note_a, note_b, note_c])
        edges = kg.bfs("01_Projects/A.md", max_hops=1)
        assert len(edges) == 2
        sources = {e[0] for e in edges}
        targets = {e[1] for e in edges}
        assert sources == {"01_Projects/A.md"}
        assert targets == {"02_Areas/B.md", "03_Resources/C.md"}

    def test_multi_hop_bfs(self):
        note_a = self.make_note("01_Projects/A.md", related=["02_Areas/B.md"])
        note_b = self.make_note("02_Areas/B.md", related=["03_Resources/C.md"])
        note_c = self.make_note("03_Resources/C.md", related=["04_Archive/D.md"])
        note_d = self.make_note("04_Archive/D.md")
        kg = KnowledgeGraph.from_notes([note_a, note_b, note_c, note_d])

        edges_1hop = kg.bfs("01_Projects/A.md", max_hops=1)
        assert len(edges_1hop) == 1
        assert edges_1hop[0][1] == "02_Areas/B.md"
        assert edges_1hop[0][4] == 1

        edges_2hop = kg.bfs("01_Projects/A.md", max_hops=2)
        assert len(edges_2hop) == 2
        depths = {e[4] for e in edges_2hop}
        assert depths == {1, 2}

        edges_3hop = kg.bfs("01_Projects/A.md", max_hops=3)
        assert len(edges_3hop) == 3

    def test_typed_relations_in_graph(self):
        note = NoteFile(
            abs_path="/vault/01_Projects/A.md",
            rel_path="01_Projects/A.md",
            metadata=OKFMetadata(
                type="Project",
                title="A",
                description="test",
                timestamp=datetime(2026, 1, 1),
                related=[
                    TypedRelation(
                        path="02_Areas/B.md",
                        relation="depends_on",
                        confidence=0.8,
                    ),
                ],
            ),
        )
        target = self.make_note("02_Areas/B.md")
        kg = KnowledgeGraph.from_notes([note, target])
        edges = kg.bfs("01_Projects/A.md")
        assert len(edges) == 1
        assert edges[0][1] == "02_Areas/B.md"
        assert edges[0][2] == "depends_on"
        assert edges[0][3] == 0.8

    def test_bfs_from_unreachable_node(self):
        note_a = self.make_note("01_Projects/A.md")
        note_b = self.make_note("02_Areas/B.md")
        kg = KnowledgeGraph.from_notes([note_a, note_b])
        assert kg.bfs("01_Projects/A.md") == []

    def test_from_notes_skips_none_metadata(self):
        note = NoteFile(
            abs_path="/vault/no_meta.md",
            rel_path="no_meta.md",
            metadata=None,
        )
        kg = KnowledgeGraph.from_notes([note])
        assert len(kg._nodes) == 0

    def test_add_relation_deduplicates_nodes(self):
        kg = KnowledgeGraph()
        kg.add_relation("A.md", "B.md")
        kg.add_relation("A.md", "C.md")
        assert len(kg._nodes) == 3


class TestMermaidExport:
    """Tests for Mermaid diagram generation."""

    def make_note(self, rel_path: str, related: list[str] | None = None) -> NoteFile:
        meta = OKFMetadata(
            type="Project",
            title=rel_path,
            description="test",
            timestamp=datetime(2026, 1, 1),
            related=related or [],
        )
        return NoteFile(
            abs_path=f"/vault/{rel_path}",
            rel_path=rel_path,
            metadata=meta,
        )

    def test_empty_graph_returns_minimal_mermaid(self):
        kg = KnowledgeGraph()
        result = kg.to_mermaid()
        assert "```mermaid" in result
        assert "graph TD" in result
        assert "```" in result

    def test_basic_mermaid_output(self):
        note = self.make_note(
            "01_Projects/A.md",
            related=["02_Areas/B.md"],
        )
        target = self.make_note("02_Areas/B.md")
        kg = KnowledgeGraph.from_notes([note, target])
        result = kg.to_mermaid()

        assert "```mermaid" in result
        assert "graph TD" in result
        assert 'N0["A"]' in result
        assert 'N1["B"]' in result
        assert "N0 -->|related_to| N1" in result

    def test_mermaid_with_center_path(self):
        note_a = self.make_note("01_Projects/A.md", related=["02_Areas/B.md"])
        note_b = self.make_note("02_Areas/B.md", related=["03_Resources/C.md"])
        note_c = self.make_note("03_Resources/C.md")
        kg = KnowledgeGraph.from_notes([note_a, note_b, note_c])

        result = kg.to_mermaid(center_path="01_Projects/A.md", max_depth=1)
        assert 'N0["A"]' in result
        assert 'N1["B"]' in result
        assert "N0 -->|related_to| N1" in result
        assert "C" not in result

    def test_mermaid_with_custom_relation(self):
        note = NoteFile(
            abs_path="/vault/A.md",
            rel_path="A.md",
            metadata=OKFMetadata(
                type="Project",
                title="A",
                description="test",
                timestamp=datetime(2026, 1, 1),
                related=[
                    TypedRelation(path="B.md", relation="depends_on", confidence=0.9),
                ],
            ),
        )
        target = self.make_note("B.md")
        kg = KnowledgeGraph.from_notes([note, target])
        result = kg.to_mermaid()
        assert 'N0["A"]' in result
        assert 'N1["B"]' in result
        assert "N0 -->|depends_on| N1" in result

    def test_mermaid_center_path_no_relations(self):
        note = self.make_note("orphan.md")
        kg = KnowledgeGraph.from_notes([note])
        result = kg.to_mermaid(center_path="orphan.md")
        assert "orphan" not in result or "###" not in result
        assert "```mermaid" in result

    def test_mermaid_multiple_edges(self):
        note = self.make_note(
            "01_Projects/A.md",
            related=["02_Areas/B.md", "03_Resources/C.md"],
        )
        note_b = self.make_note("02_Areas/B.md")
        note_c = self.make_note("03_Resources/C.md")
        kg = KnowledgeGraph.from_notes([note, note_b, note_c])
        result = kg.to_mermaid()
        assert "N0 -->|related_to| N1" in result
        assert "N0 -->|related_to| N2" in result

    def test_suggest_related(self, tmp_path):
        from power_framework.core.relations import suggest_related

        # Create two sample markdown files with overlapping keywords
        note1 = tmp_path / "01_Projects" / "note1.md"
        note1.parent.mkdir(parents=True, exist_ok=True)
        note1.write_text(
            "---\ntype: Project\ntitle: Alpha System\ndescription: Test alpha system\ntags: [alpha, system]\ntimestamp: 2026-07-22T00:00:00\n---\nAlpha system handles data processing.",
            encoding="utf-8",
        )

        note2 = tmp_path / "01_Projects" / "note2.md"
        note2.write_text(
            "---\ntype: Project\ntitle: Beta System\ndescription: Test beta system\ntags: [alpha, beta]\ntimestamp: 2026-07-22T00:00:00\n---\nBeta system also handles alpha data processing.",
            encoding="utf-8",
        )

        suggestions = suggest_related(tmp_path, target_path="01_Projects/note1.md", score_threshold=0.1)
        assert isinstance(suggestions, list)

