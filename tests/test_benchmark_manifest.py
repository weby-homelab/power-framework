"""Regression tests for the release-evidence manifest validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "verify_benchmark_manifest.py"


def _manifest(
    *, dirty: bool = False, measurement_classes: list[str] | None = None
) -> dict[str, object]:
    checksum = "a" * 64
    classifications = measurement_classes or ["cold", "warm"]
    return {
        "schema_version": "1.0",
        "run_id": "run-phase0-001",
        "timestamp": "2026-07-27T10:00:00+00:00",
        "source": {
            "repository": "weby-homelab/power-framework",
            "commit": "b" * 40,
            "tree_sha256": checksum,
            "dirty": dirty,
        },
        "vault": {"opaque_id": "vault-0001", "snapshot_sha256": checksum, "note_count": 42},
        "models": [
            {
                "role": "embedding",
                "repository": "aapot/bge-m3-onnx",
                "revision": "c" * 40,
                "files": [{"path": "model.onnx", "sha256": checksum}],
            },
            {
                "role": "reranker",
                "repository": "onnx-community/bge-reranker-v2-m3-ONNX",
                "revision": "d" * 40,
                "files": [{"path": "model.onnx", "sha256": checksum}],
            },
        ],
        "environment": {
            "hardware": {"cpu": "test cpu", "logical_cores": 4, "memory_bytes": 8589934592},
            "cgroup": {"memory_max_bytes": 4294967296, "cpu_max": "400000 100000"},
            "python_version": "3.13.0",
            "platform": "Linux-x86_64",
        },
        "commands": [
            {
                "name": "cold-search",
                "command": "power search vault query",
                "classification": "cold",
            },
            {
                "name": "warm-search",
                "command": "power search vault query",
                "classification": "warm",
            },
        ],
        "measurements": [
            {
                "name": f"{classification}-latency",
                "classification": classification,
                "unit": "milliseconds",
                "artifact_sha256": checksum,
            }
            for classification in classifications
        ],
        "artifacts": [{"path": "raw/latency.json", "sha256": checksum}],
        "claims": [
            {
                "id": "LATENCY-001",
                "statement": "Measured only for this recorded environment.",
                "state": "measured",
                "evidence_artifact_sha256": checksum,
            }
        ],
    }


def _run_validator(tmp_path: Path, manifest: dict[str, object]) -> subprocess.CompletedProcess[str]:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return subprocess.run(  # noqa: S603 -- executes the repository-local validator under this interpreter.
        [sys.executable, str(VALIDATOR), str(manifest_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_schema_is_valid() -> None:
    result = subprocess.run(  # noqa: S603 -- executes the repository-local validator under this interpreter.
        [sys.executable, str(VALIDATOR), "--schema-only"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_valid_manifest_passes(tmp_path: Path) -> None:
    result = _run_validator(tmp_path, _manifest())

    assert result.returncode == 0, result.stderr


def test_measured_claim_rejects_dirty_source(tmp_path: Path) -> None:
    result = _run_validator(tmp_path, _manifest(dirty=True))

    assert result.returncode == 1
    assert "requires source.dirty=false" in result.stderr


def test_manifest_requires_cold_and_warm_measurements(tmp_path: Path) -> None:
    result = _run_validator(tmp_path, _manifest(measurement_classes=["cold"]))

    assert result.returncode == 1
    assert "missing required classification(s): warm" in result.stderr
