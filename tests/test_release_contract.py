"""Regression tests for the machine-readable POWER release contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "verify_release_contract.py"
BASELINE = REPO_ROOT / "release" / "evidence" / "baselines" / "v3.2.5.json"
MODELS_LOCK = REPO_ROOT / "release" / "models.lock.json"


def _run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- invokes the repository-local validator under this interpreter.
        [sys.executable, str(VALIDATOR), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_current_release_contract_is_valid() -> None:
    result = _run_validator()

    assert result.returncode == 0, result.stderr


def test_model_lock_version_must_match_project_version(tmp_path: Path) -> None:
    models_lock = json.loads(MODELS_LOCK.read_text(encoding="utf-8"))
    models_lock["release"] = "9.9.9"
    altered_lock = _write_json(tmp_path / "models.lock.json", models_lock)

    result = _run_validator("--models-lock", str(altered_lock))

    assert result.returncode == 1
    assert "does not match project version" in result.stderr


def test_dirty_source_cannot_be_a_release_baseline(tmp_path: Path) -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline["source"]["clean"] = False
    dirty_baseline = _write_json(tmp_path / "dirty-baseline.json", baseline)

    result = _run_validator("--baseline", str(dirty_baseline))

    assert result.returncode == 1
    assert "source.clean must be true" in result.stderr


def test_benchmark_hash_must_match_frozen_dataset(tmp_path: Path) -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline["benchmark"]["queries_sha256"] = "0" * 64
    altered_baseline = _write_json(tmp_path / "altered-baseline.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "benchmark.queries_sha256 does not match" in result.stderr


def test_source_tree_must_be_a_real_tree_matching_commit(tmp_path: Path) -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline["source"]["tree"] = "0" * 40
    altered_baseline = _write_json(tmp_path / "altered-baseline.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "does not resolve to a Git tree" in result.stderr


def test_source_tag_must_point_to_source_commit(tmp_path: Path) -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline["source"]["tag"] = "v3.2.4"
    altered_baseline = _write_json(tmp_path / "altered-baseline.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "does not point to source.commit" in result.stderr
