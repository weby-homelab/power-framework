"""
CLI tests for P.O.W.E.R. commands: init, lint, index, ingest, search.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from power_framework.core import DEFAULT_SEARCH_MODE
from power_framework.core.cli import _configure_windows_utf8_streams, main

if TYPE_CHECKING:
    from pathlib import Path


class _ReconfigurableStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_windows_cli_configures_utf8_streams() -> None:
    stdout = _ReconfigurableStream()
    stderr = _ReconfigurableStream()

    with (
        patch("power_framework.core.cli.os.name", "nt"),
        patch.object(sys, "stdout", stdout),
        patch.object(sys, "stderr", stderr),
    ):
        _configure_windows_utf8_streams()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


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


def test_index_strict_reports_invalid_notes(tmp_path: Path) -> None:
    projects = tmp_path / "01_Projects"
    projects.mkdir(parents=True)
    (projects / "invalid.md").write_text(
        "---\n"
        "type: Project\n"
        'title: "Invalid"\n'
        'description: "bad resource"\n'
        'resource: "not-a-url"\n'
        "timestamp: 2026-08-02T00:00:00Z\n"
        "---\n\n# Invalid\n",
        encoding="utf-8",
    )
    with (
        patch.object(sys, "argv", ["power", "index", str(tmp_path), "--strict"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1
    assert (tmp_path / "index.md").exists()


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


def test_ingest_routes_to_domain_template(sample_vault: Path) -> None:
    (sample_vault / ".power").mkdir()
    (sample_vault / ".power" / "domains.yaml").write_text(
        """
version: 1
domains:
  - name: research
    path: 03_Resources/research
    template: 05_Templates/research.md
    rules:
      - keywords: [experiment]
    search_priority: [fts]
""",
        encoding="utf-8",
    )
    (sample_vault / "05_Templates").mkdir(exist_ok=True)
    (sample_vault / "05_Templates" / "research.md").write_text(
        '---\ntype: {type}\ntitle: "{title}"\n'
        'description: "{description}"\ntimestamp: {timestamp}\n---\n\n# {title}\n\nResearch template.\n',
        encoding="utf-8",
    )
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
                "Experiment Notes",
                "--description",
                "Research experiment",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    note = sample_vault / "03_Resources" / "research" / "experiment_notes.md"
    assert note.exists()
    assert "Research template." in note.read_text(encoding="utf-8")


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


def test_search_passes_shared_temporal_contract(sample_vault: Path) -> None:
    with (
        patch("power_framework.core.cli.format_search_results", return_value="No results"),
        patch("power_framework.core.cli.search_vault", return_value=[]) as search,
        patch.object(
            sys,
            "argv",
            [
                "power",
                "search",
                str(sample_vault),
                "Test",
                "--temporal-view",
                "historical",
                "--as-of",
                "2026-07-10",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert search.call_args.kwargs["temporal_view"] == "historical"
    assert search.call_args.kwargs["as_of"] == "2026-07-10"


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
            [
                "power",
                "ingest",
                str(vault),
                "--title",
                "Duplicate Test",
                "--type",
                "Project",
                "--description",
                "Desc",
            ],
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
            [
                "power",
                "ingest",
                str(vault),
                "--title",
                "Duplicate Test",
                "--type",
                "Project",
                "--description",
                "Desc",
            ],
        ),
        pytest.raises(SystemExit) as exc2,
    ):
        main()
    assert exc2.value.code == 1


class TestSyncCoverage:
    """A sync that drops notes must say so; --strict must refuse to pretend.

    Measured origin: on a real 2790-note vault, sync silently excluded 384
    notes (13.8%) and printed only what it indexed — the hole was found by
    querying the generation database directly.
    """

    @staticmethod
    def _make_vault(tmp_path):
        import argparse

        from power_framework.core.cli import _cmd_init

        vault = tmp_path / "vault"
        _cmd_init(argparse.Namespace(path=str(vault)))
        (vault / "03_Resources" / "good.md").write_text(
            '---\ntype: Resource\ntitle: "Good"\ndescription: "Valid note"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\nBody.\n",
            encoding="utf-8",
        )
        return vault

    @staticmethod
    def _sync(vault, strict):
        import argparse

        from power_framework.core.cli import _cmd_sync

        return _cmd_sync(
            argparse.Namespace(path=str(vault), fts_only=True, force=False, strict=strict)
        )

    def test_coverage_ledger_is_always_printed(self, tmp_path, caplog):
        import logging

        vault = self._make_vault(tmp_path)
        with caplog.at_level(logging.INFO):
            assert self._sync(vault, strict=False) == 0
        assert any("Coverage:" in r.getMessage() for r in caplog.records)

    def test_excluded_note_warns_but_does_not_fail_by_default(self, tmp_path, caplog):
        import logging

        vault = self._make_vault(tmp_path)
        (vault / "03_Resources" / "broken.md").write_text(
            "---\ntype: NotARealType\ntitle: Broken\n---\n\nBody.\n", encoding="utf-8"
        )
        with caplog.at_level(logging.INFO):
            assert self._sync(vault, strict=False) == 0
        rendered = [r.getMessage() for r in caplog.records]
        assert any("1 excluded" in m for m in rendered)
        assert any("not searchable" in m for m in rendered)

    def test_strict_fails_and_names_the_excluded_note(self, tmp_path, caplog):
        import logging

        vault = self._make_vault(tmp_path)
        (vault / "03_Resources" / "broken.md").write_text(
            "---\ntype: NotARealType\ntitle: Broken\n---\n\nBody.\n", encoding="utf-8"
        )
        with caplog.at_level(logging.INFO):
            assert self._sync(vault, strict=True) == 1
        rendered = [r.getMessage() for r in caplog.records]
        assert any("broken.md" in m for m in rendered)
        assert any("Strict sync failed" in m for m in rendered)

    def test_strict_passes_on_a_clean_vault(self, tmp_path):
        vault = self._make_vault(tmp_path)
        assert self._sync(vault, strict=True) == 0


class TestDoctor:
    """doctor must tell the truth the provider list cannot: what actually binds."""

    @staticmethod
    def _doctor(path):
        import argparse

        from power_framework.core.cli import _cmd_doctor

        return _cmd_doctor(argparse.Namespace(path=path))

    def test_doctor_runs_and_states_the_listed_vs_bound_caveat(self, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            assert self._doctor(None) == 0
        rendered = [r.getMessage() for r in caplog.records]
        assert any("P.O.W.E.R. Doctor" in m for m in rendered)
        assert any("onnxruntime" in m for m in rendered)
        # The doctrinal line: a listed provider proves nothing about loadability.
        assert any("compiled-in, not necessarily loadable" in m for m in rendered)
        assert any("Bound provider" in m for m in rendered)

    def test_doctor_missing_vault_fails(self, tmp_path, monkeypatch):
        from power_framework.core import cli as cli_mod

        monkeypatch.setattr(cli_mod, "_doctor_bind_check", lambda: None)
        assert self._doctor(str(tmp_path / "no-such-vault")) == 1

    def test_doctor_vault_reports_index_and_exclusions(self, tmp_path, caplog, monkeypatch):
        import argparse
        import logging

        from power_framework.core import cli as cli_mod
        from power_framework.core.cli import _cmd_init, _cmd_sync

        monkeypatch.setattr(cli_mod, "_doctor_bind_check", lambda: None)
        vault = tmp_path / "vault"
        _cmd_init(argparse.Namespace(path=str(vault)))
        (vault / "03_Resources" / "good.md").write_text(
            '---\ntype: Resource\ntitle: "Good"\ndescription: "Valid"\n'
            "timestamp: 2026-01-01T00:00:00\n---\n\nBody.\n",
            encoding="utf-8",
        )
        (vault / "03_Resources" / "broken.md").write_text(
            "---\ntype: NotARealType\ntitle: Broken\n---\n\nBody.\n", encoding="utf-8"
        )
        _cmd_sync(argparse.Namespace(path=str(vault), fts_only=True, force=False, strict=False))

        with caplog.at_level(logging.INFO):
            assert self._doctor(str(vault)) == 0
        rendered = [r.getMessage() for r in caplog.records]
        assert any("Search index" in m and "files" in m for m in rendered)
        assert any("Excluded now" in m and "1" in m for m in rendered)
        assert any("broken.md" in m for m in rendered)
