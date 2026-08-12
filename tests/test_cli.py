"""
CLI tests for P.O.W.E.R. commands: init, lint, index, ingest, search.
"""

from __future__ import annotations

import json
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


def test_control_plane_can_materialize_and_remove_optional_base(
    sample_vault: Path,
) -> None:
    user_note = sample_vault / "01_Projects" / "human-note.md"
    user_note.write_text("# human-owned\n", encoding="utf-8")

    with (
        patch.object(
            sys,
            "argv",
            ["power", "control-plane", str(sample_vault), "--apply", "--obsidian-base"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    assert (sample_vault / "POWER_STATUS.md").exists()
    assert (sample_vault / "POWER Control.base").exists()

    with (
        patch.object(
            sys,
            "argv",
            ["power", "control-plane", str(sample_vault), "--remove-obsidian-base"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    assert not (sample_vault / "POWER Control.base").exists()
    assert user_note.read_text(encoding="utf-8") == "# human-owned\n"


def test_doctor_json_uses_machine_contract(tmp_path: Path, capsys, monkeypatch) -> None:
    from power_framework.core import cli

    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda _path, *, probe_embedding: {
            "schema_version": 1,
            "command": "doctor",
            "status": "ok",
            "runtime": {},
            "embedding": {},
            "vault": None,
            "issues": [],
            "exit_code": 0,
        },
    )
    with (
        patch.object(sys, "argv", ["power", "doctor", "--json", str(tmp_path)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1


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


def test_index_strict_reports_foreign_nested_catalog(tmp_path: Path) -> None:
    nested = tmp_path / "01_Projects" / "nested"
    nested.mkdir(parents=True)
    (nested / "Note.md").write_text(
        "---\n"
        "type: Project\n"
        'title: "Note"\n'
        'description: "Nested note"\n'
        "timestamp: 2026-08-09T00:00:00Z\n"
        "---\n\n# Note\n",
        encoding="utf-8",
    )
    foreign = nested / "_index.md"
    foreign.write_text("# Hand-maintained catalog\n", encoding="utf-8")

    with (
        patch.object(sys, "argv", ["power", "index", str(tmp_path), "--strict"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 1
    assert foreign.read_text(encoding="utf-8") == "# Hand-maintained catalog\n"


def _add_invalid_note(vault: Path) -> Path:
    invalid = vault / "03_Resources" / "invalid_sync.md"
    invalid.write_text("# no frontmatter\n", encoding="utf-8")
    return invalid


def test_sync_clean_vault_has_zero_exit_and_coverage_ledger(
    sample_vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level("INFO"),
        patch.object(
            sys,
            "argv",
            ["power", "sync", str(sample_vault), "--fts-only"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert any(
        "Coverage: 5 notes scanned, 5 indexed, 0 excluded." in r.message for r in caplog.records
    )


def test_sync_default_fails_closed_and_names_excluded_note(
    sample_vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    invalid = _add_invalid_note(sample_vault)
    with (
        caplog.at_level("INFO"),
        patch.object(
            sys,
            "argv",
            ["power", "sync", str(sample_vault), "--fts-only"],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 1
    messages = [record.message for record in caplog.records]
    assert any(
        "Coverage: 6 notes scanned, 5 indexed, 1 excluded." in message for message in messages
    )
    assert any("Exclusion reasons: invalid_metadata=1" in message for message in messages)
    assert any(
        f"excluded: {invalid.relative_to(sample_vault).as_posix()} (invalid_metadata)" in message
        for message in messages
    )


def test_sync_strict_fails_closed_and_allow_partial_is_explicit(
    sample_vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _add_invalid_note(sample_vault)
    with (
        caplog.at_level("INFO"),
        patch.object(
            sys,
            "argv",
            ["power", "sync", str(sample_vault), "--fts-only", "--strict"],
        ),
        pytest.raises(SystemExit) as strict_exc,
    ):
        main()
    assert strict_exc.value.code == 1

    caplog.clear()
    with (
        caplog.at_level("INFO"),
        patch.object(
            sys,
            "argv",
            ["power", "sync", str(sample_vault), "--fts-only", "--allow-partial"],
        ),
        pytest.raises(SystemExit) as partial_exc,
    ):
        main()
    assert partial_exc.value.code == 0
    assert any(
        "Continuing because --allow-partial was requested." in r.message for r in caplog.records
    )


def test_sync_rejects_contradictory_coverage_flags(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "sync",
                str(sample_vault),
                "--fts-only",
                "--strict",
                "--allow-partial",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 2


def test_sync_dirty_vault_has_no_silent_omissions(
    sample_vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Exercise the frozen P5.0.1 cases in one real CLI coverage receipt."""
    unicode_note = sample_vault / "03_Resources" / "Україна — AutoCAD.md"
    unicode_content = (
        "---\n"
        "type: Resource\n"
        'title: "Український AutoCAD довідник"\n'
        'description: "CRLF and backslash regression"\n'
        "timestamp: 2026-01-01T00:00:00+00:00\n"
        "---\n\n"
        "dirty-coverage-token\n"
        "MTEXT codes: \\P and \\fArial\n"
        "Windows path: C:\\Users\\Alice\\Vault\n"
    )
    unicode_note.write_bytes(unicode_content.replace("\n", "\r\n").encode("utf-8"))

    invalid_notes = {
        "foreign-status.md": (
            "---\n"
            "type: Project\n"
            "title: Foreign status\n"
            "description: Foreign lifecycle vocabulary\n"
            "status: verified-external\n"
            "timestamp: 2026-01-01T00:00:00+00:00\n"
            "---\n\nBody.\n"
        ),
        "wikilink-related.md": (
            "---\n"
            "type: Project\n"
            "title: Wikilink relation\n"
            "description: Obsidian wikilink relation\n"
            "related: [[Назва]]\n"
            "timestamp: 2026-01-01T00:00:00+00:00\n"
            "---\n\nBody.\n"
        ),
        "malformed-backslash.md": (
            "---\n"
            "type: Resource\n"
            'title: "MTEXT \\q"\n'
            'description: "Malformed user escape"\n'
            "timestamp: 2026-01-01T00:00:00+00:00\n"
            "---\n\nBody.\n"
        ),
    }
    invalid_paths = []
    for filename, content in invalid_notes.items():
        path = sample_vault / "03_Resources" / filename
        path.write_text(content, encoding="utf-8")
        invalid_paths.append(path.relative_to(sample_vault).as_posix())

    with (
        caplog.at_level("INFO"),
        patch.object(
            sys,
            "argv",
            ["power", "sync", str(sample_vault), "--fts-only"],
        ),
        pytest.raises(SystemExit) as strict_exc,
    ):
        main()

    assert strict_exc.value.code == 1
    messages = [record.message for record in caplog.records]
    assert any("Coverage: 9 notes scanned, 6 indexed, 3 excluded." in m for m in messages)
    assert any("Exclusion reasons: invalid_metadata=3" in m for m in messages)
    for rel_path in invalid_paths:
        assert any(f"excluded: {rel_path} (invalid_metadata)" in m for m in messages)

    from power_framework.core.searcher import search_vault

    assert search_vault(sample_vault, "dirty-coverage-token", mode="fts")

    caplog.clear()
    with (
        caplog.at_level("INFO"),
        patch.object(
            sys,
            "argv",
            ["power", "sync", str(sample_vault), "--fts-only", "--allow-partial"],
        ),
        pytest.raises(SystemExit) as partial_exc,
    ):
        main()

    assert partial_exc.value.code == 0
    partial_messages = [record.message for record in caplog.records]
    assert any("Continuing because --allow-partial was requested." in m for m in partial_messages)
    assert all(
        any(f"excluded: {rel_path} (invalid_metadata)" in m for m in partial_messages)
        for rel_path in invalid_paths
    )


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


def test_memory_propose_rejects_content_in_argv(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "memory",
                "propose",
                str(sample_vault),
                "01_Projects/secret.md",
                "secret-content",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 1


def test_memory_propose_reads_content_from_file(sample_vault: Path, tmp_path: Path) -> None:
    content_file = tmp_path / "proposal.md"
    content_file.write_text(
        '---\ntype: Project\ntitle: "File proposal"\n'
        'description: "stdin/file boundary"\ntimestamp: 2026-08-11T00:00:00Z\n---\n',
        encoding="utf-8",
    )
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "memory",
                "propose",
                str(sample_vault),
                "01_Projects/file-proposal.md",
                "--content-file",
                str(content_file),
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0


def test_memory_apply_rejects_proposal_json_in_argv(sample_vault: Path) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "memory",
                "apply",
                str(sample_vault),
                '{"proposal_id":"argv-secret"}',
                "--approved",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 1


def test_search_uses_canonical_default_mode(sample_vault: Path) -> None:
    with (
        patch("power_framework.core.application.search_vault", return_value=[]) as search,
        patch.object(sys, "argv", ["power", "search", str(sample_vault), "Test"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert search.call_args.kwargs["mode"] == DEFAULT_SEARCH_MODE


def test_search_passes_shared_temporal_contract(sample_vault: Path) -> None:
    with (
        patch("power_framework.core.application.search_vault", return_value=[]) as search,
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
    assert "3.5.0" in captured.out


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
    from power_framework.core.searcher import search_vault

    assert search_vault(vault, "duplicate", mode="fts")[0].rel_path == (
        "01_Projects/duplicate_test.md"
    )

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


def test_memory_apply_cli_publishes_search_projection(sample_vault, capsys) -> None:
    from unittest.mock import patch

    from power_framework.core.cli import main
    from power_framework.core.memory_api import propose_change
    from power_framework.core.searcher import search_vault

    marker = "cli-closed-mutation-marker"
    proposal = propose_change(
        sample_vault,
        "01_Projects/CliTransaction.md",
        '---\ntype: Project\ntitle: "CLI transaction"\ndescription: "CLI transaction"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n'
        + marker
        + "\n",
    )
    proposal_file = sample_vault / "proposal.json"
    proposal_file.write_text(json.dumps(proposal), encoding="utf-8")

    with (
        patch(
            "sys.argv",
            [
                "power",
                "memory",
                "apply",
                str(sample_vault),
                "--proposal-file",
                str(proposal_file),
                "--approved",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert search_vault(sample_vault, marker, mode="fts")[0].rel_path == (
        "01_Projects/CliTransaction.md"
    )
    assert "search_generation" in capsys.readouterr().out


def test_handoff_cli_persists_and_resumes_packet(sample_vault, capsys) -> None:
    from unittest.mock import patch

    commands = [
        [
            "power",
            "handoff",
            "create",
            str(sample_vault),
            "--task-id",
            "cli-handoff",
            "--objective",
            "Continue the verified workflow",
            "--owner",
            "human",
            "--actor",
            "agent-a",
        ],
        [
            "power",
            "handoff",
            "resume",
            str(sample_vault),
            "--task-id",
            "cli-handoff",
            "--idempotency-key",
            "cli-resume-1",
            "--actor",
            "agent-b",
        ],
    ]
    for argv in commands:
        with patch.object(sys, "argv", argv), pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["state"] == "working"
    assert result["checkpoint"] == 1
    assert (sample_vault / ".power" / "work-packets" / "cli-handoff.md").exists()


class TestFtsOnlyDenseGuard:
    """`--fts-only` must not silently discard an existing dense index.

    Reproduced on a real vault: an fts-only refresh after editing notes replaced
    a 19 893-chunk generation with a chunkless one, and every dense search mode
    then raised DenseIndexUnavailableError.
    """

    NOTE = (
        '---\ntype: Resource\ntitle: "N"\ndescription: "note"\n'
        "timestamp: 2026-01-01T00:00:00\n---\n\n{body}\n"
    )

    @staticmethod
    def _sync(vault, *, fts_only, accept_dense_loss=False):
        import argparse

        from power_framework.core.cli import _cmd_sync

        return _cmd_sync(
            argparse.Namespace(
                path=str(vault),
                fts_only=fts_only,
                force=False,
                strict=False,
                allow_partial=True,
                accept_dense_loss=accept_dense_loss,
            )
        )

    def _vault_with_dense(self, tmp_path):
        import argparse

        from power_framework.core.cli import _cmd_init

        vault = tmp_path / "vault"
        _cmd_init(argparse.Namespace(path=str(vault)))
        note = vault / "03_Resources" / "n.md"
        note.write_text(self.NOTE.format(body="Body one."), encoding="utf-8")
        self._sync(vault, fts_only=False)
        return vault, note

    def test_fts_only_refuses_to_discard_an_existing_dense_index(self, tmp_path, caplog):
        import logging

        from power_framework.core.generation_index import active_dense_chunk_count

        vault, note = self._vault_with_dense(tmp_path)
        assert active_dense_chunk_count(vault) > 0

        note.write_text(self.NOTE.format(body="Body EDITED."), encoding="utf-8")
        with caplog.at_level(logging.INFO):
            assert self._sync(vault, fts_only=True) == 1
        assert any("Refusing --fts-only" in r.getMessage() for r in caplog.records)
        assert active_dense_chunk_count(vault) > 0, "the dense index must survive a refusal"

    def test_explicit_opt_in_still_allows_the_downgrade(self, tmp_path):
        from power_framework.core.generation_index import active_dense_chunk_count

        vault, note = self._vault_with_dense(tmp_path)
        note.write_text(self.NOTE.format(body="Body EDITED."), encoding="utf-8")
        assert self._sync(vault, fts_only=True, accept_dense_loss=True) == 0
        assert active_dense_chunk_count(vault) == 0

    def test_fts_only_is_unaffected_when_there_is_no_dense_index(self, tmp_path):
        import argparse

        from power_framework.core.cli import _cmd_init

        vault = tmp_path / "fresh"
        _cmd_init(argparse.Namespace(path=str(vault)))
        (vault / "03_Resources" / "n.md").write_text(
            self.NOTE.format(body="Body."), encoding="utf-8"
        )
        assert self._sync(vault, fts_only=True) == 0


class TestCachePrune:
    """Prune must require proof that a vault is gone, never assume it."""

    @staticmethod
    def _make_vault(tmp_path, name):
        import argparse

        from power_framework.core.cli import _cmd_init
        from power_framework.core.vault_storage import vault_cache_dir

        vault = tmp_path / name
        _cmd_init(argparse.Namespace(path=str(vault)))
        return vault, vault_cache_dir(vault)

    def test_cache_dir_records_its_source_vault(self, tmp_path, monkeypatch):
        from pathlib import Path

        from power_framework.core import vault_storage
        from power_framework.core.vault_storage import read_cache_source

        monkeypatch.setattr(
            vault_storage, "get_cache_dir", lambda *, create=True: tmp_path / "cache"
        )
        vault, namespace = self._make_vault(tmp_path, "v1")
        source = read_cache_source(namespace)
        assert source is not None
        assert Path(source["vault_path"]) == vault.resolve()

    def test_live_vault_is_never_pruned(self, tmp_path, monkeypatch):
        from power_framework.core import vault_storage

        monkeypatch.setattr(
            vault_storage, "get_cache_dir", lambda *, create=True: tmp_path / "cache"
        )
        _vault, namespace = self._make_vault(tmp_path, "live")
        report = vault_storage.prune_vault_caches(dry_run=False)
        assert namespace.is_dir()
        assert "live 1" in report

    def test_deleted_vault_is_pruned(self, tmp_path, monkeypatch):
        import shutil

        from power_framework.core import vault_storage

        monkeypatch.setattr(
            vault_storage, "get_cache_dir", lambda *, create=True: tmp_path / "cache"
        )
        vault, namespace = self._make_vault(tmp_path, "doomed")
        shutil.rmtree(vault)
        assert namespace.is_dir()

        preview = vault_storage.prune_vault_caches(dry_run=True)
        assert "Would remove: 1" in preview
        assert namespace.is_dir(), "dry run must not delete"

        vault_storage.prune_vault_caches(dry_run=False)
        assert not namespace.exists()

    def test_unattributable_namespace_is_kept_unless_asked(self, tmp_path, monkeypatch):
        from power_framework.core import vault_storage

        monkeypatch.setattr(
            vault_storage, "get_cache_dir", lambda *, create=True: tmp_path / "cache"
        )
        legacy = tmp_path / "cache" / "vaults" / "00000000-0000-4000-8000-000000000000"
        legacy.mkdir(parents=True)
        (legacy / "search.db").write_bytes(b"x")

        vault_storage.prune_vault_caches(dry_run=False)
        assert legacy.is_dir(), "a namespace with no source record is not proof of death"

        vault_storage.prune_vault_caches(dry_run=False, include_unknown=True)
        assert not legacy.exists()

    def test_malformed_source_is_unknown_without_touching_vault(self, tmp_path, monkeypatch):
        from power_framework.core import vault_storage

        monkeypatch.setattr(
            vault_storage, "get_cache_dir", lambda *, create=False: tmp_path / "cache"
        )
        vault = tmp_path / "uninitialized"
        vault.mkdir()
        namespace = tmp_path / "cache" / "vaults" / "00000000-0000-4000-8000-000000000000"
        namespace.mkdir(parents=True)
        (namespace / "source.json").write_text(
            json.dumps(
                {
                    "vault_id": namespace.name,
                    "vault_path": "",
                    "schema_version": 1,
                }
            ),
            encoding="utf-8",
        )

        result = vault_storage.classify_cache_namespaces()
        assert result[0].verdict == "unknown"
        assert not (vault / ".power").exists()

    def test_missing_vault_identity_is_unknown_without_creating_one(self, tmp_path, monkeypatch):
        from power_framework.core import vault_storage

        monkeypatch.setattr(
            vault_storage, "get_cache_dir", lambda *, create=False: tmp_path / "cache"
        )
        vault = tmp_path / "missing-identity"
        vault.mkdir()
        namespace = tmp_path / "cache" / "vaults" / "00000000-0000-4000-8000-000000000000"
        namespace.mkdir(parents=True)
        (namespace / "source.json").write_text(
            json.dumps(
                {
                    "vault_id": namespace.name,
                    "vault_path": str(vault),
                    "schema_version": 1,
                }
            ),
            encoding="utf-8",
        )

        result = vault_storage.classify_cache_namespaces()
        assert result[0].verdict == "unknown"
        assert result[0].detail == "vault identity missing"
        assert not (vault / ".power").exists()
