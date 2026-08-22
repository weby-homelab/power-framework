"""Focused tests for the exact-artifact native candidate harness."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts import verify_native_candidate as harness

if TYPE_CHECKING:
    import pytest


def _inputs(tmp_path: Path) -> harness.CandidateInputs:
    power = tmp_path / "power_framework-3.7.4-py3-none-any.whl"
    gui = tmp_path / "power_gui-0.7.10-py3-none-any.whl"
    manifest = tmp_path / "power.suite.manifest.json"
    constraints = tmp_path / "power-suite.constraints.txt"
    power.write_bytes(b"exact POWER wheel")
    gui.write_bytes(b"exact GUI wheel")
    manifest.write_text('{"schema":"power.suite.manifest.v2"}\n', encoding="utf-8")
    constraints.write_text("mcp==2.0.0\n", encoding="utf-8")
    return harness.CandidateInputs(
        power_wheel=power,
        gui_wheel=gui,
        manifest=manifest,
        constraints=constraints,
        home=tmp_path / "home with spaces-Ж",
        expected_power="3.7.4",
        expected_gui="0.7.10",
    )


def _install_mocks(
    monkeypatch: pytest.MonkeyPatch,
    inputs: harness.CandidateInputs,
    *,
    mcp_status: str = "ok",
    constraints_path: Path | None = None,
) -> tuple[list[list[str]], list[bool]]:
    resolved_constraints = (constraints_path or inputs.constraints).resolve()
    constraints_sha = harness._sha256_file(inputs.constraints)
    release_slot = inputs.home / ".local" / "share" / "power" / "releases" / "slot-a"
    current = inputs.home / ".local" / "share" / "power" / "current"
    calls: list[list[str]] = []
    approvals: list[bool] = []

    def fake_build(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ready",
            "native": {"state": str(inputs.home / "suite-install.json")},
            "contract": {
                "components": {
                    "power": {"metadata": {"version": inputs.expected_power}},
                    "gui": {"metadata": {"version": inputs.expected_gui}},
                },
                "dependencies": {
                    "path": str(resolved_constraints),
                    "sha256": constraints_sha,
                },
            },
        }

    def fake_apply(plan: dict[str, Any], *, approved: bool) -> dict[str, Any]:
        assert plan["status"] == "ready"
        approvals.append(approved)
        bin_dir = release_slot / "venv" / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("python", "pip"):
            (bin_dir / name).write_text("executable\n", encoding="utf-8")
        current.parent.mkdir(parents=True, exist_ok=True)
        current.symlink_to(release_slot, target_is_directory=True)
        launcher_dir = inputs.home / ".local" / "bin"
        launcher_dir.mkdir(parents=True)
        for name in ("power", "power-mcp", "power-gui"):
            launcher = launcher_dir / name
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")
            launcher.chmod(0o755)
        return {
            "status": "applied",
            "suite_version": inputs.expected_power,
            "application_schema": "power.application.v2",
            "manifest_sha256": harness._sha256_file(inputs.manifest),
            "release_slot": str(release_slot),
            "current": str(current),
            "previous_release_slot": None,
        }

    def fake_identity(executable: Path, *, include_suite: bool) -> dict[str, Any]:
        result: dict[str, Any] = {
            "python": {"executable": str(executable), "version": "3.13.7"},
            "pip": {"executable": str(executable.with_name("pip")), "version": "25.2"},
        }
        if include_suite:
            result["distributions"] = {
                "power-framework": inputs.expected_power,
                "power-gui": inputs.expected_gui,
            }
        return result

    def fake_run(
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 300,
    ) -> subprocess.CompletedProcess[str]:
        assert timeout_seconds == 300
        calls.append(command)
        executable = Path(command[0]).name
        stdout = ""
        if command[1:] == ["--version"] and executable in {"power", "power-mcp"}:
            stdout = f"{inputs.expected_power}\n"
        elif command[1:] == ["--help"] and executable == "power-gui":
            stdout = "usage: power-gui\n"
        elif command[1:] == ["integrations", "doctor"]:
            stdout = json.dumps(
                {
                    "status": "ok",
                    "runtime": {"power_framework": inputs.expected_power},
                }
            )
        elif len(command) > 1 and command[1] == "search":
            marker = command[3]
            stdout = json.dumps(
                {
                    "actual_mode": "fts",
                    "results": [{"metadata": {"title": f"Native Candidate {marker}"}}],
                }
            )
        elif executable == "power-mcp" and command[1:] == ["preflight"]:
            assert env is not None
            stdout = json.dumps(
                {
                    "status": mcp_status,
                    "transport": "stdio",
                    "vault_root": env["POWER_VAULT_DIR"],
                    "power_version": inputs.expected_power,
                }
            )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(harness, "build_native_install_plan", fake_build)
    monkeypatch.setattr(harness, "apply_native_install_plan", fake_apply)
    monkeypatch.setattr(harness, "_python_identity", fake_identity)
    monkeypatch.setattr(harness, "_run_command", fake_run)
    return calls, approvals


def test_candidate_harness_passes_all_exact_native_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    calls, approvals = _install_mocks(monkeypatch, inputs)

    report = harness.verify_candidate(inputs)

    assert report["schema"] == "power.native-candidate-validation.v1"
    assert report["status"] == "passed"
    assert approvals == [True]
    assert report["inputs"]["constraints"]["sha256"] == harness._sha256_file(inputs.constraints)
    assert report["install"]["current_target"] == report["install"]["release_slot"]
    assert report["vault_exercise"]["search"]["marker_found"] is True
    assert report["mcp_preflight"]["status"] == "ok"
    arguments = [command[1:] for command in calls]
    assert ["--version"] in arguments
    assert ["integrations", "doctor"] in arguments
    assert any(argument and argument[0] == "init" for argument in arguments)
    assert any(argument and argument[0] == "ingest" for argument in arguments)
    assert any(
        argument and argument[0] == "sync" and "--strict" in argument for argument in arguments
    )
    assert any(argument and argument[0] == "search" and "fts" in argument for argument in arguments)
    assert ["preflight"] in arguments


def test_constraints_input_mismatch_fails_before_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    other_constraints = tmp_path / "other.constraints.txt"
    other_constraints.write_text("mcp==2.0.0\n", encoding="utf-8")
    _calls, approvals = _install_mocks(
        monkeypatch,
        inputs,
        constraints_path=other_constraints,
    )

    report = harness.verify_candidate(inputs)

    assert report["status"] == "failed"
    assert "manifest-declared" in report["failure"]["message"]
    assert approvals == []


def test_mcp_preflight_non_ok_status_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    _install_mocks(monkeypatch, inputs, mcp_status="error")

    report = harness.verify_candidate(inputs)

    assert report["status"] == "failed"
    assert report["failure"]["type"] == "CandidateValidationError"
    assert "preflight status" in report["failure"]["message"]
    assert report["install"]["current_target"] == report["install"]["release_slot"]
    assert report["integrations_doctor"]["status"] == "ok"


def test_cli_argument_error_emits_failed_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = harness.main([])

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 1
    assert report["schema"] == "power.native-candidate-validation.v1"
    assert report["status"] == "failed"
    assert report["failure"]["type"] == "ArgumentError"
