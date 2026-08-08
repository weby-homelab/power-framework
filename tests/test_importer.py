"""Regression coverage for fail-closed, foreign-frontmatter imports."""

from __future__ import annotations

import sys
from pathlib import Path  # noqa: TC003
from unittest.mock import patch

import pytest

from power_framework.core.cli import main
from power_framework.core.importer import (
    ImportPolicy,
    build_import_plan,
    format_import_report,
)
from power_framework.core.searcher import search_vault


def _write_note(path: Path, frontmatter: str, body: str) -> None:
    """Write one minimal Markdown note into a temporary source tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


def _foreign_source(tmp_path: Path) -> Path:
    """Build a source tree containing valid, foreign, and fatal metadata cases."""
    source = tmp_path / "source"
    _write_note(
        source / "valid.md",
        "type: Resource\ntitle: Valid\ndescription: Valid source\ntimestamp: 2026-01-01T00:00:00Z",
        "A valid source note.",
    )
    _write_note(
        source / "status.md",
        "type: Resource\ntitle: Foreign status\ndescription: Foreign status\n"
        "status: verified-external\ntimestamp: 2026-01-01T00:00:00Z",
        "Status quarantine body with unique-status-import-token.",
    )
    _write_note(
        source / "related.md",
        "type: Resource\ntitle: Foreign relation\ndescription: Foreign relation\n"
        "related:\n  - - Obsidian Link\ntimestamp: 2026-01-01T00:00:00Z",
        "Relation quarantine body with unique-related-import-token.",
    )
    _write_note(
        source / "fatal.md",
        "title: Missing type\ndescription: This remains fatal\ntimestamp: 2026-01-01T00:00:00Z",
        "This note must remain excluded.",
    )
    return source


def test_import_plan_is_write_free_and_policy_explicit(tmp_path: Path) -> None:
    """Verify strict and quarantine plans account for every source note pre-write."""
    source = _foreign_source(tmp_path)
    target = tmp_path / "vault" / "03_Resources"

    strict = build_import_plan(source, target, ImportPolicy.STRICT)
    assert strict.scanned == 4
    assert len(strict.candidates) == 1
    assert len(strict.excluded) == 3
    assert strict.quarantined == []
    assert not target.exists()

    quarantine = build_import_plan(source, target, ImportPolicy.QUARANTINE)
    assert quarantine.scanned == 4
    assert len(quarantine.will_write) == 3
    assert len(quarantine.quarantined) == 2
    assert quarantine.reason_counts["status: foreign status value"] == 1
    assert quarantine.reason_counts["related: foreign relation shape"] == 1
    assert quarantine.reason_counts["missing_type"] == 1
    assert not target.exists()

    report = format_import_report(quarantine, dry_run=True)
    assert "notes scanned: 4" in report
    assert "will quarantine: 2" in report
    assert "EXCLUDE fatal.md: missing_type" in report


def test_import_dry_run_does_not_mutate_vault(sample_vault: Path, tmp_path: Path) -> None:
    """Verify dry-run reports exclusions without creating notes or indexes."""
    source = _foreign_source(tmp_path)
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "import",
                str(source),
                "--into",
                "03_Resources",
                "--path",
                str(sample_vault),
                "--policy",
                "quarantine",
                "--dry-run",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 1
    assert not (sample_vault / "03_Resources" / "status.md").exists()
    assert not (sample_vault / "index.md").exists()


def test_quarantine_import_is_searchable_and_idempotent(sample_vault: Path, tmp_path: Path) -> None:
    """Verify quarantine apply preserves values, searchability, and rerun stability."""
    source = _foreign_source(tmp_path)
    args = [
        "power",
        "import",
        str(source),
        "--into",
        "03_Resources/imported",
        "--path",
        str(sample_vault),
        "--policy",
        "quarantine",
        "--allow-partial",
    ]
    with patch.object(sys, "argv", args), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0

    status_note = sample_vault / "03_Resources" / "imported" / "status.md"
    related_note = sample_vault / "03_Resources" / "imported" / "related.md"
    assert "x-status: verified-external" in status_note.read_text(encoding="utf-8")
    assert "x-related:" in related_note.read_text(encoding="utf-8")
    assert search_vault(sample_vault, "unique-status-import-token", mode="fts")
    assert search_vault(sample_vault, "unique-related-import-token", mode="fts")

    with (
        patch.object(sys, "argv", ["power", "index", str(sample_vault), "--strict"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0

    with patch.object(sys, "argv", args), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert len(list((sample_vault / "03_Resources" / "imported").glob("*.md"))) == 3
