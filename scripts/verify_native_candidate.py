#!/usr/bin/env python3
"""Validate one exact POWER Suite native candidate in a dedicated HOME."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never

from power_framework.core.integrations import (
    apply_native_install_plan,
    build_native_install_plan,
)

REPORT_SCHEMA = "power.native-candidate-validation.v1"


class CandidateValidationError(RuntimeError):
    """Raised when a mandatory native-candidate gate does not pass."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Convert command-line errors into the harness fail-closed JSON path."""

    def error(self, message: str) -> Never:
        raise CandidateValidationError(message)


@dataclass(frozen=True)
class CandidateInputs:
    """Exact candidate artifacts and the dedicated target profile."""

    power_wheel: Path
    gui_wheel: Path
    manifest: Path
    constraints: Path
    home: Path
    expected_power: str
    expected_gui: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_artifact(path: Path, *, label: str, suffix: str | None = None) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise CandidateValidationError(f"{label} is not an existing regular file")
    if suffix is not None and resolved.suffix != suffix:
        raise CandidateValidationError(f"{label} must use the {suffix} suffix")
    return resolved


def _resolve_inputs(inputs: CandidateInputs) -> CandidateInputs:
    home = inputs.home.expanduser()
    if home.exists() and home.is_symlink():
        raise CandidateValidationError("HOME must not be a symlink")
    home = home.resolve()
    if home == home.parent or home == Path.home().resolve():
        raise CandidateValidationError("HOME must be a dedicated profile, not the active HOME")
    return CandidateInputs(
        power_wheel=_require_artifact(inputs.power_wheel, label="POWER wheel", suffix=".whl"),
        gui_wheel=_require_artifact(inputs.gui_wheel, label="GUI wheel", suffix=".whl"),
        manifest=_require_artifact(inputs.manifest, label="Suite manifest", suffix=".json"),
        constraints=_require_artifact(inputs.constraints, label="constraints"),
        home=home,
        expected_power=inputs.expected_power,
        expected_gui=inputs.expected_gui,
    )


def _run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int = 300,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 - argv only; shell execution is never used.
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        executable = Path(command[0]).name
        operation = command[1] if len(command) > 1 else "launch"
        raise CandidateValidationError(
            f"command failed closed: {executable} {operation} (exit {result.returncode})"
        )
    return result


def _json_object(value: str, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CandidateValidationError(f"{label} did not emit valid JSON") from exc
    if not isinstance(payload, dict):
        raise CandidateValidationError(f"{label} did not emit a JSON object")
    return payload


def _python_identity(executable: Path, *, include_suite: bool) -> dict[str, Any]:
    script = textwrap.dedent(
        """
        import importlib.metadata
        import json
        import platform
        import sys
        from pathlib import Path

        pip_executable = Path(sys.executable).with_name("pip")
        payload = {
            "python": {
                "executable": sys.executable,
                "version": platform.python_version(),
                "full_version": sys.version,
            },
            "pip": {
                "executable": str(pip_executable),
                "version": importlib.metadata.version("pip"),
            },
        }
        if "--suite" in sys.argv:
            payload["distributions"] = {
                "power-framework": importlib.metadata.version("power-framework"),
                "power-gui": importlib.metadata.version("power-gui"),
            }
        print(json.dumps(payload, sort_keys=True))
        """
    ).strip()
    command = [str(executable), "-c", script]
    if include_suite:
        command.append("--suite")
    payload = _json_object(
        _run_command(command).stdout,
        label="Python toolchain probe",
    )
    pip_data = payload.get("pip")
    if not isinstance(pip_data, dict) or not Path(str(pip_data.get("executable", ""))).is_file():
        raise CandidateValidationError("pip executable identity is unavailable")
    return payload


def _base_environment(home: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["PATH"] = f"{home / '.local' / 'bin'}{os.pathsep}{environment.get('PATH', '')}"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _launcher_evidence(
    executable: Path,
    arguments: list[str],
    *,
    environment: dict[str, str],
    expected_version: str | None = None,
) -> dict[str, Any]:
    if not executable.is_file():
        raise CandidateValidationError(f"active launcher is missing: {executable.name}")
    result = _run_command([str(executable), *arguments], env=environment)
    combined = f"{result.stdout}\n{result.stderr}"
    if expected_version is not None and expected_version not in combined:
        raise CandidateValidationError(f"active launcher identity mismatch: {executable.name}")
    return {
        "path": str(executable),
        "arguments": arguments,
        "exit_code": result.returncode,
        "output_sha256": _sha256_text(combined),
        "expected_version": expected_version,
        "version_verified": expected_version is None or expected_version in combined,
    }


def _exercise_vault(
    power: Path,
    power_mcp: Path,
    *,
    home: Path,
    environment: dict[str, str],
    expected_power: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    marker = f"native-candidate-{uuid.uuid4().hex}"
    title = f"Native Candidate {marker}"
    with tempfile.TemporaryDirectory(prefix=".power-native-candidate-vault-", dir=home) as raw:
        vault = Path(raw).resolve()
        operations: list[dict[str, Any]] = []

        def run_power(arguments: list[str], name: str) -> subprocess.CompletedProcess[str]:
            result = _run_command([str(power), *arguments], env=environment)
            operations.append(
                {
                    "name": name,
                    "exit_code": result.returncode,
                    "stdout_sha256": _sha256_text(result.stdout),
                    "stderr_sha256": _sha256_text(result.stderr),
                }
            )
            return result

        run_power(["init", str(vault)], "init")
        run_power(
            [
                "ingest",
                str(vault),
                "--type",
                "Resource",
                "--title",
                title,
                "--description",
                f"Exact native candidate marker {marker}",
                "--tags",
                "native-candidate",
            ],
            "ingest",
        )
        run_power(["sync", str(vault), "--fts-only", "--strict"], "fts_sync_strict")
        search = run_power(
            [
                "search",
                str(vault),
                marker,
                "--mode",
                "fts",
                "--max-results",
                "5",
                "--json",
            ],
            "fts_search",
        )
        search_payload = _json_object(search.stdout, label="FTS search")
        results = search_payload.get("results")
        actual_mode = search_payload.get("actual_mode")
        if actual_mode != "fts":
            raise CandidateValidationError("FTS search did not report actual_mode=fts")
        if not isinstance(results, list) or not results:
            raise CandidateValidationError("FTS search did not return the unique marker note")
        if marker.casefold() not in json.dumps(results, ensure_ascii=False).casefold():
            raise CandidateValidationError("FTS search results do not contain the unique marker")

        mcp_environment = environment.copy()
        mcp_environment["POWER_VAULT_DIR"] = str(vault)
        preflight = _json_object(
            _run_command([str(power_mcp), "preflight"], env=mcp_environment).stdout,
            label="power-mcp preflight",
        )
        if preflight.get("status") != "ok":
            raise CandidateValidationError("power-mcp preflight status is not ok")
        if Path(str(preflight.get("vault_root", ""))).resolve() != vault:
            raise CandidateValidationError("power-mcp preflight used the wrong vault")
        if preflight.get("power_version") != expected_power:
            raise CandidateValidationError("power-mcp preflight reported the wrong POWER version")

        vault_evidence = {
            "disposable": True,
            "path": str(vault),
            "marker_sha256": _sha256_text(marker),
            "operations": operations,
            "search": {
                "actual_mode": actual_mode,
                "result_count": len(results),
                "marker_found": True,
            },
        }
        mcp_evidence = {
            "status": preflight["status"],
            "transport": preflight.get("transport"),
            "vault_root": preflight.get("vault_root"),
            "power_version": preflight.get("power_version"),
        }
        return vault_evidence, mcp_evidence


def _input_evidence(inputs: CandidateInputs) -> dict[str, Any]:
    return {
        "power_wheel": {
            "path": str(inputs.power_wheel),
            "sha256": _sha256_file(inputs.power_wheel),
        },
        "gui_wheel": {
            "path": str(inputs.gui_wheel),
            "sha256": _sha256_file(inputs.gui_wheel),
        },
        "manifest": {
            "path": str(inputs.manifest),
            "sha256": _sha256_file(inputs.manifest),
        },
        "constraints": {
            "path": str(inputs.constraints),
            "sha256": _sha256_file(inputs.constraints),
        },
        "home": str(inputs.home),
        "expected_power": inputs.expected_power,
        "expected_gui": inputs.expected_gui,
    }


def verify_candidate(inputs: CandidateInputs) -> dict[str, Any]:
    """Install and exercise one exact native candidate, returning a JSON-safe report."""
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "failed",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    try:
        resolved = _resolve_inputs(inputs)
        report["inputs"] = _input_evidence(resolved)
        report["toolchain"] = {
            "controller": _python_identity(Path(sys.executable), include_suite=False)
        }

        plan = build_native_install_plan(
            home=resolved.home,
            power_wheel=resolved.power_wheel,
            gui_wheel=resolved.gui_wheel,
            manifest=resolved.manifest,
        )
        if plan.get("status") not in {"ready", "update"}:
            raise CandidateValidationError(
                f"native install plan is not applicable: {plan.get('status', 'unknown')}"
            )
        contract = plan.get("contract")
        if not isinstance(contract, dict):
            raise CandidateValidationError("native install plan omitted its Suite contract")
        components = contract.get("components")
        if not isinstance(components, dict):
            raise CandidateValidationError("native install plan omitted component identities")
        power_component = components.get("power")
        gui_component = components.get("gui")
        if not isinstance(power_component, dict) or not isinstance(gui_component, dict):
            raise CandidateValidationError("native install plan requires both POWER and GUI")
        power_metadata = power_component.get("metadata")
        gui_metadata = gui_component.get("metadata")
        if not isinstance(power_metadata, dict) or not isinstance(gui_metadata, dict):
            raise CandidateValidationError("native install plan omitted wheel metadata")
        if power_metadata.get("version") != resolved.expected_power:
            raise CandidateValidationError("POWER wheel version does not match --expected-power")
        if gui_metadata.get("version") != resolved.expected_gui:
            raise CandidateValidationError("GUI wheel version does not match --expected-gui")
        dependencies = contract.get("dependencies")
        if not isinstance(dependencies, dict):
            raise CandidateValidationError("native install plan omitted constraints identity")
        declared_constraints = Path(str(dependencies.get("path", ""))).resolve()
        if declared_constraints != resolved.constraints:
            raise CandidateValidationError("--constraints is not the manifest-declared artifact")
        if dependencies.get("sha256") != report["inputs"]["constraints"]["sha256"]:
            raise CandidateValidationError("constraints digest does not match the Suite contract")

        receipt = apply_native_install_plan(plan, approved=True)
        if receipt.get("status") != "applied":
            raise CandidateValidationError("native installer did not return status=applied")
        release_slot = Path(str(receipt.get("release_slot", ""))).resolve()
        current = Path(str(receipt.get("current", "")))
        if not current.is_symlink() or current.resolve() != release_slot:
            raise CandidateValidationError(
                "active current pointer does not resolve to the receipt slot"
            )
        report["install"] = {
            "plan_status": plan["status"],
            "suite_version": receipt.get("suite_version"),
            "application_schema": receipt.get("application_schema"),
            "manifest_sha256": receipt.get("manifest_sha256"),
            "release_slot": str(release_slot),
            "current": str(current),
            "current_target": str(current.resolve()),
            "previous_release_slot": receipt.get("previous_release_slot"),
            "receipt_state": plan["native"].get("state"),
        }
        active_venv = current / "venv"
        active_python = active_venv / "bin" / "python"
        installed_identity = _python_identity(active_python, include_suite=True)
        distributions = installed_identity.get("distributions")
        if not isinstance(distributions, dict):
            raise CandidateValidationError(
                "installed Suite distribution identities are unavailable"
            )
        if distributions.get("power-framework") != resolved.expected_power:
            raise CandidateValidationError("installed POWER distribution identity mismatch")
        if distributions.get("power-gui") != resolved.expected_gui:
            raise CandidateValidationError("installed GUI distribution identity mismatch")
        report["toolchain"]["installed"] = installed_identity

        environment = _base_environment(resolved.home)
        launcher_dir = resolved.home / ".local" / "bin"
        power = launcher_dir / "power"
        power_mcp = launcher_dir / "power-mcp"
        power_gui = launcher_dir / "power-gui"
        launchers = {
            "power": _launcher_evidence(
                power,
                ["--version"],
                environment=environment,
                expected_version=resolved.expected_power,
            ),
            "power-mcp": _launcher_evidence(
                power_mcp,
                ["--version"],
                environment=environment,
                expected_version=resolved.expected_power,
            ),
            "power-gui": _launcher_evidence(
                power_gui,
                ["--help"],
                environment=environment,
            ),
        }
        report["launchers"] = launchers
        doctor = _json_object(
            _run_command([str(power), "integrations", "doctor"], env=environment).stdout,
            label="power integrations doctor",
        )
        if doctor.get("status") != "ok":
            raise CandidateValidationError("power integrations doctor status is not ok")
        doctor_runtime = doctor.get("runtime")
        if (
            not isinstance(doctor_runtime, dict)
            or doctor_runtime.get("power_framework") != resolved.expected_power
        ):
            raise CandidateValidationError("power integrations doctor reported the wrong runtime")
        report["integrations_doctor"] = doctor

        vault_evidence, mcp_evidence = _exercise_vault(
            power,
            power_mcp,
            home=resolved.home,
            environment=environment,
            expected_power=resolved.expected_power,
        )
        report.update(
            {
                "status": "passed",
                "vault_exercise": vault_evidence,
                "mcp_preflight": mcp_evidence,
            }
        )
    except Exception as exc:  # Fail closed into the required machine-readable report.
        report["status"] = "failed"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    return report


def _parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--power-wheel", required=True, type=Path)
    parser.add_argument("--gui-wheel", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--constraints", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--expected-power", required=True)
    parser.add_argument("--expected-gui", required=True)
    return parser


def _argument_failure(message: str) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "failure": {"type": "ArgumentError", "message": message},
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        report = verify_candidate(
            CandidateInputs(
                power_wheel=args.power_wheel,
                gui_wheel=args.gui_wheel,
                manifest=args.manifest,
                constraints=args.constraints,
                home=args.home,
                expected_power=args.expected_power,
                expected_gui=args.expected_gui,
            )
        )
    except CandidateValidationError as exc:
        report = _argument_failure(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
