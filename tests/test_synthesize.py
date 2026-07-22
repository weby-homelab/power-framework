"""Tests for synthesize_session_ingest."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from power_framework.core.synthesize import synthesize_session_ingest


def test_synthesize_session_ingest_success(tmp_path):
    # Initialize vault structure
    (tmp_path / "01_Projects").mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "log.md"
    log_file.write_text("# Log\n", encoding="utf-8")

    with patch("power_framework.core.synthesize.run_generate_hierarchical_index", return_value="Index updated"), \
         patch("power_framework.core.synthesize.run_lint_report", return_value="Lint clean"):
        report = synthesize_session_ingest(
            name="01_Projects/session1.md",
            title="Session 1",
            description="First session synthesis",
            content="Session notes content.",
            vault_path=tmp_path,
        )
        assert "synthesized and ingested" in report
        assert (tmp_path / "01_Projects" / "session1.md").exists()


def test_synthesize_session_ingest_exists_error(tmp_path):
    note = tmp_path / "existing.md"
    note.write_text("content", encoding="utf-8")
    with pytest.raises(FileExistsError):
        synthesize_session_ingest(
            name="existing.md",
            title="Title",
            description="Desc",
            content="Content",
            vault_path=tmp_path,
        )
