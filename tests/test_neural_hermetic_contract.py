"""Mandatory no-cache neural contracts using injected deterministic doubles."""

from __future__ import annotations

import pytest

from power_framework.core.linter import run_rot_report
from power_framework.core.rot_scoring import ContentDedupDetector, ContradictionDetector

pytestmark = pytest.mark.neural_hermetic


def _write_note(vault, name: str, body: str, **metadata: str) -> None:
    lines = ["---", "type: Project", f'title: "{name}"']
    lines.extend(f"{key}: {value}" for key, value in metadata.items())
    lines.extend(["---", "", body])
    path = vault / "01_Projects" / name
    path.write_text("\n".join(lines), encoding="utf-8")


def test_embedding_manager_contract_uses_fake_tokenizer_and_session(fake_bge_manager) -> None:
    first = fake_bge_manager.embed("stable embedding input")
    second = fake_bge_manager.embed("stable embedding input")

    assert fake_bge_manager.active_provider == "CPUExecutionProvider"
    assert len(first) == fake_bge_manager.dimension == 1024
    assert first == second
    assert fake_bge_manager.embed("") == [0.0] * 1024


def test_embedding_manager_batch_contract_is_deterministic(fake_bge_manager) -> None:
    vectors = fake_bge_manager.embed_batch(["alpha", "", "beta"], batch_size=2)

    assert len(vectors) == 3
    assert vectors[1] == [0.0] * 1024
    assert vectors[0] != vectors[2]
    assert fake_bge_manager.embed_batch([]) == []


def test_dedup_contract_accepts_injected_embedder(tmp_path, deterministic_embedder) -> None:
    (tmp_path / "01_Projects").mkdir()
    body = "Shared content about deterministic semantic indexing and retrieval " * 3
    _write_note(tmp_path, "note_a.md", body + " alpha")
    _write_note(tmp_path, "note_b.md", body + " beta")

    pairs = ContentDedupDetector(threshold=0.75, embedder=deterministic_embedder).detect(tmp_path)

    assert len(pairs) == 1
    assert {pairs[0][0], pairs[0][1]} == {
        "01_Projects/note_a.md",
        "01_Projects/note_b.md",
    }
    assert pairs[0][2] >= 0.75


def test_contradiction_contract_accepts_injected_embedder(tmp_path, deterministic_embedder) -> None:
    (tmp_path / "01_Projects").mkdir()
    body = "The production service uses a deterministic reverse proxy configuration " * 3
    _write_note(tmp_path, "active.md", body, status="active")
    _write_note(tmp_path, "archived.md", body, status="archived")

    results = ContradictionDetector(
        similarity_threshold=0.75,
        embedder=deterministic_embedder,
    ).detect(tmp_path)

    assert len(results) == 1
    assert "status" in results[0][2].lower()


def test_rot_report_contract_executes_dedup_and_contradiction_paths(
    tmp_path, deterministic_embedder
) -> None:
    (tmp_path / "01_Projects").mkdir()
    body = "The service keeps a deterministic reverse proxy configuration for production " * 3
    _write_note(tmp_path, "active.md", body, status="active")
    _write_note(tmp_path, "archived.md", body, status="archived")
    report = run_rot_report(tmp_path, extended=True, embedder=deterministic_embedder)

    assert "CONTENT DEDUP" in report
    assert "SEMANTIC CONTRADICTIONS" in report
    assert "01_Projects/active.md" in report
    assert "01_Projects/archived.md" in report
