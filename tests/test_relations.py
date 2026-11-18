"""
Tests for entity extraction and relation suggestions.
"""

from __future__ import annotations

import os
import sqlite3
import struct
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from power_framework.core.models import NoteFile, OKFMetadata, TypedRelation
from power_framework.core.relations import (
    KnowledgeGraph,
    RelationSuggestion,
    _compute_overlap_score,
    _extract_keywords,
    format_relation_suggestions,
    suggest_related,
)


class TestExtractKeywords:
    """Tests for keyword extraction."""

    def test_extracts_meaningful_words(self):
        words = _extract_keywords("Docker container deployment setup")
        assert "docker" in words
        assert "container" in words
        assert "deployment" in words

    def test_filters_stop_words(self):
        words = _extract_keywords("this is a test with the and for")
        assert len(words) <= 2  # 'test' and maybe 'with'

    def test_empty_text(self):
        assert _extract_keywords("") == set()

    def test_unicode_support(self):
        words = _extract_keywords("розгортання контейнера докер")
        assert "розгортання" in words or "контейнера" in words


class TestComputeOverlapScore:
    """Tests for relation score computation."""

    def test_identical_keywords(self):
        kw = {"docker", "deploy", "container"}
        score = _compute_overlap_score(kw, kw, ["dev"], ["dev"])
        assert score > 0.5

    def test_no_overlap(self):
        score = _compute_overlap_score({"abc"}, {"xyz"}, [], [])
        assert score == 0.0

    def test_tag_boost(self):
        kw_a = {"docker"}
        kw_b = {"kubernetes"}
        score_with_tags = _compute_overlap_score(kw_a, kw_b, ["dev"], ["dev"])
        score_no_tags = _compute_overlap_score(kw_a, kw_b, [], [])
        assert score_with_tags > score_no_tags


class TestSuggestRelated:
    """Tests for relation suggestion on vaults."""

    def test_healthy_vault(self, sample_vault: Path):
        suggestions = suggest_related(sample_vault, max_results=10)
        # The sample vault has notes with "Test" in title — they may overlap
        assert isinstance(suggestions, list)

    def test_specific_target(self, sample_vault: Path):
        suggestions = suggest_related(
            sample_vault,
            target_path="03_Resources/TestResource.md",
            max_results=5,
        )
        assert isinstance(suggestions, list)

    def test_no_target_for_nonexistent(self, sample_vault: Path):
        suggestions = suggest_related(
            sample_vault,
            target_path="nonexistent.md",
            max_results=5,
        )
        assert suggestions == []

    def test_empty_vault(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        suggestions = suggest_related(empty)
        assert suggestions == []

    def test_max_results(self, sample_vault: Path):
        suggestions = suggest_related(sample_vault, max_results=2)
        assert len(suggestions) <= 2


class TestRelationSuggestion:
    """Tests for RelationSuggestion class."""

    def test_creation(self):
        rs = RelationSuggestion(
            source_path="a.md",
            target_path="b.md",
            score=0.75,
            reason="Overlap",
        )
        assert rs.source_path == "a.md"
        assert rs.target_path == "b.md"
        assert rs.score == 0.75
        assert rs.reason == "Overlap"


class TestKnowledgeGraphIntegrity:
    def test_from_notes_quarantines_missing_relation_target(self):
        source = NoteFile(
            abs_path="/vault/source.md",
            rel_path="01_Projects/source.md",
            metadata=OKFMetadata(
                type="Project",
                title="Source",
                description="Source note",
                timestamp=datetime(2026, 1, 1),
                related=[TypedRelation(path="01_Projects/missing.md")],
            ),
        )
        target = NoteFile(
            abs_path="/vault/target.md",
            rel_path="01_Projects/target.md",
            metadata=OKFMetadata(
                type="Project",
                title="Target",
                description="Target note",
                timestamp=datetime(2026, 1, 1),
            ),
        )

        graph = KnowledgeGraph.from_notes([source, target])

        assert graph._nodes == {"01_Projects/source.md", "01_Projects/target.md"}
        assert graph._edges == []
        assert graph.quarantined_edges == [
            ("01_Projects/source.md", "01_Projects/missing.md", "related_to", 1.0)
        ]


class TestFormatRelationSuggestions:
    """Tests for formatted output."""

    def test_empty(self):
        report = format_relation_suggestions([], Path("/test"))
        assert "No relation suggestions" in report

    def test_with_suggestions(self):
        suggestions = [
            RelationSuggestion("a.md", "b.md", 0.8, "Strong overlap"),
        ]
        report = format_relation_suggestions(suggestions, Path("/test"))
        assert "a.md" in report
        assert "b.md" in report
        assert "80%" in report


class TestSemanticSuggestions:
    """Tests for suggest_related_semantic (WTF #5 remediation)."""

    def _fake_manager(self, vectors: dict[str, list[float]]):
        class _Fake:
            def embed(self, text: str):
                return vectors.get(text, [0.0] * len(next(iter(vectors.values()))))

        return _Fake()

    def test_cosine_helper(self):
        from power_framework.core.relations import _cosine

        assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
        assert _cosine([], [1.0]) == 0.0

    def test_semantic_ranks_closest_note(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Build a vault with two notes + a target whose text overlaps note A.
        (tmp_path / "01_Projects").mkdir()
        target = tmp_path / "01_Projects" / "Target.md"
        note_a = tmp_path / "01_Projects" / "NoteA.md"
        note_b = tmp_path / "01_Projects" / "NoteB.md"
        for p, body in (
            (target, "semantic retrieval vector cosine similarity embedding"),
            (note_a, "semantic retrieval vector cosine similarity embedding"),
            (note_b, "banana bread recipe with walnuts and cinnamon sugar"),
        ):
            p.write_text(
                "---\ntype: Project\ntitle: T\n"
                f'description: "{body}"\ntimestamp: 2026-01-01T00:00:00\n---\n\n{body}\n'
            )

        # Deterministic fake embeddings keyed by substring so the full note
        # bodies (which include frontmatter) still resolve correctly.
        class _Fake:
            def embed(self, text: str):
                if "semantic retrieval" in text:
                    return [1.0, 0.0, 0.0]
                if "banana bread" in text:
                    return [0.0, 1.0, 0.0]
                return [0.0, 0.0, 1.0]

        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", lambda: _Fake()
        )

        from power_framework.core.relations import suggest_related_semantic

        suggestions = suggest_related_semantic(
            tmp_path, target_path="01_Projects/Target.md", max_results=5
        )
        assert suggestions, "expected at least one semantic suggestion"
        # Note A (identical embedding) must outrank the unrelated Note B.
        top = suggestions[0]
        assert top.target_path == "01_Projects/NoteA.md"
        assert top.score == 1.0

    def test_semantic_falls_back_to_keyword_without_embeddings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / "01_Projects").mkdir()
        target = tmp_path / "01_Projects" / "Target.md"
        target.write_text(
            "---\ntype: Project\ntitle: T\n"
            'description: "docker container deployment"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\ndocker container deployment setup\n"
        )

        def _boom():
            raise RuntimeError("no embedding backend")

        monkeypatch.setattr("power_framework.core.embeddings.get_embedding_manager", _boom)

        from power_framework.core.relations import suggest_related_semantic

        # Must not raise; degrades to keyword suggestions.
        suggestions = suggest_related_semantic(tmp_path, target_path="01_Projects/Target.md")
        assert isinstance(suggestions, list)

    def test_semantic_uses_stored_doc_embeddings_and_skips_paginated_catalogs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        (tmp_path / "01_Projects").mkdir()
        target = tmp_path / "01_Projects" / "Target.md"
        note_a = tmp_path / "01_Projects" / "NoteA.md"
        note_b = tmp_path / "01_Projects" / "NoteB.md"
        paginated = tmp_path / "01_Projects" / "_index-2.md"
        for p, body in (
            (target, "alpha semantic concept target"),
            (note_a, "alpha semantic concept candidate"),
            (note_b, "completely unrelated topic"),
            (paginated, "alpha semantic concept catalog page"),
        ):
            p.write_text(
                "---\ntype: Project\ntitle: T\n"
                f'description: "{body}"\ntimestamp: 2026-01-01T00:00:00\n---\n\n{body}\n',
                encoding="utf-8",
            )

        class _SyncEmbedder:
            model_name = "fake-bge-m3"
            dimension = 3

            def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
                assert batch_size > 0
                return [[1.0, 0.0, 0.0] if "alpha" in text else [0.0, 1.0, 0.0] for text in texts]

        monkeypatch.setattr(
            "power_framework.core.index_sync._get_embedding_manager", lambda: _SyncEmbedder()
        )
        monkeypatch.setattr(
            "power_framework.experimental.embeddings.configured_embedding_identity",
            lambda: ("_SyncEmbedder", "fake-bge-m3"),
        )
        from power_framework.core.generation_index import sync_vault_atomically

        sync_vault_atomically(tmp_path, sync_embeddings=True)

        # Once synced, suggest_related_semantic must use stored doc_embeddings without
        # loading or calling the embedding manager at all.
        def _must_not_embed():
            raise AssertionError("get_embedding_manager must not be called when vectors are stored")

        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", _must_not_embed
        )
        from power_framework.core.relations import suggest_related_semantic

        suggestions = suggest_related_semantic(
            tmp_path, target_path="01_Projects/Target.md", max_results=5
        )
        paths = [s.target_path for s in suggestions]
        assert paths == ["01_Projects/NoteA.md", "01_Projects/NoteB.md"]
        assert "01_Projects/_index-2.md" not in paths
        assert suggestions[0].score == pytest.approx(1.0)
        assert suggestions[1].score == pytest.approx(0.0)

        # Adding a new unsynced note should only embed the new note, not cached ones.
        new_note = tmp_path / "01_Projects" / "FreshTarget.md"
        new_note.write_text(
            "---\ntype: Project\ntitle: Fresh\n"
            'description: "fresh target"\ntimestamp: 2026-01-01T00:00:00\n---\n\nfresh target\n',
            encoding="utf-8",
        )
        embedded_calls: list[str] = []

        class _OnlyFresh:
            def embed(self, text: str) -> list[float]:
                embedded_calls.append(text)
                return [1.0, 0.0, 0.0]

        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", lambda: _OnlyFresh()
        )
        fresh_suggestions = suggest_related_semantic(
            tmp_path, target_path="01_Projects/FreshTarget.md", max_results=5
        )
        assert len(embedded_calls) == 1
        assert "fresh target" in embedded_calls[0]
        assert fresh_suggestions[0].target_path in {"01_Projects/Target.md", "01_Projects/NoteA.md"}

        # Editing an existing note updates its mtime so only that note is re-embedded.
        new_note.unlink()
        embedded_calls.clear()
        edited_stat = note_a.stat()
        note_a.write_text(
            "---\ntype: Project\ntitle: T\n"
            'description: "updated candidate"\ntimestamp: 2026-01-01T00:00:00\n---\n\nupdated body\n',
            encoding="utf-8",
        )
        os.utime(note_a, ns=(edited_stat.st_atime_ns, edited_stat.st_mtime_ns + 2_000_000_000))
        suggest_related_semantic(tmp_path, target_path="01_Projects/Target.md", max_results=5)
        assert len(embedded_calls) == 1
        assert "updated body" in embedded_calls[0]

    def test_semantic_rejects_unattested_or_mismatched_manifest_and_corrupt_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        vault = tmp_path / "vault#1?q"
        (vault / "01_Projects").mkdir(parents=True)
        target = vault / "01_Projects" / "Target.md"
        note_a = vault / "01_Projects" / "NoteA.md"
        for p, body in ((target, "alpha vector note"), (note_a, "alpha vector peer")):
            p.write_text(
                "---\ntype: Project\ntitle: T\n"
                f'description: "{body}"\ntimestamp: 2026-01-01T00:00:00\n---\n\n{body}\n',
                encoding="utf-8",
            )

        class _SyncEmbedder:
            model_name = "fake-bge-m3"
            dimension = 3

            def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
                assert batch_size > 0
                return [[1.0, 0.0, 0.0] for _ in texts]

        monkeypatch.setattr(
            "power_framework.core.index_sync._get_embedding_manager", lambda: _SyncEmbedder()
        )
        monkeypatch.setattr(
            "power_framework.experimental.embeddings.configured_embedding_identity",
            lambda: ("_SyncEmbedder", "fake-bge-m3"),
        )
        from power_framework.core.generation_index import (
            resolve_active_generation_path,
            sync_vault_atomically,
        )
        from power_framework.core.relations import suggest_related_semantic

        sync_vault_atomically(vault, sync_embeddings=True)

        # Model mismatch in configured_embedding_identity invalidates cached 3d rows and
        # cleanly re-embeds with the new 2d backend (instead of returning [] on dim mismatch).
        monkeypatch.setattr(
            "power_framework.experimental.embeddings.configured_embedding_identity",
            lambda: ("_NewEmbedder", "other-model"),
        )
        batch_sizes: list[int] = []

        class _NewEmbedder:
            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                batch_sizes.append(len(texts))
                return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", lambda: _NewEmbedder()
        )
        suggestions = suggest_related_semantic(vault, target_path="01_Projects/Target.md")
        assert batch_sizes == [2]
        assert [s.target_path for s in suggestions] == ["01_Projects/NoteA.md"]

        # FTS-only sync wipes dense_index_manifest -> stored rows must not be reused.
        old_stat = note_a.stat()
        note_a.write_text(
            "---\ntype: Project\ntitle: T\n"
            'description: "alpha vector changed"\ntimestamp: 2026-01-01T00:00:00\n---\n\nchanged\n',
            encoding="utf-8",
        )
        os.utime(note_a, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 2_000_000_000))
        sync_vault_atomically(vault, sync_embeddings=False, accept_dense_loss=True)
        monkeypatch.setattr(
            "power_framework.experimental.embeddings.configured_embedding_identity",
            lambda: ("_SyncEmbedder", "fake-bge-m3"),
        )
        batch_sizes.clear()
        suggest_related_semantic(vault, target_path="01_Projects/Target.md")
        assert batch_sizes == [2]

        # Re-sync dense, then inject NaN BLOB + non-numeric mtime into legacy/active DB copy.
        sync_vault_atomically(vault, sync_embeddings=True)
        db_path = resolve_active_generation_path(vault)
        assert db_path is not None
        # Corrupt active DB rows on a temporary legacy vault to avoid mutating generation hash;
        # inject NaN + non-numeric mtime in a standalone legacy DB vault.
        legacy_vault = tmp_path / "legacy#?vault"
        (legacy_vault / "01_Projects").mkdir(parents=True)
        t2 = legacy_vault / "01_Projects" / "Target.md"
        n2 = legacy_vault / "01_Projects" / "NoteA.md"
        for p, body in ((t2, "alpha omega"), (n2, "alpha omega")):
            p.write_text(
                "---\ntype: Project\ntitle: T\n"
                f'description: "{body}"\ntimestamp: 2026-01-01T00:00:00\n---\n\n{body}\n',
                encoding="utf-8",
            )
        from power_framework.core.constants import DENSE_INDEX_SCHEMA_VERSION
        from power_framework.core.db import _init_db
        from power_framework.core.vault_storage import vault_db_path

        legacy_db = vault_db_path(legacy_vault)
        legacy_db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(legacy_db)) as conn:
            _init_db(conn)
            conn.executemany(
                "INSERT INTO dense_index_manifest(manifest_key, manifest_value) VALUES (?, ?)",
                [
                    ("schema_version", DENSE_INDEX_SCHEMA_VERSION),
                    ("embedding_dimension", "2"),
                    ("embedding_provider", "_SyncEmbedder"),
                    ("embedding_model", "fake-bge-m3"),
                ],
            )
            conn.execute(
                "INSERT INTO doc_embeddings(rel_path, embedding, mtime) VALUES (?, ?, ?)",
                ("01_Projects/Target.md", struct.pack("2f", float("nan"), 1.0), t2.stat().st_mtime),
            )
            conn.execute(
                "INSERT INTO doc_embeddings(rel_path, embedding, mtime) VALUES (?, ?, ?)",
                ("01_Projects/NoteA.md", struct.pack("2f", 1.0, 0.0), "not-a-float"),
            )
            conn.commit()
        batch_sizes.clear()
        res_legacy = suggest_related_semantic(legacy_vault, target_path="01_Projects/Target.md")
        assert batch_sizes == [2]
        assert [s.target_path for s in res_legacy] == ["01_Projects/NoteA.md"]

    def test_semantic_batching_malformed_batch_empty_target_and_override_isolation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        evil_db = tmp_path / "evil.db"
        evil_db.write_bytes(b"not sqlite")
        monkeypatch.setenv("POWER_SEARCH_DB", str(evil_db))

        (tmp_path / "01_Projects").mkdir()
        target = tmp_path / "01_Projects" / "Target.md"
        target.write_text(
            "---\ntype: Project\ntitle: T\n"
            'description: "alpha shared keyword"\ntimestamp: 2026-01-01T00:00:00\n---\n\n'
            "alpha shared keyword\n",
            encoding="utf-8",
        )
        for i in range(10):
            (tmp_path / "01_Projects" / f"N{i}.md").write_text(
                "---\ntype: Project\ntitle: N\n"
                'description: "alpha shared keyword"\ntimestamp: 2026-01-01T00:00:00\n---\n\n'
                f"alpha shared keyword {i}\n",
                encoding="utf-8",
            )

        seen_chunks: list[int] = []

        class _ChunkedEmbedder:
            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                seen_chunks.append(len(texts))
                return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", lambda: _ChunkedEmbedder()
        )
        from power_framework.core.relations import suggest_related_semantic

        results = suggest_related_semantic(
            tmp_path, target_path="01_Projects/Target.md", max_results=3
        )
        assert seen_chunks == [8, 3]
        assert len(results) == 3

        # Returning None from embed_batch degrades cleanly to keyword fallback without crashing.
        class _BrokenBatch:
            def embed_batch(self, texts: list[str]):
                return None if texts else []

        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", lambda: _BrokenBatch()
        )
        fallback = suggest_related_semantic(
            tmp_path, target_path="01_Projects/Target.md", max_results=3
        )
        assert fallback
        assert all("Keyword" in s.reason or "Shared" in s.reason for s in fallback)

        # ActiveGenerationError falls back to legacy/re-embed without crashing.
        from power_framework.core.generation_index import ActiveGenerationError

        monkeypatch.setattr(
            "power_framework.core.generation_index.resolve_active_generation_path",
            lambda _v: (_ for _ in ()).throw(ActiveGenerationError("corrupt state")),
        )
        monkeypatch.setattr(
            "power_framework.core.embeddings.get_embedding_manager", lambda: _ChunkedEmbedder()
        )
        seen_chunks.clear()
        res_err = suggest_related_semantic(
            tmp_path, target_path="01_Projects/Target.md", max_results=2
        )
        assert len(res_err) == 2

        # Empty target note returns [] cleanly without arbitrary 0%-similarity matches.
        empty_note = tmp_path / "01_Projects" / "Empty.md"
        empty_note.write_text("", encoding="utf-8")
        assert suggest_related_semantic(tmp_path, target_path="01_Projects/Empty.md") == []
