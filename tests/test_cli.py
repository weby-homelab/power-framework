"""
CLI tests for P.O.W.E.R. commands: init, lint, index, ingest, search.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from power_framework.core import DEFAULT_SEARCH_MODE
from power_framework.core.cli import main

if TYPE_CHECKING:
    from pathlib import Path


def test_init_creates_vault(tmp_path: Path) -> None:
    vault = tmp_path / "new_vault"
    with patch.object(sys, "argv", ["power", "init", str(vault)]), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert vault.exists()
    assert (vault / "01_Projects").is_dir()
    assert (vault / "index.md").exists()
    assert (vault / "log.md").exists()
    assert (vault / "05_Templates" / "default.md").exists()


def test_init_fails_on_nonempty(tmp_path: Path) -> None:
    vault = tmp_path / "nonempty"
    vault.mkdir()
    (vault / "existing.md").write_text("existing")
    with patch.object(sys, "argv", ["power", "init", str(vault)]), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_lint_valid_vault(sample_vault: Path) -> None:
    with (
        patch.object(sys, "argv", ["power", "lint", str(sample_vault)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0


def test_lint_issues_return_nonzero(vault_with_issues: Path) -> None:
    with (
        patch.object(sys, "argv", ["power", "lint", str(vault_with_issues)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


def test_lint_missing_vault(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    with (
        patch.object(sys, "argv", ["power", "lint", str(missing)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


def test_index_generates_files(sample_vault: Path) -> None:
    with (
        patch.object(sys, "argv", ["power", "index", str(sample_vault)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    assert (sample_vault / "index.md").exists()
    assert (sample_vault / "01_Projects" / "_index.md").exists()


def test_index_missing_vault(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    with (
        patch.object(sys, "argv", ["power", "index", str(missing)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


def test_ingest_creates_note(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "ingest",
                str(sample_vault),
                "--type",
                "Project",
                "--title",
                "New Test Note",
                "--description",
                "A test note created by ingest",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    note = sample_vault / "01_Projects" / "new_test_note.md"
    assert note.exists()
    content = note.read_text(encoding="utf-8")
    assert "New Test Note" in content
    assert "type: Project" in content


def test_ingest_with_tags(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "ingest",
                str(sample_vault),
                "--type",
                "Resource",
                "--title",
                "Test Resource",
                "--description",
                "A resource with tags",
                "--tags",
                "test",
                "demo",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    note = sample_vault / "03_Resources" / "test_resource.md"
    assert note.exists()


def test_ingest_missing_vault(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "ingest",
                str(missing),
                "--type",
                "Project",
                "--title",
                "Fail",
                "--description",
                "Should fail",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


def test_search_returns_results(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["power", "search", str(sample_vault), "Test", "--mode", "fts"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0


def test_search_uses_canonical_default_mode(sample_vault: Path) -> None:
    with (
        patch("power_framework.core.cli.format_search_results", return_value="No results"),
        patch("power_framework.core.cli.search_vault", return_value=[]) as search,
        patch.object(sys, "argv", ["power", "search", str(sample_vault), "Test"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert search.call_args.kwargs["mode"] == DEFAULT_SEARCH_MODE


def test_search_no_results(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["power", "search", str(sample_vault), "XyzzyNonExistent", "--mode", "fts"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0


def test_search_missing_vault(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    with (
        patch.object(
            sys,
            "argv",
            ["power", "search", str(missing), "test"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


def test_version_flag(capsys: pytest.CaptureFixture) -> None:
    with patch.object(sys, "argv", ["power", "--version"]), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "power" in captured.out


def test_no_command_shows_help(capsys: pytest.CaptureFixture) -> None:
    with patch.object(sys, "argv", ["power"]), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_ingest_duplicate_returns_1(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    with patch.object(sys, "argv", ["power", "init", str(vault)]), pytest.raises(SystemExit):
        main()

    # First ingest
    with (
        patch.object(
            sys,
            "argv",
            ["power", "ingest", str(vault), "--title", "Duplicate Test", "--type", "Project", "--description", "Desc"],
        ),
        pytest.raises(SystemExit) as exc1,
    ):
        main()
    assert exc1.value.code == 0

    # Second ingest without --overwrite
    with (
        patch.object(
            sys,
            "argv",
            ["power", "ingest", str(vault), "--title", "Duplicate Test", "--type", "Project", "--description", "Desc"],
        ),
        pytest.raises(SystemExit) as exc2,
    ):
        main()
    assert exc2.value.code == 1

