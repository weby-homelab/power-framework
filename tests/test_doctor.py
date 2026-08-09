"""Regression tests for the read-only, agent-facing doctor contract."""

from __future__ import annotations

import json
import os
from pathlib import Path

from jsonschema import validate

from power_framework.core import doctor


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
    report = doctor.run_doctor(tmp_path)

    parsed = json.loads(doctor.report_as_json(report))
    schema = json.loads(
        (Path(__file__).parents[1] / "docs" / "schemas" / "doctor-report-v1.json").read_text(
            encoding="utf-8"
        )
    )
    validate(parsed, schema)

    assert parsed["schema_version"] == doctor.DOCTOR_SCHEMA_VERSION
    assert parsed["command"] == "doctor"
    assert parsed["status"] == "degraded"
    assert parsed["exit_code"] == 1
    assert parsed["vault"]["index_state"] == "missing"
    assert parsed["issues"][0]["code"] == "search_index_missing"


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

    report = doctor.run_doctor(tmp_path)

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

    doctor.run_doctor(vault)

    assert not (vault / ".power").exists()
    assert not (cache_home / "power-framework").exists()


def test_file_path_is_rejected_as_vault(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_probe_embedding_binding", _safe_embedding)
    path = tmp_path / "not-a-vault"
    path.write_text("not a directory", encoding="utf-8")

    report = doctor.run_doctor(path)

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
