"""Regression checks for blocking GitHub Actions policy."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
REPO_ROOT = WORKFLOWS_DIR.parent.parent
FORBIDDEN_WORKFLOW_PATTERNS = ("continue-on-error", "|| true", "/root/gemma/brain")


def test_pr_workflows_do_not_suppress_or_depend_on_private_vaults() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in WORKFLOWS_DIR.glob("*.yml")
    )

    for pattern in FORBIDDEN_WORKFLOW_PATTERNS:
        assert pattern not in workflow_text, f"workflow policy forbids {pattern!r}"


def test_ci_keeps_blocking_test_and_security_jobs() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "  test:" in ci_text
    assert "  security:" in ci_text


def test_ci_defers_non_linux_runtime_smoke_for_3_5_0() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "windows-latest" not in ci_text
    assert "macos-latest" not in ci_text
    assert "runs-on: ubuntu-latest" in ci_text


def test_ci_aggregates_all_supported_ubuntu_reports() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "  upgrade-matrix-aggregate:" in ci_text
    assert "actions/upload-artifact@" in ci_text
    assert "actions/download-artifact@" in ci_text
    assert "merge-multiple: true" in ci_text
    assert "scripts/aggregate_upgrade_matrix.py" in ci_text
    assert "os: [ubuntu-latest]" in ci_text
    assert "--require-supported-platforms" in ci_text
    assert "name: power35-upgrade-aggregate" in ci_text
    assert "power35-upgrade-aggregate.json" in ci_text


def test_current_python_support_starts_at_3_11() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.11"' in pyproject_text
    assert '"Programming Language :: Python :: 3.10"' not in pyproject_text
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in ci_text
    assert '"3.10"' not in ci_text


def test_workflow_actions_are_pinned_to_immutable_commits() -> None:
    for workflow_path in WORKFLOWS_DIR.glob("*.yml"):
        for line in workflow_path.read_text(encoding="utf-8").splitlines():
            if "uses:" not in line:
                continue
            assert re.search(r"uses:\s+[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$", line), (
                f"{workflow_path.name} contains an unpinned action: {line.strip()}"
            )


def test_release_workflow_publishes_sbom_and_attestation() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert "anchore/sbom-action@" in release_text
    assert "actions/attest-build-provenance@" in release_text
    assert "dist/*.spdx.json" in release_text
    assert "attestations: write" in release_text
    assert "id-token: write" in release_text
    assert "gh release view" in release_text
    assert "GitHub release readback verified" in release_text


def test_release_publish_is_blocked_by_a_tag_validation_job() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert "  validate:" in release_text
    assert "uv sync --locked --group dev --extra semantic --extra rerank" in release_text
    assert "uv run pytest tests/" in release_text
    assert "uv run mkdocs build --strict" in release_text
    assert "complexity_dashboard.py --baseline-revision v3.4.5 --require-budget" in release_text
    assert "  upgrade-matrix:" in release_text
    assert "os: [ubuntu-latest]" in release_text
    assert "--require-supported-platforms" in release_text
    assert "macos-latest" not in release_text
    assert "windows-latest" not in release_text
    assert "  upgrade-matrix-aggregate:" in release_text
    assert "needs: validate" in release_text
    assert "needs: [validate, upgrade-matrix-aggregate]" in release_text
    assert "--require-signed-tag" in release_text
    assert "Install the pinned maintainer release signing key" in release_text
    assert "gh api users/weby-homelab/gpg_keys" in release_text
    assert 'select(.key_id == "2D49E810C7F2527E")' in release_text
    assert "7AF1EDA195FE29FF093FB1CA2D49E810C7F2527E" in release_text
    assert 'gpg --batch --import "$key_file"' in release_text


def test_release_materializes_phase8_evidence_through_protected_environment() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert "name: power35-stable-release" in release_text
    assert "POWER35_REAL_VAULT_RECEIPT_JSON" in release_text
    assert "POWER35_HUMAN_MANIFEST_JSON" in release_text
    assert (
        "POWER35_REAL_VAULT_RECEIPT_JSON: ${{ secrets.POWER35_REAL_VAULT_RECEIPT_JSON }}"
        in release_text
    )
    assert "POWER35_HUMAN_MANIFEST_JSON: ${{ secrets.POWER35_HUMAN_MANIFEST_JSON }}" in release_text
    assert "scripts/materialize_phase8_evidence.py" in release_text
    assert '--output-dir "$RUNNER_TEMP/power35-phase8"' in release_text


def test_ci_uses_locked_dependencies_and_clean_package_smoke() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    docs_text = (WORKFLOWS_DIR / "docs.yml").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert (REPO_ROOT / "uv.lock").is_file()
    assert ci_text.count("uv sync --locked --group dev") >= 4
    assert "uv sync --locked --group dev --extra semantic --extra rerank" in ci_text
    assert '"mkdocs>=' in pyproject_text
    assert '"mkdocs-material>=' in pyproject_text
    assert "uv sync --locked --group dev" in docs_text
    assert "uv run mkdocs build --strict" in docs_text
    assert "package-smoke:" in ci_text
    assert "scripts/smoke_package.py" in ci_text
    assert "scripts/smoke_package.py" in release_text
    assert "scripts/generate_release_receipt.py" in release_text
    assert "maintainer-provisioned Phase 8 evidence" in release_text
    assert "--phase8-real-vault-receipt" in release_text
    assert "--phase8-human-manifest" in release_text
    assert "run_outcome_benchmark.py" in release_text
    assert "run_continuity_benchmark.py" in release_text
    assert "scripts/generate_release_validation.py" in release_text
    assert "scripts/generate_release_gate_manifest.py" in release_text
    assert "scripts/generate_release_candidate.py" in release_text
    assert "--require-worktree-hash" in release_text
    assert "power35-gates.json" in release_text
    assert "power35-validation.json" in release_text
    assert "--gate-manifest" in release_text
    assert '--junitxml="$RUNNER_TEMP/power35-junit.xml"' in release_text
    assert '--cov-report=json:"$RUNNER_TEMP/power35-coverage.json"' in release_text
    assert "power35-phase8-technical-receipts" in release_text
    assert 'assert outcome["raw_content_in_report"] is False' in release_text
    assert 'assert outcome["comparison"]["practical_improvement"] is True' in release_text
    assert 'assert continuity["gate"]["power_beats_plain_handoff"] is True' in release_text
    assert "--phase8-outcome-receipt" in release_text
    assert "--phase8-continuity-receipt" in release_text
    assert "--validation-report" in release_text
    assert "--sbom" in release_text
    assert "--upgrade-matrix-aggregate" in release_text
    assert "power35-release-upgrade-aggregate" in release_text


def test_quarantined_fleet_docs_and_helper_forbid_live_cache_transfer() -> None:
    guide_paths = [
        REPO_ROOT / "docs" / "guides" / "hybrid-fleet-gpu-offloading-guide.md",
        REPO_ROOT / "docs" / "guides" / "hybrid-fleet-gpu-offloading-guide.ua.md",
    ]
    forbidden = re.compile(r"(?:rsync\b|generation-state\.db|[-_]wal\b|[-_]shm\b)", re.IGNORECASE)

    for guide_path in guide_paths:
        guide_text = guide_path.read_text(encoding="utf-8")
        assert "quarantined" in guide_text.lower()
        assert "3.5.0" in guide_text
        assert "not" in guide_text.lower() or "не" in guide_text.lower()
        assert not forbidden.search(guide_text), guide_path

    helper_path = REPO_ROOT.parent.parent / "scripts" / "sync_brain_db_from_ws.sh"
    if helper_path.is_file():
        helper_text = helper_path.read_text(encoding="utf-8")
        assert "no-op" in helper_text.lower()
        assert "disabled until manifest/quarantine/rollback support exists" in helper_text.lower()
        assert not forbidden.search(helper_text), (
            "legacy helper must not reintroduce live-cache copy"
        )
