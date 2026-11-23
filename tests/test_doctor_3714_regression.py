"""Maintenance regressions for legacy FTS-only doctor diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from jsonschema import validate

from power_framework.core import doctor
from power_framework.core.db import _init_db
from tests.mcp_test_client import stdio_session


def make_index(tmp_path: Path, name: str, *, without_dense: bool) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    folder = vault / "01_Projects"
    folder.mkdir(parents=True)
    body = (
        "---\ntype: Project\ntitle: Fixture\ndescription: Synthetic fixture\n"
        "timestamp: 2026-01-01T00:00:00\n---\n\nfixturequartz\n"
    )
    (folder / "note.md").write_text(body, encoding="utf-8")
    database = tmp_path / name
    with closing(sqlite3.connect(database)) as connection:
        _init_db(connection)
        connection.execute(
            "INSERT INTO file_metadata (rel_path, mtime) VALUES (?, ?)",
            ("01_Projects/note.md", 1.0),
        )
        connection.execute(
            "INSERT INTO fts_notes (title, tags, description, content, rel_path, note_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Fixture", "", "Synthetic fixture", body, "01_Projects/note.md", "Project"),
        )
        if without_dense:
            connection.execute("DROP TABLE chunk_embeddings")
        connection.commit()
        assert connection.execute(
            "SELECT COUNT(*) FROM fts_notes WHERE fts_notes MATCH ?", ("fixturequartz",)
        ).fetchone() == (1,)
    return vault, database


@pytest.mark.parametrize(
    ("name", "without_dense"),
    [("relative index.db", True), ("relative ?# %.db", False)],
)
def test_doctor_preserves_fts_and_relative_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, without_dense: bool
) -> None:
    vault, database = make_index(tmp_path, name, without_dense=without_dense)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POWER_SEARCH_DB", name)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    report = doctor.run_doctor(vault)
    assert report["schema_version"] == 1
    assert report["vault"]["index_state"] == "legacy_database"
    assert report["vault"]["database_path"] == name
    assert report["vault"]["indexed_notes"] == 1
    assert report["vault"]["scanned_notes"] == 1
    assert report["vault"]["indexed_chunks"] == (None if without_dense else 0)
    assert not any(issue["code"] == "search_database_unreadable" for issue in report["issues"])
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not any(
        database.with_name(database.name + suffix).exists() for suffix in ("-wal", "-shm")
    )


def test_missing_dense_and_fts_is_not_reported_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, database = make_index(tmp_path, "missing-fts.db", without_dense=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("DROP TABLE fts_notes")
        connection.commit()
    monkeypatch.setenv("POWER_SEARCH_DB", str(database))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    report = doctor.run_doctor(vault)
    assert report["vault"]["index_state"] == "unreadable"
    assert any(issue["code"] == "search_database_unreadable" for issue in report["issues"])


@pytest.mark.asyncio
async def test_relative_fts_only_is_consistent_across_cli_and_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, database = make_index(tmp_path, "relative ?# %.db", without_dense=True)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POWER_SEARCH_DB", database.name)
    monkeypatch.setenv("POWER_VAULT_DIR", str(vault))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cli = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "from power_framework.core.cli import main; main()",
            "doctor",
            str(vault),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert cli.returncode == 1  # The legacy unprobed-provider warning is unchanged.
    cli_report = json.loads(cli.stdout)
    schema = json.loads(
        (Path(__file__).parents[1] / "docs/schemas/doctor-report-v1.json").read_text()
    )
    validate(cli_report, schema)
    value = {
        "mcpServers": {
            "power": {
                "command": sys.executable,
                "args": ["-m", "power_framework.mcp.power_server"],
                "env": dict(os.environ),
            }
        }
    }
    async with stdio_session(value) as client:
        listing = await client.list_tools()
        assert any(item.name == "get_server_info" for item in listing.tools)
        response = await client.call_tool("get_server_info", {})
        assert not response.is_error
        sdk_report = json.loads(response.structured_content["result"])
    validate(sdk_report, schema)
    for report in (cli_report, sdk_report):
        assert report["schema_version"] == 1
        assert report["status"] == "degraded"
        assert report["exit_code"] == 1
        assert [issue["code"] for issue in report["issues"]] == ["embedding_binding_not_requested"]
        assert report["vault"]["database_path"] == database.name
        assert report["vault"]["index_state"] == "legacy_database"
        assert report["vault"]["indexed_notes"] == 1
        assert report["vault"]["indexed_chunks"] is None
        assert not any(issue["code"] == "search_database_unreadable" for issue in report["issues"])
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
