"""Tests for tag-bound release baseline generation."""

from __future__ import annotations

import hashlib
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

    expected_commit = tag.stdout.strip()
    expected_tree = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local object.
        [git_executable, "show", "-s", "--format=%T", expected_commit],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local refs.
        [git_executable, "rev-parse", "--verify", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != expected_commit:
        pytest.skip(f"{tag_name} is not checked out; final baseline is tag-gate only")
    worktree = subprocess.run(  # noqa: S603 -- fixed Git executable and repository-local refs.
        [git_executable, "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if worktree.stdout.strip():
        pytest.skip(f"{tag_name} baseline requires a clean checkout; local worktree is dirty")
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

    (tmp_path / "corpus.jsonl").write_text('{"doc_id": "d1"}\n', encoding="utf-8")
    (tmp_path / "queries.jsonl").write_text(
        '{"query_id": "q1", "journey": "current_fact"}\n'
        '{"query_id": "q2", "journey": "historical_fact"}\n'
        '{"query_id": "q3", "journey": "provenance_trace"}\n'
        '{"query_id": "q4", "journey": "abstention"}\n'
        '{"query_id": "q5", "journey": "candidate_boundary"}\n',
        encoding="utf-8",
    )
    (tmp_path / "raw-judgments.jsonl").write_text('{"relevance": 2}\n', encoding="utf-8")
    (tmp_path / "adjudicated-qrels.jsonl").write_text(
        '{"query_id": "q1", "document_id": "d1", "final": {"relevance": 2, "acceptable_citation": true, "temporal_status": "current"}}\n'
        '{"query_id": "q2", "document_id": "d2", "final": {"relevance": 2, "acceptable_citation": true, "temporal_status": "historical"}}\n'
        '{"query_id": "q3", "document_id": "d3", "final": {"relevance": 2, "acceptable_citation": true, "temporal_status": "not_applicable"}}\n'
        '{"query_id": "q4", "document_id": "d4", "final": {"relevance": 0, "acceptable_citation": false, "temporal_status": "not_applicable"}}\n'
        '{"query_id": "q5", "document_id": "d5", "final": {"relevance": 2, "acceptable_citation": true, "temporal_status": "not_applicable"}}\n',
        encoding="utf-8",
    )
    (tmp_path / "annotation_protocol_v2.md").write_text("protocol\n", encoding="utf-8")
    (tmp_path / "calibration-agreement.v2.json").write_text(
        json.dumps(
            {
                "schema_version": "power.m2.human-agreement.v2",
                "annotation_protocol_version": "2.0",
                "status": "calibration_passed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    raw_sha = hashlib.sha256((tmp_path / "raw-judgments.jsonl").read_bytes()).hexdigest()
    (tmp_path / "adjudication-agreement.v2.json").write_text(
        json.dumps(
            {
                "schema_version": "power.m2.human-agreement.v2",
                "annotation_protocol_version": "2.0",
                "status": "calibration_passed",
                "raw_judgments_sha256": raw_sha,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    human_manifest_dict = {
        "schema_version": "2.0",
        "status": "adjudicated",
        "split": "sealed_holdout",
        "language": "uk",
        "threshold_profile": "m2-v2.1",
        "annotator_count": 2,
        "journeys": [
            "current_fact",
            "historical_fact",
            "provenance_trace",
            "abstention",
            "candidate_boundary",
        ],
        "thresholds": {
            "recall_at_10": 0.75,
            "ndcg_at_10": 0.70,
            "mrr_at_10": 0.70,
            "citation_provenance_accuracy": 0.95,
            "stale_answer_rate_max": 0.02,
            "abstention_quality": 0.90,
            "p95_latency_ms": 1500,
        },
        "artifacts": {
            "corpus": "corpus.jsonl",
            "queries": "queries.jsonl",
            "raw_judgments": "raw-judgments.jsonl",
            "adjudicated_qrels": "adjudicated-qrels.jsonl",
        },
        "annotation_protocol": "annotation_protocol_v2.md",
        "calibration": {
            "status": "passed",
            "agreement_receipt": "calibration-agreement.v2.json",
            "agreement_receipt_sha256": hashlib.sha256(
                (tmp_path / "calibration-agreement.v2.json").read_bytes()
            ).hexdigest(),
        },
        "agreement": {
            "receipt": "adjudication-agreement.v2.json",
            "receipt_sha256": hashlib.sha256(
                (tmp_path / "adjudication-agreement.v2.json").read_bytes()
            ).hexdigest(),
        },
        "corpus_sha256": hashlib.sha256((tmp_path / "corpus.jsonl").read_bytes()).hexdigest(),
        "queries_sha256": hashlib.sha256((tmp_path / "queries.jsonl").read_bytes()).hexdigest(),
        "raw_judgments_sha256": raw_sha,
        "adjudicated_qrels_sha256": hashlib.sha256(
            (tmp_path / "adjudicated-qrels.jsonl").read_bytes()
        ).hexdigest(),
    }
    human_manifest_bytes = json.dumps(human_manifest_dict, indent=2).encode("utf-8")
    human_manifest_path = tmp_path / "human-manifest.json"
    human_manifest_path.write_bytes(human_manifest_bytes)

    real_vault_dict = {
        "schema_version": "power.phase8.real-vault-receipt.v1",
        "release": version,
        "status": "passed",
        "content_free": True,
        "raw_content_present": False,
        "source": {"revision": expected_commit, "clean": True},
        "vault": {
            "opaque_id": "real-vault-prxmx01-prod-202608",
            "snapshot_sha256": "a" * 64,
            "note_count": 10,
        },
        "runtime": {
            "executable": "power",
            "provider": "cpu",
            "generation": "g1",
            "config_sha256": "b" * 64,
        },
        "experiments": [
            {"id": "build", "status": "passed", "receipt_sha256": "c" * 64},
            {
                "id": "transfer",
                "status": "passed",
                "receipt_sha256": "d" * 64,
                "bytes": {"full": 100, "wire": 50, "delta": 10, "compression": "zstd"},
            },
            {"id": "import", "status": "passed", "receipt_sha256": "e" * 64},
            {"id": "query", "status": "passed", "receipt_sha256": "f" * 64},
        ],
        "quality": {
            "sealed_dataset": True,
            "real_vault": True,
            "blind_scoring": True,
            "no_answer_scoring": True,
            "outcome_gate": "pass",
            "power_beats_no_power": True,
            "comparators": ["fts", "auto", "semantic", "no_power"],
            "metrics": {
                "recall_at_10": 0.8,
                "ndcg_at_10": 0.8,
                "mrr_at_10": 0.8,
                "evidence_use": 0.9,
                "no_answer_score": 0.9,
                "stale_answer_rate": 0.01,
                "latency_p95_ms": 100.0,
            },
            "fresh_agent_completion_percent": 100.0,
            "safety_invariants_percent": 100.0,
            "median_human_reminders": 0,
        },
        "human_evidence": {
            "status": "passed",
            "sealed_holdout": True,
            "manifest_sha256": hashlib.sha256(human_manifest_bytes).hexdigest(),
        },
    }
    real_vault_path = tmp_path / "real-vault-receipt.json"
    real_vault_path.write_text(json.dumps(real_vault_dict), encoding="utf-8")

    outcome_path = tmp_path / "outcome-receipt.json"
    outcome_path.write_text(
        json.dumps(
            {
                "schema_version": "power.phase8.outcome-receipt.v1",
                "release": version,
                "status": "passed",
                "source": {"revision": expected_commit, "clean": True},
                "metrics": {"recall_at_10": 0.8},
                "fresh_agent_completion_percent": 100.0,
                "safety_invariants_percent": 100.0,
            }
        ),
        encoding="utf-8",
    )
    continuity_path = tmp_path / "continuity-receipt.json"
    continuity_path.write_text(
        json.dumps(
            {
                "schema_version": "power.phase8.continuity-receipt.v1",
                "release": version,
                "status": "passed",
                "source": {"revision": expected_commit, "clean": True},
                "soak_hours": 24,
                "retention_integrity_percent": 100.0,
                "readback_pass_rate_percent": 100.0,
            }
        ),
        encoding="utf-8",
    )

    outcome_path = tmp_path / "outcome-receipt.json"
    outcome_path.write_text(
        json.dumps(
            {
                "schema_version": "power.phase8-outcome.v2",
                "release": version,
                "source": {
                    "commit": expected_commit,
                    "tree": expected_tree,
                    "clean": True,
                    "worktree_sha256": "0" * 64,
                },
                "synthetic": True,
                "content_free": True,
                "workflow_count": 20,
                "gate": {
                    "fresh_agent_completion": 1.0,
                    "safety_invariants_100": True,
                    "false_premise_abstention": True,
                    "stale_state_filter": True,
                    "technical_continuity_20": True,
                    "blocked_workflow_abstention": True,
                    "median_human_reminders": 0,
                },
                "comparison": {
                    "practical_improvement": True,
                    "power_mean_score": 0.95,
                    "no_power_mean_score": 0.35,
                    "evidence_recall": {"power": 0.75, "no_power": 0.0},
                },
                "feedback_reuse": {
                    "measured": False,
                    "reason": "no human labels",
                },
                "retrieval_profiles": {
                    "fts": {"status": "executed"},
                    "auto": {"status": "executed"},
                    "semantic": {
                        "status": "not_evaluated",
                        "reason": "no sealed provider",
                    },
                },
                "blind_scoring": False,
                "bootstrap_context_tokens": {"measured": False},
                "raw_content_in_report": False,
                "human_quality_certification": False,
                "real_vault": False,
                "sealed_holdout": "not_opened",
            }
        ),
        encoding="utf-8",
    )
    continuity_path = tmp_path / "continuity-receipt.json"
    continuity_path.write_text(
        json.dumps(
            {
                "schema_version": "power.phase8-continuity.v2",
                "release": version,
                "source": {
                    "commit": expected_commit,
                    "tree": expected_tree,
                    "clean": True,
                    "worktree_sha256": "0" * 64,
                },
                "synthetic": True,
                "content_free": True,
                "workflow_count": 20,
                "independent_processes": 60,
                "plain_handoff_processes": 40,
                "metrics": {"duplicate_work_rate": 0.0},
                "gate": {
                    "correct_resume_20": True,
                    "proof_carrying_handoff": True,
                    "source_preserved": True,
                    "unsafe_actions_100_percent_safe": True,
                    "human_reminders_median_zero": True,
                    "power_beats_plain_handoff": True,
                },
                "comparison": {
                    "practical_improvement": True,
                    "power_continuity_rate": 1.0,
                    "plain_handoff_continuity_rate": 0.0,
                },
                "raw_content_in_report": False,
                "human_quality_certification": False,
                "real_vault": False,
                "sealed_holdout": "not_opened",
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
            "--phase8-real-vault-receipt",
            str(real_vault_path),
            "--phase8-human-manifest",
            str(human_manifest_path),
            "--phase8-outcome-receipt",
            str(outcome_path),
            "--phase8-continuity-receipt",
            str(continuity_path),
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
    assert baseline["source"]["commit"] == expected_commit
    assert baseline["source"]["tree"] == expected_tree

    verified = subprocess.run(  # noqa: S603 -- invokes repository-local scripts.
        [
            sys.executable,
            str(VERIFY),
            "--require-tag",
            "--sbom",
            str(sbom),
            "--upgrade-matrix-aggregate",
            str(upgrade_matrix),
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
