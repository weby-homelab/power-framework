"""Regression tests for the machine-readable POWER release contract."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "verify_release_contract.py"
TEMPLATE = REPO_ROOT / "release" / "evidence" / "baselines" / "v3.4.5.json"
MODELS_LOCK = REPO_ROOT / "release" / "models.lock.json"
RELEASE_NOTES = REPO_ROOT / "docs" / "release-3.6.2.md"
PREPUBLICATION_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.ua.md",
    REPO_ROOT / "docs" / "getting-started.md",
    REPO_ROOT / "docs" / "getting-started.ua.md",
    REPO_ROOT / "docs" / "mcp-client-onboarding.md",
    REPO_ROOT / "docs" / "mcp-client-onboarding.ua.md",
)
EVIDENCE_IGNORE = REPO_ROOT / "release" / "evidence" / ".gitignore"

from scripts.verify_release_contract import _validate_git_source  # noqa: E402


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


def _write_candidate_validation(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "power.release-validation.v1",
            "status": "passed",
            "passed": 1,
            "skipped": 0,
            "coverage_percent": 70.0,
            "warning_count": 0,
            "warning_policy": "warnings are errors",
            "skipped_optional_gates": [],
            "mandatory_skipped": 0,
            "mandatory_failed": 0,
            "test_failures": 0,
            "test_errors": 0,
            "warnings_as_errors": True,
            "junit_sha256": "a" * 64,
            "coverage_sha256": "b" * 64,
            "gate_manifest_sha256": "c" * 64,
            "content_free": True,
        },
    )


def _build_candidate(tmp_path: Path) -> Path:
    output = tmp_path / "candidate.json"
    result = subprocess.run(  # noqa: S603 -- invokes the repository-local generator.
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_release_candidate.py"),
            "--output",
            str(output),
            "--validation-report",
            str(_write_candidate_validation(tmp_path / "validation.json")),
            "--template",
            str(TEMPLATE),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return output


def test_current_release_contract_is_valid(tmp_path: Path) -> None:
    candidate = _build_candidate(tmp_path)
    result = _run_validator(
        "--candidate",
        "--require-worktree-hash",
        "--baseline",
        str(candidate),
    )

    assert result.returncode == 0, result.stderr


def test_candidate_worktree_hash_must_match_current_checkout(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["source"]["worktree_sha256"] = "0" * 64
    altered_baseline = _write_json(tmp_path / "stale-candidate.json", baseline)

    result = _run_validator(
        "--candidate",
        "--require-worktree-hash",
        "--baseline",
        str(altered_baseline),
    )

    assert result.returncode == 1
    assert "does not match the current worktree" in result.stderr


def test_validation_receipt_contract_is_fail_closed(tmp_path: Path) -> None:
    cases = (
        ("status", "failed", "validation.status must be passed"),
        ("content_free", False, "validation.content_free must be true"),
        ("junit_sha256", "missing", "validation.junit_sha256 must be a SHA-256"),
        ("test_failures", 1, "zero test failures and errors"),
    )
    for field, value, expected in cases:
        baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
        if value == "missing":
            baseline["validation"].pop(field)
        else:
            baseline["validation"][field] = value
        altered_baseline = _write_json(tmp_path / f"invalid-{field}.json", baseline)

        result = _run_validator("--candidate", "--baseline", str(altered_baseline))

        assert result.returncode == 1
        assert expected in result.stderr


def test_candidate_gate_rejects_final_publication_scope(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["candidate"] = False
    baseline["scope"]["candidate_only"] = False
    altered_baseline = _write_json(tmp_path / "final-as-candidate.json", baseline)

    result = _run_validator("--candidate", "--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "must carry candidate=true" in result.stderr
    assert "must carry scope.candidate_only=true" in result.stderr


def test_release_notes_keep_governance_claims_within_evidence_boundary() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")

    assert "Zero open repository issues" not in notes
    assert "published `v3.6.2` release" not in notes
    assert "physical `3.6.1` binary" in notes
    assert "not a claim of full previous-runtime upgrade" in notes
    assert "canonical Task v2 MCP filter/event surface" in notes
    assert "macOS and Windows remain outside the supported release boundary" in notes


def test_current_docs_do_not_claim_3_6_publication_without_remote_readback() -> None:
    forbidden_claims = (
        "`v3.6.2` is available",
        "`v3.6.2` доступний",
        "реліз містить machine",
        "the release contains the machine",
    )

    for path in PREPUBLICATION_DOCS:
        text = path.read_text(encoding="utf-8")
        for claim in forbidden_claims:
            assert claim not in text, f"{path.name} makes an unverified publication claim"


def test_default_3_6_2_baseline_is_fail_closed_until_tag_workflow_generates_it() -> None:
    ignore_text = EVIDENCE_IGNORE.read_text(encoding="utf-8")

    assert not (REPO_ROOT / "release" / "evidence" / "baselines" / "v3.6.2.json").exists()
    assert "baselines/v3.6.2.json" in ignore_text
    assert "final baseline is generated from the clean signed tag" in ignore_text


def test_windows_rollback_points_to_the_previous_stable_release() -> None:
    for relative_path in (
        "docs/windows-11-installation.md",
        "docs/windows-11-installation.ua.md",
    ):
        guide = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "v3.4.5" in guide
        assert ("releases/download/v3.4.5/power_framework-3.4.5-py3-none-any.whl") in guide
        assert "--force-reinstall $ReleaseWheel" not in guide


def test_model_lock_version_must_match_project_version(tmp_path: Path) -> None:
    models_lock = json.loads(MODELS_LOCK.read_text(encoding="utf-8"))
    models_lock["release"] = "9.9.9"
    altered_lock = _write_json(tmp_path / "models.lock.json", models_lock)

    result = _run_validator(
        "--models-lock",
        str(altered_lock),
        "--baseline",
        str(_build_candidate(tmp_path)),
    )

    assert result.returncode == 1
    assert "does not match project version" in result.stderr


def test_model_lock_hash_is_stable_for_windows_crlf_checkout(tmp_path: Path) -> None:
    canonical = MODELS_LOCK.read_bytes().replace(b"\r\n", b"\n")
    crlf_lock = tmp_path / "models.lock.json"
    crlf_lock.write_bytes(canonical.replace(b"\n", b"\r\n"))

    result = _run_validator(
        "--candidate",
        "--models-lock",
        str(crlf_lock),
        "--baseline",
        str(_build_candidate(tmp_path)),
    )

    assert result.returncode == 0, result.stderr


def test_dirty_source_cannot_be_a_release_baseline(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["source"]["clean"] = False
    dirty_baseline = _write_json(tmp_path / "dirty-baseline.json", baseline)

    result = _run_validator("--baseline", str(dirty_baseline))

    assert result.returncode == 1
    assert "source.clean must be true" in result.stderr


def test_benchmark_hash_must_match_frozen_dataset(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["benchmark"]["queries_sha256"] = "0" * 64
    altered_baseline = _write_json(tmp_path / "altered-baseline.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "benchmark.queries_sha256 does not match" in result.stderr


def test_source_tree_must_be_a_real_tree_matching_commit(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["source"]["tree"] = "0" * 40
    altered_baseline = _write_json(tmp_path / "altered-baseline.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "does not resolve to a Git tree" in result.stderr


def test_source_tag_must_point_to_source_commit(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["source"]["tag"] = "v3.2.4"
    altered_baseline = _write_json(tmp_path / "altered-baseline.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "does not point to source.commit" in result.stderr


def test_release_tag_is_required_for_final_gate(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["source"]["tag"] = "v9.9.9"
    candidate_baseline = _write_json(tmp_path / "candidate-baseline.json", baseline)

    candidate = _run_validator("--candidate", "--baseline", str(candidate_baseline))
    assert candidate.returncode == 0, candidate.stderr

    final = _run_validator(
        "--baseline",
        str(candidate_baseline),
        "--require-tag",
    )
    assert final.returncode == 1
    assert "does not resolve to a commit" in final.stderr


def test_final_gate_rejects_candidate_publication_scope(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["source"]["clean"] = True
    baseline["candidate"] = True
    baseline["scope"]["candidate_only"] = True
    baseline["scope"]["technical_release"] = False
    altered_baseline = _write_json(tmp_path / "candidate-scope.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "cannot carry candidate=true" in result.stderr
    assert "cannot carry candidate_only=true" in result.stderr
    assert "technical_release must be true" in result.stderr


def test_final_gate_rejects_ambiguous_phase8_quality_scope(tmp_path: Path) -> None:
    baseline = json.loads(_build_candidate(tmp_path).read_text(encoding="utf-8"))
    baseline["candidate"] = False
    baseline["source"]["clean"] = True
    baseline["scope"].update(
        {
            "technical_release": True,
            "candidate_only": False,
        }
    )
    altered_baseline = _write_json(tmp_path / "unproven-phase8.json", baseline)

    result = _run_validator("--baseline", str(altered_baseline))

    assert result.returncode == 1
    assert "Phase 8 evidence status must be optional or passed" in result.stderr


def test_candidate_generator_accepts_output_outside_checkout(tmp_path: Path) -> None:
    output = tmp_path / "candidate.json"
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps(
            {
                "schema_version": "power.release-validation.v1",
                "status": "passed",
                "passed": 1020,
                "skipped": 11,
                "coverage_percent": 81.66,
                "warning_count": 0,
                "warning_policy": "warnings are errors",
                "skipped_optional_gates": ["physical platforms"],
                "mandatory_skipped": 0,
                "mandatory_failed": 0,
                "test_failures": 0,
                "test_errors": 0,
                "warnings_as_errors": True,
                "junit_sha256": "a" * 64,
                "coverage_sha256": "b" * 64,
                "gate_manifest_sha256": "c" * 64,
                "content_free": True,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 -- invokes the repository-local generator.
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_release_candidate.py"),
            "--output",
            str(output),
            "--validation-report",
            str(validation),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["candidate"] is True
    verified = _run_validator(
        "--candidate",
        "--require-worktree-hash",
        "--baseline",
        str(output),
    )
    assert verified.returncode == 0, verified.stderr


def test_signed_tag_requirement_rejects_unsigned_annotated_tag(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    git = shutil.which("git")
    assert git is not None

    def run_git(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 -- fixed Git executable and test-local arguments.
            [git, *args], check=True, capture_output=capture_output, text=True
        )

    run_git("init", "-q", "-b", "main", str(repo))
    run_git("-C", str(repo), "config", "user.name", "test")
    run_git("-C", str(repo), "config", "user.email", "test@example.invalid")
    (repo / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    run_git("-C", str(repo), "add", "tracked.txt")
    run_git("-C", str(repo), "commit", "-qm", "fixture")
    run_git("-C", str(repo), "tag", "-a", "v3.5.0", "-m", "unsigned fixture")
    commit = run_git("-C", str(repo), "rev-parse", "HEAD", capture_output=True).stdout.strip()
    tree = run_git(
        "-C", str(repo), "show", "-s", "--format=%T", "HEAD", capture_output=True
    ).stdout.strip()

    errors: list[str] = []
    _validate_git_source(
        {"commit": commit, "tree": tree, "tag": "v3.5.0"},
        release="3.5.0",
        git_repo=repo,
        require_tag=True,
        require_signed_tag=True,
        errors=errors,
    )

    assert any("not a valid signed tag" in error for error in errors)
