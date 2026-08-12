"""Tests for tag-bound release baseline generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_release_baseline.py"
VERIFY = REPO_ROOT / "scripts" / "verify_release_contract.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from generate_release_baseline import _default_template, build_baseline  # noqa: E402
from release_platforms import DEFERRED_RELEASE_PLATFORMS, SUPPORTED_RELEASE_PLATFORMS  # noqa: E402


def test_default_template_skips_candidate_baseline() -> None:
    assert _default_template().name == "v3.4.5.json"


def _write_validation_report(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "power.release-validation.v1",
                "status": "passed",
                "passed": 1014,
                "skipped": 11,
                "coverage_percent": 81.66,
                "warning_count": 0,
                "warning_policy": "warnings are errors",
                "skipped_optional_gates": ["physical platforms"],
                "mandatory_skipped": 0,
                "mandatory_failed": 0,
                "warnings_as_errors": True,
                "junit_sha256": "a" * 64,
                "coverage_sha256": "b" * 64,
                "gate_manifest_sha256": "c" * 64,
                "content_free": True,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_generated_baseline_binds_current_release_tag(tmp_path: Path) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    tag_name = f"v{version}"
    tag = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local refs.
        [git_executable, "rev-parse", "--verify", f"refs/tags/{tag_name}^{{}}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if tag.returncode != 0:
        pytest.skip(f"{tag_name} is created only for the release tag gate")

    output = tmp_path / "release-baseline.json"
    validation_report = _write_validation_report(tmp_path / "validation.json")
    sbom = tmp_path / "sbom.spdx.json"
    sbom.write_text('{"spdxVersion": "SPDX-2.3"}\n', encoding="utf-8")
    upgrade_matrix = tmp_path / "upgrade-matrix-aggregate.json"
    upgrade_matrix.write_text(
        json.dumps(
            {
                "schema_version": "power.upgrade-matrix.aggregate.v1",
                "content_free": True,
                "raw_content_in_report": False,
                "release_gate": {
                    "all_platforms_executed": True,
                    "local_invariants": True,
                },
                "supported_platforms": list(SUPPORTED_RELEASE_PLATFORMS),
                "deferred_platforms": list(DEFERRED_RELEASE_PLATFORMS),
                "platforms": dict.fromkeys(SUPPORTED_RELEASE_PLATFORMS, "executed"),
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [
            sys.executable,
            str(SCRIPT),
            "--tag",
            tag_name,
            "--validation-report",
            str(validation_report),
            "--sbom",
            str(sbom),
            "--upgrade-matrix-aggregate",
            str(upgrade_matrix),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    baseline = json.loads(output.read_text(encoding="utf-8"))
    assert baseline["release"] == version
    expected_commit = tag.stdout.strip()
    expected_tree = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local object.
        [git_executable, "show", "-s", "--format=%T", expected_commit],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert baseline["source"]["commit"] == expected_commit
    assert baseline["source"]["tree"] == expected_tree

    verified = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [
            sys.executable,
            str(VERIFY),
            "--require-tag",
            "--baseline",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr


def test_final_baseline_clears_candidate_publication_scope(tmp_path: Path) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(  # noqa: S603 -- invokes the test-local Git repository.
        [git_executable, "init", "-q", "-b", "main", str(repo)], check=True
    )
    subprocess.run(  # noqa: S603 -- invokes the test-local Git repository.
        [git_executable, "-C", str(repo), "config", "user.name", "test"], check=True
    )
    subprocess.run(  # noqa: S603 -- invokes the test-local Git repository.
        [git_executable, "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (repo / "pyproject.toml").write_text('[project]\nversion = "3.5.0"\n', encoding="utf-8")
    models_lock = repo / "models.lock.json"
    models_lock.write_text('{"release": "3.5.0"}\n', encoding="utf-8")
    dataset = repo / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "corpus": {"hash_sha256": "a" * 64},
                "queries": {"hash_sha256": "b" * 64},
                "qrels": {"hash_sha256": "c" * 64},
                "expected_answers": {"hash_sha256": "d" * 64},
            }
        ),
        encoding="utf-8",
    )
    template = repo / "candidate.json"
    template.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release": "3.5.0",
                "candidate": True,
                "scope": {"technical_release": False, "candidate_only": True},
                "benchmark": {"synthetic": True},
            }
        ),
        encoding="utf-8",
    )
    sbom = repo / "sbom.json"
    sbom.write_text('{"spdxVersion":"SPDX-2.3"}\n', encoding="utf-8")
    upgrade_matrix = repo / "upgrade-aggregate.json"
    upgrade_matrix.write_text(
        json.dumps(
            {
                "schema_version": "power.upgrade-matrix.aggregate.v1",
                "content_free": True,
                "raw_content_in_report": False,
                "supported_platforms": ["linux"],
                "deferred_platforms": ["macos", "windows"],
                "platforms": {"linux": "executed"},
                "release_gate": {
                    "all_platforms_executed": True,
                    "local_invariants": True,
                },
            }
        ),
        encoding="utf-8",
    )
    validation_report = _write_validation_report(repo / "validation.json")
    subprocess.run(  # noqa: S603 -- invokes the test-local Git repository.
        [git_executable, "-C", str(repo), "add", "-A"], check=True
    )
    subprocess.run(  # noqa: S603 -- invokes the test-local Git repository.
        [git_executable, "-C", str(repo), "commit", "-qm", "candidate"], check=True
    )
    subprocess.run(  # noqa: S603 -- invokes the test-local Git repository.
        [git_executable, "-C", str(repo), "tag", "v3.5.0"], check=True
    )

    baseline = build_baseline(
        repo=repo,
        tag="v3.5.0",
        template_path=template,
        models_lock_path=models_lock,
        dataset_manifest_path=dataset,
        validation_report_path=validation_report,
        sbom_path=sbom,
        upgrade_matrix_path=upgrade_matrix,
    )

    assert baseline["candidate"] is False
    assert baseline["scope"]["technical_release"] is True
    assert baseline["scope"]["candidate_only"] is False
    assert baseline["validation"]["passed"] == 1014
    assert baseline["validation"]["skipped"] == 11
    assert baseline["validation"]["coverage_percent"] == 81.66

    (repo / "dirty-after-tag.txt").write_text("must block final baseline\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean worktree"):
        build_baseline(
            repo=repo,
            tag="v3.5.0",
            template_path=template,
            models_lock_path=models_lock,
            dataset_manifest_path=dataset,
            validation_report_path=validation_report,
            sbom_path=sbom,
            upgrade_matrix_path=upgrade_matrix,
        )
