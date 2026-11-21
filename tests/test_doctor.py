"""Regression tests for the read-only, agent-facing doctor contract."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest
from jsonschema import validate

from power_framework.core import capabilities, doctor, generation_index
from power_framework.core.constants import DENSE_INDEX_SCHEMA_VERSION
from power_framework.core.db import _init_db
from power_framework.core.generation_index import sync_vault_atomically
from power_framework.core.index_diagnostics import read_index_status


def _safe_embedding() -> tuple[dict[str, object], list[dict[str, str]]]:
    return (
        {
            "provider": "bge-m3",
            "requested_device": "auto",
            "available_providers": ["CPUExecutionProvider"],
            "model_cached": True,
            "binding": "verified",
            "bound_provider": "CPUExecutionProvider",
            "probe_seconds": 0.001,
            "runtime": {"available": True, "version": "test"},
        },
        [],
    )


def test_json_report_is_versioned_and_machine_readable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_probe_embedding_binding", _safe_embedding)
    report = doctor.run_doctor(tmp_path, probe_embedding=True)

    parsed = json.loads(doctor.report_as_json(report))
    schema = json.loads(
        (Path(__file__).parents[1] / "docs" / "schemas" / "doctor-report-v1.json").read_text(
            encoding="utf-8"
        )
    )
    validate(parsed, schema)
    discovery_fields = {
        "server_status",
        "provider_probe",
        "fts_status",
        "dense_status",
        "write_status",
        "lint_status",
        "index_age_seconds",
        "index_freshness",
    }
    assert discovery_fields <= schema["properties"].keys()
    assert discovery_fields <= parsed.keys()

    assert parsed["schema_version"] == doctor.DOCTOR_SCHEMA_VERSION
    assert parsed["command"] == "doctor"
    assert parsed["status"] == "degraded"
    assert parsed["exit_code"] == 1
    assert parsed["vault"]["index_state"] == "missing"
    assert parsed["issues"][0]["code"] == "search_index_missing"
    assert parsed["capabilities"] == capabilities.manifest()
    assert len(parsed["capabilities"]["interfaces"]["cli_commands"]) == 27
    assert len(parsed["capabilities"]["interfaces"]["mcp_tools"]) == 21
    contracts = parsed["capabilities"]["interfaces"]["mcp_tool_contracts"]
    assert [contract["name"] for contract in contracts] == parsed["capabilities"]["interfaces"][
        "mcp_tools"
    ]
    assert all(
        set(contract["annotations"])
        == {
            "readOnlyHint",
            "destructiveHint",
            "idempotentHint",
            "openWorldHint",
        }
        for contract in contracts
    )
    assert all(
        set(contract["risk"]) == {"local_only", "egress", "approval"} for contract in contracts
    )
    archive_contract = next(
        contract for contract in contracts if contract["name"] == "archive_notes"
    )
    assert archive_contract["annotations"]["destructiveHint"] is True
    assert archive_contract["risk"]["approval"] == "explicit"
    assert parsed["capabilities"]["search"]["default_mode"] == "auto"


def test_lightweight_discovery_skips_embedding_probe_and_cache_state(
    tmp_path: Path, monkeypatch
) -> None:
    cache_home = tmp_path / "cache-home"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    def fail_if_called() -> tuple[dict[str, object], list[dict[str, str]]]:
        raise AssertionError("lightweight discovery must not probe the embedding session")

    monkeypatch.setattr(doctor, "_probe_embedding_binding", fail_if_called)

    report = doctor.run_doctor(tmp_path)

    assert report["embedding"]["binding"] == "not_requested"
    assert report["embedding"]["probe_requested"] is False
    assert report["provider_probe"] == "not_run"
    assert not any(issue["code"] == "embedding_binding_not_requested" for issue in report["issues"])
    assert not cache_home.exists()


@pytest.mark.parametrize(
    ("binding", "issue_code", "probe_status"),
    [
        ("failed", "embedding_binding_failed", "failed"),
        ("not_supported", "embedding_probe_not_supported", "disabled"),
        ("not_verified", "embedding_model_not_cached", "unavailable"),
    ],
)
def test_doctor_distinguishes_provider_probe_outcomes(
    monkeypatch: pytest.MonkeyPatch, binding: str, issue_code: str, probe_status: str
) -> None:
    monkeypatch.setattr(
        doctor,
        "_probe_embedding_binding",
        lambda: ({"binding": binding}, [{"code": issue_code, "severity": "warning"}]),
    )
    report = doctor.run_doctor(probe_embedding=True)
    assert report["provider_probe"] == probe_status
    assert report["embedding"]["probe_requested"] is True


def test_lightweight_doctor_p95_stays_below_half_second(tmp_path: Path) -> None:
    durations: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        report = doctor.run_doctor(tmp_path)
        durations.append(time.perf_counter() - started)
        assert report["embedding"]["probe_requested"] is False

    p95 = sorted(durations)[18]
    assert p95 < 0.5, f"lightweight doctor p95 exceeded 500 ms: {p95:.3f}s"


def test_discovery_reports_manifest_compatibility_without_claiming_vector_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "index.db"
    monkeypatch.setattr(
        "power_framework.experimental.embeddings.configured_embedding_identity",
        lambda: ("FixtureProvider", "fixture-model"),
    )
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.execute("INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES ('fixture', X'00')")
        conn.executemany(
            "INSERT INTO dense_index_manifest VALUES (?, ?)",
            (
                ("schema_version", DENSE_INDEX_SCHEMA_VERSION),
                ("chunk_count", "1"),
                ("embedding_dimension", "3"),
                ("embedding_provider", "FixtureProvider"),
                ("embedding_model", "fixture-model"),
            ),
        )
        conn.commit()
    assert read_index_status(database) == (0, 1, True, "manifest_compatible")
    monkeypatch.setattr(
        "power_framework.experimental.embeddings.configured_embedding_identity",
        lambda: ("FixtureProvider", "other-model"),
    )
    assert read_index_status(database) == (0, 1, True, "incompatible")


def test_doctor_reads_relative_search_db_override_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    database = tmp_path / "relative index.db"
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.commit()
    before = database.read_bytes()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POWER_SEARCH_DB", database.name)

    report = doctor.run_doctor(vault)

    assert report["server_status"] == "ok"
    assert report["vault"]["index_state"] == "legacy_database"
    assert report["vault"]["database_path"] == database.name
    assert report["fts_status"] == "ready"
    assert report["dense_status"] == "missing"
    assert report["index_age_seconds"] is not None
    assert database.read_bytes() == before
    assert not list(tmp_path.glob(f"{database.name}-*"))
    assert not (vault / ".power").exists()


def test_doctor_preserves_fts_readiness_for_legacy_index_without_dense_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    database = tmp_path / "legacy.db"
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.execute("DROP TABLE chunk_embeddings")
        conn.commit()
    monkeypatch.setenv("POWER_SEARCH_DB", str(database))

    report = doctor.run_doctor(vault)

    assert report["server_status"] == "ok"
    assert report["vault"]["index_state"] == "legacy_database"
    assert report["vault"]["indexed_notes"] == 0
    assert report["vault"]["indexed_chunks"] is None
    assert report["fts_status"] == "ready"
    assert report["dense_status"] == "unavailable"
    assert report["index_age_seconds"] is not None


def test_doctor_preserves_legacy_counts_when_fts_table_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    database = tmp_path / "legacy.db"
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.execute("DROP TABLE fts_notes")
        conn.execute("INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES ('fixture', X'00')")
        conn.commit()
    monkeypatch.setenv("POWER_SEARCH_DB", str(database))

    report = doctor.run_doctor(vault)

    assert report["vault"]["index_state"] == "legacy_database"
    assert report["vault"]["indexed_notes"] == 0
    assert report["vault"]["indexed_chunks"] == 1
    assert report["fts_status"] == "unavailable"
    assert report["dense_status"] == "incompatible"
    assert report["server_status"] == "error"
    assert report["exit_code"] == 1
    assert any(issue["code"] == "fts_index_unavailable" for issue in report["issues"])


def test_discovery_does_not_recover_a_rollback_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    database = tmp_path / "index.db"
    journal = tmp_path / "index.db-journal"
    with closing(sqlite3.connect(database)) as conn:
        _init_db(conn)
        conn.execute("CREATE TABLE journal_fixture (payload BLOB)")
        conn.execute("INSERT INTO journal_fixture VALUES (zeroblob(262144))")
        conn.commit()

    # Interrupt a fixed fixture program; the temporary database path is its only argument.
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import os, sqlite3, sys\n"
            "db = sqlite3.connect(sys.argv[1])\n"
            "db.execute('PRAGMA journal_mode=DELETE')\n"
            "db.execute('PRAGMA cache_size=1')\n"
            "db.execute('UPDATE journal_fixture SET payload=randomblob(262144)')\n"
            "os._exit(0)\n",
            str(database),
        ],
        check=True,
        timeout=10,
    )
    original = database.read_bytes(), journal.read_bytes()
    control = tmp_path / "control.db"
    control_journal = tmp_path / "control.db-journal"
    shutil.copyfile(database, control)
    shutil.copyfile(journal, control_journal)
    with closing(sqlite3.connect(control)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM file_metadata").fetchone() == (0,)
    assert not control_journal.exists(), "control must actually require rollback recovery"
    monkeypatch.setenv("POWER_SEARCH_DB", str(database))

    report = doctor.run_doctor(vault)

    assert report["fts_status"] == "unavailable"
    assert (database.read_bytes(), journal.read_bytes()) == original


def test_doctor_does_not_inspect_an_uncheckpointed_wal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "example.md").write_text("# Example\n", encoding="utf-8")
    database = tmp_path / "index.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(database))
    with closing(sqlite3.connect(database)) as writer:
        _init_db(writer)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        writer.execute("INSERT INTO file_metadata VALUES ('example.md', 1)")
        writer.commit()
        index_files = [database, tmp_path / "index.db-wal", tmp_path / "index.db-shm"]
        assert writer.execute("SELECT COUNT(*) FROM file_metadata").fetchone() == (1,)
        assert index_files[1].stat().st_size > 0
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in index_files]

        report = doctor.run_doctor(vault)

        assert report["vault"]["index_state"] == "unreadable"
        assert report["vault"]["indexed_notes"] is None
        assert report["fts_status"] == "unavailable"
        assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in index_files] == before

    assert not list(tmp_path.glob("index.db-*"))
    assert doctor.run_doctor(vault)["vault"]["indexed_notes"] == 1
    assert not list(tmp_path.glob("index.db-*"))


def test_discovery_does_not_create_or_modify_generation_sidecars(
    sample_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "generation-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    sync_vault_atomically(sample_vault, sync_embeddings=False)

    def sidecars() -> dict[Path, tuple[bytes, int]]:
        return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.rglob("*.db-*")}

    before = sidecars()
    for _ in range(2):
        report = doctor.run_doctor(sample_vault)
        assert report["server_status"] == "ok"
        assert report["vault"]["index_state"] == "active_generation"
        assert report["fts_status"] == "ready"
        assert sidecars() == before


@pytest.mark.parametrize("changed_file", ["generation-state.db", "generation"])
def test_discovery_rejects_a_change_during_generation_verification(
    sample_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_file: str
) -> None:
    cache = tmp_path / "generation-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.delenv("POWER_SEARCH_DB", raising=False)
    sync_vault_atomically(sample_vault, sync_embeddings=False)
    generation_index.invalidate_active_generation_cache(sample_vault)
    state_db = next(cache.rglob("generation-state.db"))
    file_identity = generation_index._file_identity

    def touch_during_verification(path: Path) -> tuple[str, int]:
        digest = file_identity(path)
        target = path if changed_file == "generation" else state_db
        stat = target.stat()
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return digest

    monkeypatch.setattr(generation_index, "_file_identity", touch_during_verification)

    report = doctor.run_doctor(sample_vault)

    assert report["server_status"] == "error"
    assert report["vault"]["index_state"] == "unreadable"
    assert report["vault"]["active_generation"] is None
    assert report["vault"]["indexed_notes"] is None
    assert report["fts_status"] == "unavailable"
    assert any(issue["code"] == "active_generation_unreadable" for issue in report["issues"])


def test_doctor_bootstrap_is_bounded_and_content_free(tmp_path: Path) -> None:
    report = doctor.run_doctor(tmp_path)
    bootstrap = report["bootstrap"]

    assert bootstrap["schema_version"] == "power-agent-v1"
    assert bootstrap["budget_bytes"] == 12 * 1024
    assert bootstrap["content_capture"] == "disabled"
    assert bootstrap["required_sequence"] == [
        "discover",
        "inspect",
        "retrieve",
        "plan",
        "apply",
        "verify",
        "handoff",
    ]
    assert "read_canonical_index" in bootstrap["legacy_required_sequence"]
    assert len(json.dumps(bootstrap, ensure_ascii=False).encode("utf-8")) <= 12 * 1024


def test_capability_manifest_is_read_only(tmp_path: Path, monkeypatch) -> None:
    cache_home = tmp_path / "cache-home"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    report = capabilities.manifest()

    assert report["read_only"] is True
    assert report["network_access"] is False
    assert report["storage"]["cache_root"] == str(cache_home / "power-framework")
    assert not cache_home.exists()


def test_vault_report_keeps_complete_exclusion_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_probe_embedding_binding", _safe_embedding)
    resources = tmp_path / "03_Resources"
    resources.mkdir()
    (resources / "good.md").write_text(
        "---\ntype: Resource\ntitle: Good\ndescription: Valid\n"
        "timestamp: 2026-01-01T00:00:00\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (resources / "bad.md").write_text(
        "---\ntype: NotARealType\ntitle: Bad\n---\n\nBody.\n", encoding="utf-8"
    )

    report = doctor.run_doctor(tmp_path, probe_embedding=True)

    assert report["vault"]["scanned_notes"] == 2
    assert report["vault"]["excluded_notes"] == [
        {"path": "03_Resources/bad.md", "reason": "invalid_metadata"}
    ]
    assert any(issue["code"] == "notes_excluded" for issue in report["issues"])


def test_model_cache_probe_uses_only_existing_snapshot_files(tmp_path: Path, monkeypatch) -> None:
    from power_framework.core import embeddings

    snapshot = (
        tmp_path / "models--aapot--bge-m3-onnx" / "snapshots" / embeddings.BGE_M3_ONNX_REVISION
    )
    snapshot.mkdir(parents=True)
    for filename in ("model.onnx", "model.onnx.data", "tokenizer.json"):
        (snapshot / filename).write_bytes(b"cached")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))

    assert doctor._model_is_cached() is True


def test_vault_probe_does_not_create_identity_or_cache_namespace(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(doctor, "_probe_embedding_binding", _safe_embedding)
    cache_home = tmp_path / "cache-home"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    vault = tmp_path / "vault"
    vault.mkdir()

    doctor.run_doctor(vault, probe_embedding=True)

    assert not (vault / ".power").exists()
    assert not (cache_home / "power-framework").exists()


def test_file_path_is_rejected_as_vault(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_probe_embedding_binding", _safe_embedding)
    path = tmp_path / "not-a-vault"
    path.write_text("not a directory", encoding="utf-8")

    report = doctor.run_doctor(path, probe_embedding=True)

    assert report["exit_code"] == 1
    assert any(issue["code"] == "vault_not_directory" for issue in report["issues"])


def test_cached_binding_probe_forces_offline_manager_and_restores_environment(monkeypatch) -> None:
    from power_framework.core import embeddings

    monkeypatch.setattr(doctor, "_model_is_cached", lambda: True)
    monkeypatch.setattr(embeddings, "EMBED_PROVIDER", "bge-m3")
    monkeypatch.setattr(embeddings, "_preload_gpu_runtime", lambda _ort: None)
    monkeypatch.delenv("POWER_MODEL_OFFLINE", raising=False)

    class FakeManager:
        active_provider = "CPUExecutionProvider"

        def embed(self, _text: str) -> list[float]:
            assert os.environ["POWER_MODEL_OFFLINE"] == "1"
            return [0.0]

    monkeypatch.setattr(embeddings, "BGEM3OnnxManager", FakeManager)

    embedding, issues = doctor._probe_embedding_binding()

    assert embedding["binding"] == "verified"
    assert embedding["bound_provider"] == "CPUExecutionProvider"
    assert issues == []
    assert "POWER_MODEL_OFFLINE" not in os.environ
