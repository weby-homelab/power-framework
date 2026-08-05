"""Tests for note rename propagation functionality."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from power_framework.core.cli import main
from power_framework.core.healer import propagate_rename

if TYPE_CHECKING:
    from pathlib import Path
from power_framework.core.parser import parse_frontmatter, read_file_content


def test_propagate_rename_dry_run(tmp_path: Path):
    """Verify that propagate_rename in dry_run mode does not modify notes on disk."""
    # Setup note A referencing note B
    note_a = tmp_path / "NoteA.md"
    note_a.write_text(
        "---\n"
        "type: Project\n"
        'title: "Note A"\n'
        'description: "A test note"\n'
        "related: [02_Areas/NoteB.md]\n"
        "timestamp: 2026-07-17T12:00:00Z\n"
        "---\n"
        "Content of note A\n"
    )

    # Perform rename propagation in dry_run mode
    updated_count, logs = propagate_rename(
        tmp_path, "02_Areas/NoteB.md", "02_Areas/NoteB_new.md", dry_run=True
    )

    assert updated_count == 1
    assert len(logs) == 1
    assert "NoteA.md" in logs[0]

    # Read NoteA again and verify it hasn't changed on disk
    content = read_file_content(note_a)
    assert "02_Areas/NoteB.md" in content
    assert "02_Areas/NoteB_new.md" not in content


def test_propagate_rename_live(tmp_path: Path):
    """Verify that propagate_rename actually modifies files on disk in live mode."""
    # Setup note A referencing note B (both as simple string and inside relation object)
    note_a = tmp_path / "NoteA.md"
    note_a.write_text(
        "---\n"
        "type: Project\n"
        'title: "Note A"\n'
        'description: "A test note"\n'
        "related: [02_Areas/NoteB.md, {path: 02_Areas/NoteB.md, relation: depends_on, "
        "confidence: 0.42, evidence: {source: human-review}}]\n"
        "timestamp: 2026-07-17T12:00:00Z\n"
        "---\n"
        "Content of note A\n"
    )

    # Perform live rename propagation
    updated_count, logs = propagate_rename(
        tmp_path, "02_Areas/NoteB.md", "02_Areas/NoteB_new.md", dry_run=False
    )

    assert updated_count == 1
    assert len(logs) == 1

    # Read NoteA and verify both references have been updated
    content = read_file_content(note_a)
    assert "02_Areas/NoteB.md" not in content
    assert "02_Areas/NoteB_new.md" in content
    assert 'path: "02_Areas/NoteB_new.md"' in content or "02_Areas/NoteB_new.md" in content
    parsed = parse_frontmatter(content)
    assert parsed is not None
    assert parsed["related"][1] == {
        "path": "02_Areas/NoteB_new.md",
        "relation": "depends_on",
        "confidence": 0.42,
        "evidence": {"source": "human-review"},
    }


def test_cli_rename_command(tmp_path: Path):
    """Verify CLI rename command physically renames file and propagates changes."""
    # Setup file structure
    (tmp_path / "02_Areas").mkdir(parents=True, exist_ok=True)
    note_b = tmp_path / "02_Areas" / "NoteB.md"
    source_content = (
        "---\n"
        "type: Area\n"
        'title: "Note B"\n'
        'description: "Target note"\n'
        "timestamp: 2026-07-17T12:00:00Z\n"
        "---\n"
        "Content of target note\n"
    )
    note_b.write_text(source_content)
    note_b_new = tmp_path / "02_Areas" / "NoteB_new.md"

    note_a = tmp_path / "NoteA.md"
    note_a.write_text(
        "---\n"
        "type: Project\n"
        'title: "Note A"\n'
        'description: "Referencing note"\n'
        "related: [02_Areas/NoteB.md]\n"
        "timestamp: 2026-07-17T12:00:00Z\n"
        "---\n"
        "Content of note A\n"
    )

    # Test Dry-Run CLI command
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "rename",
                str(tmp_path),
                "--old",
                "02_Areas/NoteB.md",
                "--new",
                "02_Areas/NoteB_new.md",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    # Dry run should not rename physically
    assert note_b.exists()
    assert not note_b_new.exists()

    # Test Live CLI command
    note_b_new.write_text("OLD TARGET CONTENT\n")
    original_replace = os.replace
    with (
        patch("power_framework.core.cli.os.replace", wraps=original_replace) as replace_mock,
        patch.object(
            sys,
            "argv",
            [
                "power",
                "rename",
                str(tmp_path),
                "--old",
                "02_Areas/NoteB.md",
                "--new",
                "02_Areas/NoteB_new.md",
                "--no-dry-run",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    # Live run should rename physically and overwrite the existing destination
    assert not note_b.exists()
    assert note_b_new.exists()
    assert read_file_content(note_b_new) == source_content
    assert read_file_content(note_b_new) != "OLD TARGET CONTENT\n"
    replace_mock.assert_any_call(note_b, note_b_new)

    # References in Note A should be updated on disk
    content = read_file_content(note_a)
    assert "02_Areas/NoteB_new.md" in content
