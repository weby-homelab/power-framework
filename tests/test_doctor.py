"""Regression tests for the read-only, agent-facing doctor contract."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from jsonschema import validate

from power_framework.core import capabilities, doctor


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

    assert parsed["schema_version"] == doctor.DOCTOR_SCHEMA_VERSION
    assert parsed["command"] == "doctor"
    assert parsed["status"] == "degraded"
    assert parsed["exit_code"] == 1
    assert parsed["vault"]["index_state"] == "missing"
    assert parsed["issues"][0]["code"] == "search_index_missing"
    assert parsed["capabilities"] == capabilities.manifest()
    assert len(parsed["capabilities"]["interfaces"]["cli_commands"]) == 25
    assert len(parsed["capabilities"]["interfaces"]["mcp_tools"]) == 20
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
    assert report["issues"][0]["code"] == "embedding_binding_not_requested"
    assert not cache_home.exists()


def test_lightweight_doctor_p95_stays_below_half_second(tmp_path: Path) -> None:
    durations: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        report = doctor.run_doctor(tmp_path)
        durations.append(time.perf_counter() - started)
        assert report["embedding"]["probe_requested"] is False

    p95 = sorted(durations)[18]
    assert p95 < 0.5, f"lightweight doctor p95 exceeded 500 ms: {p95:.3f}s"


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
