"""Tests for semantic ROT: dense embedding dedup and contradiction detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from power_framework.core.rot_scoring import (
    ContradictionDetector,
    _dense_cosine_similarity,
)

if TYPE_CHECKING:
    from pathlib import Path


LONG_BODY = (
    "The server infrastructure should use Nginx as the primary reverse proxy "
    "for handling all incoming HTTP and HTTPS traffic to backend services."
)
DIFF_BODY = (
    "Python is a general-purpose programming language commonly used for "
    "web development and data science applications with a large ecosystem."
)
PHYS_BODY = (
    "Quantum physics is the branch of science that studies the behavior of "
    "matter and energy at the atomic and subatomic levels using wave functions."
)


class TestDenseCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        assert _dense_cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        assert _dense_cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_partial_similarity(self):
        vec_a = [1.0, 0.0]
        vec_b = [1.0, 1.0]
        sim = _dense_cosine_similarity(vec_a, vec_b)
        assert 0.5 < sim < 1.0

    def test_zero_vector(self):
        vec_a = [0.0, 0.0]
        vec_b = [1.0, 0.0]
        assert _dense_cosine_similarity(vec_a, vec_b) == 0.0


class TestContentDedupDetectorEmbedding:
    """Verify ContentDedupDetector works with EmbeddingManager."""

    def test_detects_similar_content(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()

        note_a = vault / "01_Projects" / "note_a.md"
        note_a.write_text(
            '---\ntype: Project\ntitle: "Note A"\n'
            'description: "First note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "Python programming language is widely used for building web applications "
            "and data science projects. It has a large ecosystem of libraries."
        )

        note_b = vault / "01_Projects" / "note_b.md"
        note_b.write_text(
            '---\ntype: Project\ntitle: "Note B"\n'
            'description: "Second note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "Python programming language is commonly used for web development "
            "and data science tasks. It has many available libraries."
        )

        from power_framework.core.rot_scoring import ContentDedupDetector

        detector = ContentDedupDetector(threshold=0.5)
        pairs = detector.detect(vault)
        assert len(pairs) >= 1
        assert any("note_a" in p[0] or "note_a" in p[1] for p in pairs)

    def test_different_content_not_deduped(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()

        note_a = vault / "01_Projects" / "note_a.md"
        note_a.write_text(
            '---\ntype: Project\ntitle: "Note A"\n'
            'description: "First note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "Python programming language is used for web development and data science."
        )

        note_b = vault / "01_Projects" / "note_b.md"
        note_b.write_text(
            '---\ntype: Project\ntitle: "Note B"\n'
            'description: "Second note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\n"
            "Quantum physics explores the behavior of matter at the atomic "
            "and subatomic level through mathematical models."
        )

        from power_framework.core.rot_scoring import ContentDedupDetector

        detector = ContentDedupDetector(threshold=0.75)
        pairs = detector.detect(vault)
        assert len(pairs) == 0


class TestContradictionDetectorMetadataFallback:
    """Test ContradictionDetector fallback (no OPENROUTER_API_KEY)."""

    def test_conflicting_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vault = self._make_pair_vault(
            tmp_path,
            body_a=LONG_BODY,
            fm_a={"type": "Project", "status": "active"},
            body_b=LONG_BODY,
            fm_b={"type": "Project", "status": "archived"},
        )
        detector = ContradictionDetector(similarity_threshold=0.5)
        results = detector.detect(vault)
        assert len(results) >= 1
        assert "status" in results[0][2].lower()

    def test_different_owners(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vault = self._make_pair_vault(
            tmp_path,
            body_a=LONG_BODY,
            fm_a={"type": "Project", "owner": "alice"},
            body_b=LONG_BODY,
            fm_b={"type": "Project", "owner": "bob"},
        )
        detector = ContradictionDetector(similarity_threshold=0.5)
        results = detector.detect(vault)
        assert len(results) >= 1
        assert "owner" in results[0][2].lower()

    def test_opposite_expiry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vault = self._make_pair_vault(
            tmp_path,
            body_a=LONG_BODY,
            fm_a={"type": "Project", "expiry": "2020-01-01"},
            body_b=LONG_BODY,
            fm_b={"type": "Project", "expiry": "2030-01-01"},
        )
        detector = ContradictionDetector(similarity_threshold=0.5)
        results = detector.detect(vault)
        assert len(results) >= 1
        assert "expir" in results[0][2].lower()

    def test_conflicting_priorities(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vault = self._make_pair_vault(
            tmp_path,
            body_a=LONG_BODY,
            fm_a={"type": "Project", "priority": "high"},
            body_b=LONG_BODY,
            fm_b={"type": "Project", "priority": "low"},
        )
        detector = ContradictionDetector(similarity_threshold=0.5)
        results = detector.detect(vault)
        assert len(results) >= 1
        assert "priorit" in results[0][2].lower()

    def test_no_false_positive(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vault = self._make_pair_vault(
            tmp_path,
            body_a=DIFF_BODY,
            fm_a={"type": "Project", "status": "active", "owner": "alice"},
            body_b=PHYS_BODY,
            fm_b={"type": "Project", "status": "active", "owner": "alice"},
        )
        detector = ContradictionDetector(similarity_threshold=0.95)
        results = detector.detect(vault)
        assert len(results) == 0

    @staticmethod
    def _write_note(
        vault: Path,
        name: str,
        body: str,
        frontmatter: dict | None = None,
    ) -> Path:
        if frontmatter is None:
            frontmatter = {"type": "Project"}
        fm_lines = ["---"]
        for k, v in frontmatter.items():
            fm_lines.append(f"{k}: {v}")
        fm_lines.append("---")
        content = "\n".join(fm_lines) + "\n\n" + body
        path = vault / name
        path.write_text(content)
        return path

    @classmethod
    def _make_pair_vault(
        cls,
        tmp_path: Path,
        body_a: str,
        fm_a: dict,
        body_b: str,
        fm_b: dict,
    ) -> Path:
        vault = tmp_path / "contra_vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()
        cls._write_note(vault / "01_Projects", "note_a.md", body_a, fm_a)
        cls._write_note(vault / "01_Projects", "note_b.md", body_b, fm_b)
        return vault


class TestContradictionDetectorLLM:
    """Test ContradictionDetector with mocked LLM call."""

    LLM_BODY_A = (
        "The production web server configuration must use port 8080 for all "
        "incoming HTTP traffic and port 8443 for HTTPS traffic."
    )
    LLM_BODY_B = (
        "The production web server configuration must use port 9090 for all "
        "incoming HTTP traffic and port 9443 for HTTPS traffic."
    )
    LLM_COMPAT_A = (
        "Python is a high-level programming language that is widely used "
        "for building web applications and data science projects."
    )
    LLM_COMPAT_B = (
        "Python can be used for web development frameworks like Django "
        "and Flask, as well as data science libraries like NumPy."
    )

    def test_llm_detects_contradiction(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
        vault = self._make_simple_vault(tmp_path, self.LLM_BODY_A, self.LLM_BODY_B)

        detector = ContradictionDetector(similarity_threshold=0.5)

        import urllib.request

        def mock_urlopen(req, **kwargs):
            class MockResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    import json

                    return json.dumps(
                        {
                            "choices": [
                                {
                                    "message": {
                                        "content": "YES: Port configuration conflict (8080 vs 9090)"
                                    }
                                }
                            ]
                        }
                    ).encode("utf-8")

                @property
                def status(self):
                    return 200

            return MockResponse()

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
        results = detector.detect(vault)
        assert len(results) >= 1
        assert "port" in results[0][2].lower() or "conflict" in results[0][2].lower()

    def test_llm_no_contradiction(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
        vault = self._make_simple_vault(tmp_path, self.LLM_COMPAT_A, self.LLM_COMPAT_B)

        detector = ContradictionDetector(similarity_threshold=0.5)

        import urllib.request

        def mock_urlopen(req, **kwargs):
            class MockResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    import json

                    return json.dumps({"choices": [{"message": {"content": "NO"}}]}).encode("utf-8")

                @property
                def status(self):
                    return 200

            return MockResponse()

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
        results = detector.detect(vault)
        assert len(results) == 0

    @staticmethod
    def _make_simple_vault(tmp_path: Path, body_a: str, body_b: str) -> Path:
        vault = tmp_path / "llm_vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()
        for name, body in [("note_a.md", body_a), ("note_b.md", body_b)]:
            content = '---\ntype: Project\ntitle: "Note"\n---\n\n' + body
            (vault / "01_Projects" / name).write_text(content)
        return vault


class TestRotReportSemanticContradictions:
    """Test that run_rot_report includes contradictions section."""

    def test_report_contains_contradictions_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from power_framework.core.linter import run_rot_report

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        vault = tmp_path / "rep_vault"
        vault.mkdir()
        (vault / "01_Projects").mkdir()

        for name, status in [("a.md", "active"), ("b.md", "archived")]:
            content = (
                "---\ntype: Project\n"
                f'status: {status}\ntitle: "Note"\n---\n\n'
                "The server should use Nginx for reverse proxy configuration "
                "and handle SSL termination at the edge."
            )
            (vault / "01_Projects" / name).write_text(content)

        report = run_rot_report(vault, extended=True)
        assert "SEMANTIC CONTRADICTIONS" in report
        assert "01_Projects/a.md" in report
        assert "01_Projects/b.md" in report
